import types
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import pytest

pytest.importorskip("agentscope.mcp")

from agentscope.mcp import HttpMCPConfig, MCPClient
from polaris.pkg.model.contract import (
    ServiceContract,
    ServiceFeature,
    ServiceFeatureStatus,
    ServiceFeatureType,
)
from polaris.pkg.model.service import ServiceInstances
from polarismesh_specification.api.v1.service_manage import response_pb2, service_pb2

from polaris_ai.agentscope import PolarisMCPClientPool, PolarisMCPResolver
from polaris_ai.agentscope.mcp import PolarisMCPClient
from tests._support import FakeContext, FakeEngine


def instance(host="127.0.0.1", port=8080, protocol="mcp-streamable-http"):
    raw = service_pb2.Instance(
        id={"value": f"{host}:{port}"},
        host={"value": host},
        port={"value": port},
        healthy={"value": True},
        weight={"value": 100},
        protocol={"value": protocol},
        version={"value": "server-v1"},
        metadata={
            "mcp-server-name": "search-mcp",
            "mcp-protocol-version": "2025-06-18",
            "mcp-endpoint-path": "/sse" if protocol == "mcp-sse" else "/mcp",
        },
    )
    return ServiceInstances.new_from_discover_rsp(response_pb2.DiscoverResponse(
        service={"name": {"value": "search-mcp"}, "namespace": {"value": "default"}},
        instances=[raw],
    )).instances[0]


class FakeWatch:
    closed = False

    async def close(self):
        self.closed = True


class FakeConsumer:
    def __init__(self, instances, contract=None):
        self.instances = list(instances)
        self.contract = contract
        self.watch_calls = []
        self.reported = []

    async def async_get_healthy_instances(self, request):
        instances = list(self.instances)
        return types.SimpleNamespace(get_instances=lambda: instances)

    async def async_get_service_contract(self, request):
        return self.contract

    async def async_watch_service(self, request, listener):
        self.watch_calls.append((request, listener))
        return FakeWatch()

    async def async_unwatch_service(self, watch):
        await watch.close()

    async def async_update_service_call_result(self, result):
        self.reported.append(result)


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connected = False
        self.closed = False
        self.is_stateful = kwargs["is_stateful"]

    async def connect(self):
        self.connected = True

    async def close(self):
        self.closed = True


class FakeReporter:
    def __init__(self):
        self.calls = []

    async def report(self, **kwargs):
        self.calls.append(kwargs)


class MCPTests(IsolatedAsyncioTestCase):
    async def test_resolver_builds_native_config_and_contract_filter(self):
        contract = ServiceContract(
            "default",
            "search-mcp",
            service_features=[
                ServiceFeature(ServiceFeatureType.MCP_TOOL, "disabled", status=ServiceFeatureStatus.DISABLED),
                ServiceFeature(ServiceFeatureType.MCP_TOOL, "enabled", status=ServiceFeatureStatus.ENABLED),
                ServiceFeature(ServiceFeatureType.MCP_RESOURCE, "disabled", status=ServiceFeatureStatus.DISABLED),
            ],
        )
        consumer = FakeConsumer([instance()], contract)
        with patch("polaris_ai.agentscope.mcp.ConsumerAPI", return_value=consumer):
            resolver = PolarisMCPResolver(
                FakeContext(FakeEngine()), client_factory=FakeClient,
            )
            client = await resolver.async_create_client("search-mcp")
        self.assertEqual(["disabled"], client.kwargs["disable_tools"])
        self.assertFalse(client.is_stateful)
        config = client.kwargs["mcp_config"]
        self.assertIsInstance(config, HttpMCPConfig)
        self.assertEqual("http://127.0.0.1:8080/mcp", config.url)

    async def test_pool_reconciles_watch_updates_and_closes_removed_clients(self):
        first = instance()
        second = instance(port=8081)
        consumer = FakeConsumer([first])
        with patch("polaris_ai.agentscope.mcp.ConsumerAPI", return_value=consumer):
            resolver = PolarisMCPResolver(
                FakeContext(FakeEngine()), client_factory=FakeClient,
            )
            pool = PolarisMCPClientPool(resolver, "search-mcp", filter_contract=False)
            await pool.start()
            self.assertEqual(1, len(pool.clients))
            original = pool.clients[0]
            consumer.instances = [second]
            await pool.refresh()
            self.assertEqual(1, len(pool.clients))
            self.assertTrue(original.closed)
            self.assertEqual(8081, pool.clients[0].kwargs["port"])
            await pool.close()
            self.assertTrue(pool.clients == ())
            self.assertTrue(consumer.watch_calls)

    async def test_native_client_wraps_tool_call_metrics(self):
        reporter = FakeReporter()
        client = PolarisMCPClient(
            name="search_mcp",
            is_stateful=False,
            mcp_config=HttpMCPConfig(url="http://127.0.0.1:8080/mcp"),
            reporter=reporter,
            service="search-mcp",
            host="127.0.0.1",
            port=8080,
        )

        class Tool:
            async def call(self, **kwargs):
                return kwargs

        tool = Tool()
        async def get_tool(_self, name):
            return tool

        with patch.object(MCPClient, "get_tool", get_tool):
            wrapped = await client.get_tool("search")
            result = await wrapped.call(query="hello")
        self.assertEqual({"query": "hello"}, result)
        self.assertEqual("search", reporter.calls[0]["method"])
        self.assertEqual("mcp", reporter.calls[0]["instance_type"])
        self.assertTrue(reporter.calls[0]["success"])
