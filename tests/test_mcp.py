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

import asyncio
import types
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import pytest

pytest.importorskip("agentscope.mcp")

from agentscope.mcp import HttpMCPConfig, MCPClient
from agentscope.message import ToolResultState
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


def instance(
    host="127.0.0.1",
    port=8080,
    protocol="mcp-streamable-http",
    *,
    version="server-v1",
    protocol_versions="2025-06-18",
):
    raw = service_pb2.Instance(
        id={"value": f"{host}:{port}"},
        host={"value": host},
        port={"value": port},
        healthy={"value": True},
        weight={"value": 100},
        protocol={"value": protocol},
        version={"value": version},
        metadata={
            "mcp-server-name": "search-mcp",
            "mcp-protocol-version": protocol_versions,
            "mcp-endpoint-path": "/sse" if protocol == "mcp-sse" else "/mcp",
        },
    )
    return ServiceInstances.new_from_discover_rsp(response_pb2.DiscoverResponse(
        service={"name": {"value": "search-mcp"}, "namespace": {"value": "default"}},
        instances=[raw],
    )).instances[0]


class FakeWatch:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FakeConsumer:
    def __init__(self, instances, contract=None):
        self.instances = list(instances)
        self.contract = contract
        self.watch_calls = []
        self.watches = []
        self.contract_calls = []
        self.reported = []

    async def async_get_healthy_instances(self, request):
        instances = list(self.instances)
        return types.SimpleNamespace(get_instances=lambda: instances)

    async def async_get_service_contract(self, request):
        self.contract_calls.append(request)
        return self.contract

    async def async_watch_service(self, request, listener):
        self.watch_calls.append((request, listener))
        watch = FakeWatch()
        self.watches.append(watch)
        return watch

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
                ServiceFeature(
                    ServiceFeatureType.MCP_TOOL,
                    "disabled",
                    status=ServiceFeatureStatus.DISABLED,
                ),
                ServiceFeature(
                    ServiceFeatureType.MCP_TOOL,
                    "enabled",
                    status=ServiceFeatureStatus.ENABLED,
                ),
                ServiceFeature(
                    ServiceFeatureType.MCP_RESOURCE,
                    "disabled",
                    status=ServiceFeatureStatus.DISABLED,
                ),
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

    async def test_pool_applies_resolver_protocol_version_filter(self):
        compatible = instance(port=8080, protocol_versions="2024-11-05,2025-06-18")
        incompatible = instance(port=8081, protocol_versions="2024-11-05")
        consumer = FakeConsumer([incompatible, compatible])
        with patch("polaris_ai.agentscope.mcp.ConsumerAPI", return_value=consumer):
            resolver = PolarisMCPResolver(
                FakeContext(FakeEngine()),
                client_factory=FakeClient,
                protocol_version="2025-06-18",
            )
            pool = PolarisMCPClientPool(resolver, "search-mcp", filter_contract=False)
            await pool.start()
            self.assertEqual([8080], [client.kwargs["port"] for client in pool.clients])
            await pool.close()

    async def test_pool_refreshes_same_endpoint_for_contract_and_version_changes(self):
        first = instance(version="server-v1")
        consumer = FakeConsumer([first], ServiceContract("default", "search-mcp"))
        with patch("polaris_ai.agentscope.mcp.ConsumerAPI", return_value=consumer):
            resolver = PolarisMCPResolver(
                FakeContext(FakeEngine()),
                client_factory=FakeClient,
                filter_contract=True,
            )
            pool = PolarisMCPClientPool(resolver, "search-mcp")
            await pool.start()
            original = pool.clients[0]
            self.assertIsNone(original.kwargs["disable_tools"])

            consumer.contract = ServiceContract(
                "default",
                "search-mcp",
                revision="contract-v2",
                service_features=[
                    ServiceFeature(
                        ServiceFeatureType.MCP_TOOL,
                        "dangerous_tool",
                        status=ServiceFeatureStatus.DISABLED,
                    )
                ],
            )
            await pool.refresh()
            contract_filtered = pool.clients[0]
            self.assertTrue(original.closed)
            self.assertEqual(["dangerous_tool"], contract_filtered.kwargs["disable_tools"])

            consumer.instances = [instance(version="server-v2")]
            await pool.refresh()
            versioned = pool.clients[0]
            self.assertTrue(contract_filtered.closed)
            self.assertEqual("server-v2", consumer.contract_calls[-1].version)
            self.assertIsNot(versioned, contract_filtered)
            await pool.close()

    async def test_pool_start_rolls_back_connected_clients_when_later_client_fails(self):
        first = instance(port=8080, protocol="mcp-sse")
        second = instance(port=8081, protocol="mcp-sse")
        consumer = FakeConsumer([first, second])
        created = []

        def factory(**kwargs):
            if kwargs["port"] == 8081:
                raise RuntimeError("connect failed")
            client = FakeClient(**kwargs)
            created.append(client)
            return client

        with patch("polaris_ai.agentscope.mcp.ConsumerAPI", return_value=consumer):
            resolver = PolarisMCPResolver(
                FakeContext(FakeEngine()),
                client_factory=factory,
            )
            pool = PolarisMCPClientPool(resolver, "search-mcp", filter_contract=False)
            with pytest.raises(RuntimeError, match="connect failed"):
                await pool.start()
        self.assertEqual((), pool.clients)
        self.assertTrue(created[0].connected)
        self.assertTrue(created[0].closed)
        self.assertTrue(consumer.watches[0].closed)

    async def test_pool_start_cancellation_closes_connected_clients_and_watch(self):
        first = instance(port=8080, protocol="mcp-sse")
        second = instance(port=8081, protocol="mcp-sse")
        consumer = FakeConsumer([first, second])
        started = asyncio.Event()
        release = asyncio.Event()
        created = []

        class BlockingClient(FakeClient):
            async def connect(self):
                self.connected = True
                if self.kwargs["port"] == 8081:
                    started.set()
                    await release.wait()

        def factory(**kwargs):
            client = BlockingClient(**kwargs)
            created.append(client)
            return client

        with patch("polaris_ai.agentscope.mcp.ConsumerAPI", return_value=consumer):
            resolver = PolarisMCPResolver(
                FakeContext(FakeEngine()),
                client_factory=factory,
            )
            pool = PolarisMCPClientPool(resolver, "search-mcp", filter_contract=False)
            task = asyncio.create_task(pool.start())
            await started.wait()
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual((), pool.clients)
        self.assertTrue(all(client.closed for client in created))
        self.assertTrue(consumer.watches[0].closed)

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

    async def test_native_client_reports_streaming_tool_after_final_chunk(self):
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
                async def stream():
                    yield types.SimpleNamespace(
                        state=ToolResultState.RUNNING,
                        is_last=False,
                    )
                    yield types.SimpleNamespace(
                        state=ToolResultState.ERROR,
                        is_last=True,
                    )

                return stream()

        tool = Tool()

        async def get_tool(_self, name):
            return tool

        with patch.object(MCPClient, "get_tool", get_tool):
            wrapped = await client.get_tool("search")
            stream = await wrapped.call(query="hello")
            self.assertEqual([], reporter.calls)
            chunks = [chunk async for chunk in stream]
        self.assertEqual(2, len(chunks))
        self.assertEqual(1, len(reporter.calls))
        self.assertFalse(reporter.calls[0]["success"])
        self.assertEqual(-1, reporter.calls[0]["ret_code"])

    async def test_native_client_reports_streaming_tool_success_after_iteration(self):
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
                async def stream():
                    yield types.SimpleNamespace(
                        state=ToolResultState.RUNNING,
                        is_last=True,
                    )

                return stream()

        tool = Tool()

        async def get_tool(_self, name):
            return tool

        with patch.object(MCPClient, "get_tool", get_tool):
            wrapped = await client.get_tool("search")
            stream = await wrapped.call(query="hello")
            self.assertEqual([], reporter.calls)
            [chunk async for chunk in stream]
        self.assertEqual(1, len(reporter.calls))
        self.assertTrue(reporter.calls[0]["success"])

    async def test_native_client_reports_streaming_tool_exception(self):
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
                async def stream():
                    yield types.SimpleNamespace(
                        state=ToolResultState.RUNNING,
                        is_last=False,
                    )
                    raise TimeoutError("timed out")

                return stream()

        tool = Tool()

        async def get_tool(_self, name):
            return tool

        with patch.object(MCPClient, "get_tool", get_tool):
            wrapped = await client.get_tool("search")
            stream = await wrapped.call(query="hello")
            with self.assertRaisesRegex(TimeoutError, "timed out"):
                [chunk async for chunk in stream]
        self.assertEqual(1, len(reporter.calls))
        self.assertFalse(reporter.calls[0]["success"])
        self.assertTrue(reporter.calls[0]["timeout"])
