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

"""Resolve healthy LangGraph Server endpoints through Polaris discovery."""

import asyncio
from dataclasses import dataclass
from threading import RLock
from urllib.parse import urlsplit, urlunsplit

from polaris.api.consumer import ConsumerAPI
from polaris.pkg.model.error import SDKError
from polaris.pkg.model.service import GetHealthyInstancesRequest

from polaris_ai._async import await_completion
from polaris_ai.log import get_ai_logger

from .registry import META_GRAPH_ID, META_PATH, META_PROTOCOL


class LangGraphEndpointNotFoundError(LookupError):
    """No healthy LangGraph instance matched the requested service and graph."""


@dataclass(frozen=True)
class LangGraphEndpoint:
    namespace: str
    service: str
    graph_id: str
    host: str
    port: int
    protocol: str
    path: str

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        path = self.path if self.path.startswith("/") else f"/{self.path}"
        return urlunsplit((self.protocol, f"{host}:{self.port}", path, "", ""))


class PolarisLangGraphResolver:
    """Keep a sticky endpoint while refreshing discovery for every lookup."""

    def __init__(
        self,
        sdk_context,
        namespace: str = "default",
        *,
        timeout: int = 0,
        logger=None,
    ):
        if sdk_context is None or sdk_context.is_destroy():
            raise ValueError("An active SDKContext is required")
        if type(timeout) is not int or timeout < 0:
            raise ValueError("timeout must be a nonnegative integer")
        self.namespace = namespace.strip() or "default"
        self.timeout = timeout
        self.logger = logger if logger is not None else get_ai_logger("langgraph")
        self._context = sdk_context
        self._consumer = ConsumerAPI(sdk_context)
        self._cache: dict[tuple[str, str], LangGraphEndpoint] = {}
        self._lock = RLock()
        self._closed = False

    def _check_open(self):
        if self._closed or self._context.is_destroy():
            raise RuntimeError("LangGraph resolver or SDKContext is closed")

    @staticmethod
    def _endpoint_key(graph_id: str, service: str) -> tuple[str, str]:
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise ValueError("graph_id is required")
        if service is None:
            service = ""
        if not isinstance(service, str):
            raise ValueError("service must be a string")
        graph_id = graph_id.strip()
        return (service.strip() or graph_id, graph_id)

    def resolve(self, graph_id: str, service: str = "") -> LangGraphEndpoint:
        """Return a healthy LangGraph endpoint, retaining the previous ``host:port``."""
        service, graph_id = self._endpoint_key(graph_id, service)
        key = (service, graph_id)
        with self._lock:
            self._check_open()
            cached = self._cache.get(key)
            try:
                response = self._consumer.get_healthy_instances(
                    GetHealthyInstancesRequest(
                        namespace=self.namespace,
                        service=service,
                        timeout=self.timeout,
                        exclude_offline_service=True,
                    )
                )
            except SDKError:
                if cached is None:
                    raise
                self.logger.warning_throttled(
                    ("refresh", service, graph_id),
                    "Failed to refresh LangGraph %s; reusing %s:%s",
                    service,
                    cached.host,
                    cached.port,
                )
                return cached

            instances = [] if response is None else list(response.get_instances())
            instances = [item for item in instances if item.is_healthy() and not item.is_isolated()]
            if cached is not None:
                instances.sort(
                    key=lambda item: (
                        item.get_host(),
                        item.get_port(),
                    )
                    != (cached.host, cached.port)
                )
            for instance in instances:
                metadata = instance.get_metadata()
                registered_graph = metadata.get(META_GRAPH_ID, "").strip()
                if registered_graph and registered_graph != graph_id:
                    continue
                protocol = metadata.get(META_PROTOCOL, "").strip() or instance.get_protocol().strip()
                path = metadata.get(META_PATH, "").strip() or "/"
                if protocol not in ("http", "https") or not path.startswith("/"):
                    self.logger.warning_throttled(
                        ("invalid-endpoint", service, instance.get_host(), instance.get_port()),
                        "Skipping invalid LangGraph endpoint metadata for %s at %s:%s",
                        service,
                        instance.get_host(),
                        instance.get_port(),
                    )
                    continue
                endpoint = LangGraphEndpoint(
                    namespace=self.namespace,
                    service=service,
                    graph_id=graph_id,
                    host=instance.get_host(),
                    port=instance.get_port(),
                    protocol=protocol,
                    path=path,
                )
                parsed = urlsplit(endpoint.url)
                if not parsed.hostname or parsed.port is None:
                    continue
                if cached is not None and (cached.host, cached.port) != (
                    endpoint.host,
                    endpoint.port,
                ):
                    self.logger.info(
                        "Switched LangGraph service %s/%s from %s:%s to %s:%s",
                        self.namespace,
                        service,
                        cached.host,
                        cached.port,
                        endpoint.host,
                        endpoint.port,
                    )
                else:
                    self.logger.debug(
                        "Selected LangGraph endpoint: service=%s graph=%s host=%s port=%s",
                        service,
                        graph_id,
                        endpoint.host,
                        endpoint.port,
                    )
                self._cache[key] = endpoint
                return endpoint
            raise LangGraphEndpointNotFoundError(
                f"No healthy LangGraph endpoint for {self.namespace}/{service} "
                f"and graph {graph_id!r}"
            )

    async def async_resolve(self, graph_id: str, service: str = "") -> LangGraphEndpoint:
        return await await_completion(asyncio.to_thread(self.resolve, graph_id, service))

    def selected_endpoint(self, graph_id: str, service: str = "") -> LangGraphEndpoint | None:
        with self._lock:
            return self._cache.get(self._endpoint_key(graph_id, service))

    def invalidate(self, graph_id: str, service: str = ""):
        with self._lock:
            self._cache.pop(self._endpoint_key(graph_id, service), None)

    def invalidate_all(self):
        with self._lock:
            self._cache.clear()

    @property
    def consumer(self):
        return self._consumer

    def close(self):
        with self._lock:
            self._closed = True
            self._cache.clear()

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
