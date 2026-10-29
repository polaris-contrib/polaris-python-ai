"""Polaris discovery and contract filtering for AgentScope MCP clients."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import types

from pydantic import PrivateAttr

try:
    from agentscope.mcp import HttpMCPConfig, MCPClient
    from agentscope.message import ToolResultState
except ImportError as error:
    raise ImportError(
        "Polaris MCP support requires pip install 'polaris-python-ai[mcp]'."
    ) from error

from polaris.api.consumer import ConsumerAPI
from polaris.pkg.model.contract import (
    GetServiceContractRequest,
    ServiceFeatureStatus,
    ServiceFeatureType,
)
from polaris.pkg.model.service import GetHealthyInstancesRequest, GetInstancesRequest, InstanceType

from polaris_ai.metrics import PolarisCallReporter

logger = logging.getLogger(__name__)

MCP_STREAMABLE_HTTP = "mcp-streamable-http"
MCP_SSE = "mcp-sse"
MCP_PROTOCOLS = (MCP_STREAMABLE_HTTP, MCP_SSE)
MCP_SERVER_NAME = "mcp-server-name"
MCP_PROTOCOL_VERSION = "mcp-protocol-version"
MCP_ENDPOINT_PATH = "mcp-endpoint-path"
MCP_SCHEME = "mcp-scheme"


def _client_name(service: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]", "-", service.strip())
    return name or "polaris-mcp"


def _versions(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def mcp_endpoint(instance, scheme: str = "") -> tuple[str, int, str]:
    """Build the AgentScope MCP URL, port and native protocol for an instance."""
    protocol = instance.get_protocol()
    if protocol not in MCP_PROTOCOLS:
        raise ValueError(f"Unsupported MCP protocol {protocol!r}")
    selected_scheme = scheme or instance.get_metadata().get(MCP_SCHEME, "http")
    if selected_scheme not in ("http", "https"):
        raise ValueError("MCP scheme must be http or https")
    path = instance.get_metadata().get(MCP_ENDPOINT_PATH) or (
        "/sse" if protocol == MCP_SSE else "/mcp"
    )
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise ValueError("MCP endpoint path must be an absolute path without query or fragment")
    host = instance.get_host()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{selected_scheme}://{host}:{instance.get_port()}{path}", instance.get_port(), protocol


class PolarisMCPClient(MCPClient):
    """AgentScope MCP client that reports successful and failed Tool calls."""

    _polaris_reporter = PrivateAttr(default=None)
    _polaris_service = PrivateAttr(default="")
    _polaris_host = PrivateAttr(default="")
    _polaris_port = PrivateAttr(default=0)

    def __init__(self, *, reporter=None, service: str, host: str, port: int, **data):
        super().__init__(**data)
        self._polaris_reporter = reporter
        self._polaris_service = service
        self._polaris_host = host
        self._polaris_port = port

    async def get_tool(self, name: str):
        tool = await super().get_tool(name)
        reporter = self._polaris_reporter
        if reporter is None:
            return tool
        original = tool.call

        async def reported_call(_tool, **kwargs):
            started_at = time.monotonic()
            try:
                result = await original(**kwargs)
            except BaseException as error:
                await reporter.report(
                    service=self._polaris_service,
                    host=self._polaris_host,
                    port=self._polaris_port,
                    method=name,
                    instance_type=InstanceType.MCP,
                    started_at=started_at,
                    success=False,
                    timeout=isinstance(error, (asyncio.TimeoutError, TimeoutError)),
                )
                raise
            success = getattr(result, "state", None) != ToolResultState.ERROR
            await reporter.report(
                service=self._polaris_service,
                host=self._polaris_host,
                port=self._polaris_port,
                method=name,
                instance_type=InstanceType.MCP,
                started_at=started_at,
                success=success,
                ret_code=None if success else -1,
            )
            return result

        tool.call = types.MethodType(reported_call, tool)
        return tool


class PolarisMCPResolver:
    """Resolve MCP instances and compose native AgentScope MCP clients."""

    def __init__(
        self,
        sdk_context,
        namespace: str = "default",
        *,
        client_factory=PolarisMCPClient,
        caller_service: str = "",
        labels: str = "",
        protocol_version: str = "",
        scheme: str = "",
        timeout: float = 30.0,
        filter_contract: bool = True,
        headers: dict[str, str] | None = None,
    ):
        if sdk_context is None or sdk_context.is_destroy():
            raise ValueError("An active SDKContext is required")
        self.namespace = namespace.strip() or "default"
        self.consumer = ConsumerAPI(sdk_context)
        self.client_factory = client_factory
        self.caller_service = caller_service
        self.labels = labels
        self.protocol_version = protocol_version
        self.scheme = scheme
        self.timeout = timeout
        self.filter_contract = filter_contract
        self.headers = dict(headers or {})

    async def async_candidates(self, service: str, *, protocol_version: str = ""):
        if not isinstance(service, str) or not service.strip():
            raise ValueError("MCP service is required")
        response = await self.consumer.async_get_healthy_instances(
            GetHealthyInstancesRequest(
                namespace=self.namespace,
                service=service.strip(),
                exclude_offline_service=True,
            )
        )
        result = []
        requested = _versions(protocol_version)
        for instance in [] if response is None else response.get_instances():
            if not instance.is_healthy() or instance.is_isolated():
                continue
            if instance.get_protocol() not in MCP_PROTOCOLS:
                continue
            versions = _versions(instance.get_metadata().get(MCP_PROTOCOL_VERSION, ""))
            if requested and versions and not requested.intersection(versions):
                continue
            result.append(instance)
        return result

    async def async_disabled_tools(self, service: str, *, protocol: str = "", version: str = ""):
        try:
            contract = await self.consumer.async_get_service_contract(
                GetServiceContractRequest(
                    namespace=self.namespace,
                    service=service,
                    protocol=protocol,
                    version=version,
                )
            )
        except Exception as error:
            logger.warning("MCP contract unavailable for %s; skipping Tool filtering: %s", service, error)
            return []
        if contract is None:
            return []
        return [
            feature.name
            for feature in contract.service_features
            if feature.type == ServiceFeatureType.MCP_TOOL
            and feature.status == ServiceFeatureStatus.DISABLED
        ]

    async def async_create_client(
        self,
        service: str,
        *,
        protocol_version: str | None = None,
        scheme: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        filter_contract: bool | None = None,
    ):
        instances = await self.async_candidates(
            service,
            protocol_version=(
                self.protocol_version if protocol_version is None else protocol_version
            ),
        )
        if not instances:
            raise LookupError(f"No healthy MCP instance for {self.namespace}/{service}")
        return await self.async_client_for_instance(
            service,
            instances[0],
            scheme=self.scheme if scheme is None else scheme,
            headers=self.headers if headers is None else headers,
            timeout=self.timeout if timeout is None else timeout,
            filter_contract=(
                self.filter_contract if filter_contract is None else filter_contract
            ),
        )

    async def async_client_for_instance(
        self,
        service: str,
        instance,
        *,
        scheme: str = "",
        headers: dict[str, str] | None = None,
        timeout: float | None = 30.0,
        filter_contract: bool = True,
    ):
        url, port, protocol = mcp_endpoint(instance, scheme)
        disabled = (
            await self.async_disabled_tools(
                service,
                protocol=protocol,
                version=instance.get_version(),
            )
            if filter_contract else []
        )
        reporter = PolarisCallReporter(
            self.consumer,
            self.namespace,
            caller_service=self.caller_service,
            labels=self.labels,
        )
        client = self.client_factory(
            name=_client_name(service),
            is_stateful=protocol == MCP_SSE,
            mcp_config=HttpMCPConfig(url=url, headers=headers, timeout=timeout),
            disable_tools=disabled or None,
            reporter=reporter,
            service=service,
            host=instance.get_host(),
            port=port,
        )
        if client.is_stateful:
            await client.connect()
        return client


class PolarisMCPClientPool:
    """Maintain one MCP client per watched healthy Polaris instance."""

    def __init__(self, resolver: PolarisMCPResolver, service: str, **client_options):
        self.resolver = resolver
        self.service = service
        self.client_options = {
            "scheme": resolver.scheme,
            "headers": resolver.headers,
            "timeout": resolver.timeout,
            "filter_contract": resolver.filter_contract,
            **client_options,
        }
        self._clients: dict[tuple[str, str], MCPClient] = {}
        self._watch = None
        self._refresh_event = asyncio.Event()
        self._task = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._cursor = 0

    @property
    def clients(self):
        return tuple(self._clients.values())

    async def start(self):
        """Load clients once and subscribe to service cache lifecycle events."""
        if self._task is not None:
            return self
        loop = asyncio.get_running_loop()

        def changed(_event):
            loop.call_soon_threadsafe(self._refresh_event.set)

        self._watch = await self.resolver.consumer.async_watch_service(
            GetInstancesRequest(
                namespace=self.resolver.namespace,
                service=self.service,
                exclude_offline_service=True,
            ),
            changed,
        )
        try:
            await self.refresh()
        except BaseException:
            await self.resolver.consumer.async_unwatch_service(self._watch)
            self._watch = None
            raise
        self._task = asyncio.create_task(self._run(), name=f"polaris-mcp-pool-{self.service}")
        return self

    async def _run(self):
        while not self._closed:
            await self._refresh_event.wait()
            if self._closed:
                return
            self._refresh_event.clear()
            try:
                await self.refresh()
            except Exception as error:
                logger.warning("Failed to refresh MCP pool for %s: %s", self.service, error)

    async def refresh(self):
        """Reconcile current healthy instances with the native client pool."""
        async with self._lock:
            if self._closed:
                return
            instances = await self.resolver.async_candidates(self.service)
            desired = {}
            for instance in instances:
                try:
                    url, _port, protocol = mcp_endpoint(
                        instance, self.client_options.get("scheme", "")
                    )
                except ValueError as error:
                    logger.warning("Skipping invalid MCP instance %s: %s", instance.get_id(), error)
                    continue
                desired[(url, protocol)] = (instance, url)
            for key in tuple(self._clients):
                if key not in desired:
                    await self._clients.pop(key).close()
            for key, (instance, _url) in desired.items():
                if key not in self._clients:
                    self._clients[key] = await self.resolver.async_client_for_instance(
                        self.service, instance, **self.client_options,
                    )

    def choose_client(self):
        """Return the next connected client using round-robin selection."""
        clients = list(self._clients.values())
        if not clients:
            raise LookupError(f"No MCP client is available for {self.service}")
        self._cursor %= len(clients)
        client = clients[self._cursor]
        self._cursor = (self._cursor + 1) % len(clients)
        return client

    async def close(self):
        """Stop watch updates and close all owned MCP clients."""
        if self._closed:
            return
        self._closed = True
        self._refresh_event.set()
        task, self._task = self._task, None
        if task is not None:
            await task
        if self._watch is not None:
            await self.resolver.consumer.async_unwatch_service(self._watch)
            self._watch = None
        clients, self._clients = self._clients, {}
        for client in clients.values():
            try:
                await client.close()
            except Exception as error:
                logger.warning("Failed to close MCP client for %s: %s", self.service, error)

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        await self.close()
