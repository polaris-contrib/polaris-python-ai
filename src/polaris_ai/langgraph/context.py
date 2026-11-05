# Tencent is pleased to support the open source community by making polaris-python-ai available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# Licensed under the BSD 3-Clause License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

"""A small Polaris connection factory for LangGraph applications."""

import asyncio
from collections.abc import Iterable

from polaris.api.config import init_context_by_config
from polaris.api.consumer import ConsumerAPI
from polaris.api.log import LogOptions
from polaris.api.provider import ProviderAPI
from polaris.pkg.config.api import Configuration

from polaris_ai._async import await_completion

DEFAULT_DISCOVERY_ADDRESS = "127.0.0.1:8091"


def _validate_address(address: str) -> str:
    if not isinstance(address, str) or not address.strip():
        raise ValueError("Polaris addresses must be nonempty host:port values")
    address = address.strip()
    host, separator, port_text = address.rpartition(":")
    if not separator or not host:
        raise ValueError(f"Invalid Polaris address {address!r}: a port is required")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError(f"Invalid Polaris address {address!r}: port must be an integer") from error
    if not 0 < port < 65536:
        raise ValueError(f"Invalid Polaris address {address!r}: port must be in [1, 65535]")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    elif host.count(":") > 0:
        raise ValueError(f"Invalid Polaris address {address!r}: IPv6 hosts require brackets")
    if not host.strip():
        raise ValueError(f"Invalid Polaris address {address!r}: host is empty")
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


class PolarisLangGraphContext:
    """Expose Provider and Consumer APIs over one borrowed or owned SDK context."""

    def __init__(
        self,
        namespace: str = "default",
        *,
        address: str | Iterable[str] = DEFAULT_DISCOVERY_ADDRESS,
        connector_token: str = "",
        log_options: LogOptions | None = None,
        sdk_context=None,
    ):
        if sdk_context is not None:
            if sdk_context.is_destroy():
                raise ValueError("An active SDKContext is required")
            self._owns_context = False
            self._context = sdk_context
        else:
            addresses = [address] if isinstance(address, str) else list(address)
            if not addresses:
                raise ValueError("At least one discovery address is required")
            config = Configuration()
            config.set_default()
            config.get_global().get_server_connector().addresses = [
                _validate_address(item) for item in addresses
            ]
            config.get_global().get_server_connector().token = connector_token
            config.get_provider().get_lossless().enable = False
            self._owns_context = True
            self._context = None
            try:
                self._context = init_context_by_config(config, log_options=log_options)
            except BaseException:
                if self._context is not None:
                    self._context.destroy()
                raise

        self.namespace = namespace.strip() or "default"
        self._closed = False
        try:
            self.provider = ProviderAPI(self._context)
            self.consumer = ConsumerAPI(self._context)
        except BaseException:
            self.close()
            raise

    @classmethod
    def from_address(
        cls,
        address: str | Iterable[str] = DEFAULT_DISCOVERY_ADDRESS,
        namespace: str = "default",
        *,
        connector_token: str = "",
        log_options: LogOptions | None = None,
    ) -> "PolarisLangGraphContext":
        return cls(
            namespace,
            address=address,
            connector_token=connector_token,
            log_options=log_options,
        )

    @property
    def context(self):
        return self._context

    @property
    def owns_context(self) -> bool:
        return self._owns_context

    def _check_open(self):
        if self._closed or self._context is None or self._context.is_destroy():
            raise RuntimeError("PolarisLangGraphContext is closed")

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.provider = None
        self.consumer = None
        if self._owns_context and self._context is not None:
            self._context.destroy()

    async def async_close(self):
        await await_completion(asyncio.to_thread(self.close))

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *_):
        self.close()

    async def __aenter__(self):
        self._check_open()
        return self

    async def __aexit__(self, *_):
        await self.async_close()
