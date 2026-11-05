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

"""A Polaris-routed wrapper around LangGraph's native ``RemoteGraph``."""

from __future__ import annotations

import asyncio
import time

from polaris.pkg.model.service import InstanceType

from polaris_ai._async import await_completion
from polaris_ai.log import get_ai_logger
from polaris_ai.metrics import PolarisCallReporter


def _is_timeout(error: BaseException) -> bool:
    seen = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, asyncio.TimeoutError)):
            return True
        if current.__class__.__name__ in {
            "TimeoutException",
            "ReadTimeout",
            "ConnectTimeout",
            "WriteTimeout",
            "PoolTimeout",
        }:
            return True
        current = current.__cause__ or current.__context__
    return False


class PolarisRemoteGraph:
    """Resolve a graph endpoint from Polaris and invoke LangGraph's RemoteGraph.

    Each call refreshes discovery. The native client is reused while the selected
    URL is unchanged and rebuilt after failover. The supplied resolver remains
    borrowed unless ``owns_resolver=True``.
    """

    def __init__(
        self,
        resolver,
        graph_id: str,
        *,
        service: str = "",
        graph_factory=None,
        api_key: str = "",
        headers: dict[str, str] | None = None,
        reporter=None,
        caller_service: str = "",
        labels: str = "",
        owns_resolver: bool = False,
        logger=None,
    ):
        if resolver is None:
            raise ValueError("A PolarisLangGraphResolver is required")
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise ValueError("graph_id is required")
        self.graph_id = graph_id.strip()
        self.service = service.strip() or self.graph_id
        self._resolver = resolver
        self._graph_factory = graph_factory
        self._api_key = api_key
        self._headers = dict(headers or {})
        self._owns_resolver = owns_resolver
        self._graph = None
        self._graph_url = ""
        self._closed = False
        self.logger = logger if logger is not None else get_ai_logger("langgraph")
        self._reporter = reporter
        if self._reporter is None and getattr(resolver, "consumer", None) is not None:
            self._reporter = PolarisCallReporter(
                resolver.consumer,
                getattr(resolver, "namespace", "default"),
                caller_service=caller_service,
                labels=labels,
                logger=self.logger,
            )

    def _check_open(self):
        if self._closed:
            raise RuntimeError("Polaris remote graph is closed")

    @staticmethod
    def _native_type():
        try:
            try:
                from langgraph.pregel.remote import RemoteGraph
            except ImportError:
                from langgraph.pregel import RemoteGraph
        except ImportError as error:
            raise ImportError(
                "LangGraph integration requires "
                "pip install 'polaris-python-ai[langgraph]'."
            ) from error
        return RemoteGraph

    def _select_graph(self, endpoint):
        if self._graph is not None and self._graph_url == endpoint.url:
            return self._graph, None
        factory = self._graph_factory or self._native_type()
        self.logger.debug(
            "Creating LangGraph client: graph=%s service=%s url=%s",
            self.graph_id,
            self.service,
            endpoint.url,
        )
        previous = self._graph
        self._graph = factory(
            self.graph_id,
            url=endpoint.url,
            api_key=self._api_key or None,
            headers=self._headers or None,
        )
        self._graph_url = endpoint.url
        return self._graph, previous

    @staticmethod
    def _close_sync_graph(graph):
        client = getattr(graph, "sync_client", None)
        close = getattr(client, "close", None)
        if callable(close):
            close()

    @staticmethod
    async def _close_async_graph(graph):
        client = getattr(graph, "client", None)
        close = getattr(client, "aclose", None)
        if callable(close):
            await close()
        sync_client = getattr(graph, "sync_client", None)
        sync_close = getattr(sync_client, "close", None)
        if callable(sync_close):
            await await_completion(asyncio.to_thread(sync_close))

    @property
    def remote_graph(self):
        return self._graph

    def invoke(self, input, config=None, **kwargs):
        """Execute a synchronous graph call and report its Polaris outcome."""
        self._check_open()
        endpoint = self._resolver.resolve(self.graph_id, self.service)
        started_at = time.monotonic()
        try:
            graph, previous = self._select_graph(endpoint)
            if previous is not None:
                self._close_sync_graph(previous)
            result = graph.invoke(input, config, **kwargs)
        except BaseException as error:
            self._report_sync(
                endpoint,
                started_at,
                method="langgraph.invoke",
                success=False,
                timeout=_is_timeout(error),
            )
            raise
        self._report_sync(endpoint, started_at, method="langgraph.invoke", success=True)
        return result

    async def ainvoke(self, input, config=None, **kwargs):
        """Execute an asynchronous graph call and report its Polaris outcome."""
        self._check_open()
        endpoint = await self._resolver.async_resolve(self.graph_id, self.service)
        started_at = time.monotonic()
        try:
            graph, previous = self._select_graph(endpoint)
            if previous is not None:
                await self._close_async_graph(previous)
            result = await graph.ainvoke(input, config, **kwargs)
        except BaseException as error:
            await self._report(
                endpoint,
                started_at,
                method="langgraph.invoke",
                success=False,
                timeout=_is_timeout(error),
            )
            raise
        await self._report(endpoint, started_at, method="langgraph.invoke", success=True)
        return result

    def stream(self, input, config=None, **kwargs):
        """Stream a synchronous graph call, reporting after completion or failure."""
        self._check_open()
        endpoint = self._resolver.resolve(self.graph_id, self.service)
        started_at = time.monotonic()
        try:
            graph, previous = self._select_graph(endpoint)
            if previous is not None:
                self._close_sync_graph(previous)
            yield from graph.stream(input, config, **kwargs)
        except BaseException as error:
            self._report_sync(
                endpoint,
                started_at,
                method="langgraph.stream",
                success=False,
                timeout=_is_timeout(error),
            )
            raise
        self._report_sync(endpoint, started_at, method="langgraph.stream", success=True)

    async def astream(self, input, config=None, **kwargs):
        """Asynchronously stream a graph call, reporting after completion or failure."""
        self._check_open()
        endpoint = await self._resolver.async_resolve(self.graph_id, self.service)
        started_at = time.monotonic()
        try:
            graph, previous = self._select_graph(endpoint)
            if previous is not None:
                await self._close_async_graph(previous)
            async for chunk in graph.astream(input, config, **kwargs):
                yield chunk
        except BaseException as error:
            await self._report(
                endpoint,
                started_at,
                method="langgraph.stream",
                success=False,
                timeout=_is_timeout(error),
            )
            raise
        await self._report(endpoint, started_at, method="langgraph.stream", success=True)

    def _report_sync(self, endpoint, started_at, *, method, success, timeout=False):
        if self._reporter is None:
            return
        self._reporter.report_sync(
            service=endpoint.service,
            host=endpoint.host,
            port=endpoint.port,
            method=method,
            instance_type=InstanceType.LANGGRAPH,
            started_at=started_at,
            success=success,
            timeout=timeout,
        )

    async def _report(self, endpoint, started_at, *, method, success, timeout=False):
        if self._reporter is None:
            return
        await self._reporter.report(
            service=endpoint.service,
            host=endpoint.host,
            port=endpoint.port,
            method=method,
            instance_type=InstanceType.LANGGRAPH,
            started_at=started_at,
            success=success,
            timeout=timeout,
        )

    def invalidate(self):
        """Force endpoint discovery and native-client recreation on the next call."""
        self._graph = None
        self._graph_url = ""
        self._resolver.invalidate(self.graph_id, self.service)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._close_sync_graph(self._graph)
        self._graph = None
        self._graph_url = ""
        if self._owns_resolver:
            self._resolver.close()

    async def aclose(self):
        if self._closed:
            return
        if self._owns_resolver:
            await await_completion(self._resolver.async_close())
            await self._close_async_graph(self._graph)
            self._closed = True
            self._graph = None
            self._graph_url = ""
        else:
            await self._close_async_graph(self._graph)
            self._closed = True
            self._graph = None
            self._graph_url = ""

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *_):
        self.close()

    async def __aenter__(self):
        self._check_open()
        return self

    async def __aexit__(self, *_):
        await self.aclose()
