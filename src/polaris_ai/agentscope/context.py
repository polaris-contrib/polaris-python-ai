"""Shared Polaris connection factory for AgentScope applications."""

import asyncio
from collections.abc import Iterable

from polaris.api.config import init_context_by_config
from polaris.api.consumer import ConsumerAPI
from polaris.api.log import LogOptions
from polaris.api.provider import ProviderAPI
from polaris.api.skill import SkillAPI
from polaris.pkg.config.api import Configuration

from polaris_ai._async import await_completion

DEFAULT_DISCOVERY_ADDRESS = "127.0.0.1:8091"
SKILL_ADDRESS_PORT = 8094


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
        if not host:
            raise ValueError(f"Invalid Polaris address {address!r}: empty IPv6 host")
    elif host.count(":") > 0:
        raise ValueError(f"Invalid Polaris address {address!r}: IPv6 hosts require brackets")
    if not host.strip():
        raise ValueError(f"Invalid Polaris address {address!r}: host is empty")
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def derive_skill_addresses(addresses: Iterable[str]) -> list[str]:
    """Map discovery endpoints to the standard Skill endpoint on each host."""
    result = []
    for address in addresses:
        normalized = _validate_address(address)
        host, _, _ = normalized.rpartition(":")
        skill_address = f"{host}:{SKILL_ADDRESS_PORT}"
        if skill_address not in result:
            result.append(skill_address)
    if not result:
        raise ValueError("At least one discovery address is required")
    return result


class PolarisAgentContext:
    """Expose shared Provider, Consumer and Skill APIs over one SDK context.

    A supplied context is borrowed and is never modified or destroyed by this
    factory. When no context is supplied, the factory owns the context it
    creates, disables stat reporting, and derives Skill addresses from the
    discovery addresses. Like Java's PolarisContextManager, it also disables
    the provider lossless lifecycle for this owned context.
    """

    def __init__(
        self,
        namespace: str = "default",
        *,
        address: str | Iterable[str] = DEFAULT_DISCOVERY_ADDRESS,
        connector_token: str = "",
        skill_address: str | Iterable[str] = "",
        log_options: LogOptions | None = None,
        sdk_context=None,
    ):
        if sdk_context is not None:
            if sdk_context.is_destroy():
                raise ValueError("An active SDKContext is required")
            self._owns_context = False
            self._context = sdk_context
        else:
            if isinstance(address, str):
                addresses = [address]
            else:
                addresses = list(address)
            if not addresses:
                raise ValueError("At least one discovery address is required")
            addresses = [_validate_address(item) for item in addresses]
            if isinstance(skill_address, str):
                skill_addresses = [] if not skill_address else [skill_address]
            else:
                skill_addresses = list(skill_address)
            skill_addresses = [_validate_address(item) for item in skill_addresses]
            if not skill_addresses:
                skill_addresses = derive_skill_addresses(addresses)

            config = Configuration()
            config.set_default()
            config.get_global().get_server_connector().addresses = addresses
            config.get_global().get_server_connector().token = connector_token
            config.get_global().get_stat_reporter().enable = False
            config.get_provider().get_lossless().enable = False
            config.get_ai().get_skill().get_server_connector().addresses = skill_addresses
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
            self.skill = SkillAPI(self._context)
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
        skill_address: str | Iterable[str] = "",
        log_options: LogOptions | None = None,
    ) -> "PolarisAgentContext":
        return cls(
            namespace,
            address=address,
            connector_token=connector_token,
            skill_address=skill_address,
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
            raise RuntimeError("PolarisAgentContext is closed")

    def close(self):
        """Close owned resources; borrowed contexts remain untouched."""
        if self._closed:
            return
        self._closed = True
        self.provider = None
        self.consumer = None
        self.skill = None
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
