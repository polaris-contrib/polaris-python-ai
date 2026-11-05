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
from pathlib import Path

import pytest
from polaris.pkg.model.core import ServiceKey
from polaris.pkg.model.service import Instance, InstanceType, ServiceInstances
from polarismesh_specification.api.v1.service_manage import service_pb2

from polaris_ai.langgraph import (
    LangGraphEndpoint,
    LangGraphTransport,
    PolarisLangGraphConfig,
    PolarisLangGraphRegistrar,
    PolarisLangGraphResolver,
    PolarisRemoteGraph,
)
from tests._support import FakeContext, FakeEngine


def raw_instance(host, port=8123, *, graph_id="review-graph", healthy=True, isolated=False):
    raw = service_pb2.Instance()
    raw.id.value = f"{host}:{port}"
    raw.host.value = host
    raw.port.value = port
    raw.protocol.value = "http"
    raw.healthy.value = healthy
    raw.isolate.value = isolated
    raw.metadata["langgraph.graph-id"] = graph_id
    raw.metadata["langgraph.path"] = "/api"
    raw.metadata["langgraph.protocol"] = "http"
    key = ServiceKey("production", "review-service")
    return Instance(raw, key)


def discovery_snapshot(instances):
    service = service_pb2.Service()
    service.namespace.value = "production"
    service.name.value = "review-service"
    return ServiceInstances(service=service, instances=list(instances))


def test_config_reads_langgraph_specific_values_and_fallbacks():
    config = PolarisLangGraphConfig.from_env(
        {
            "POLARIS_SERVER_ADDRESS": "registry.example:8091",
            "POLARIS_AI_LANGGRAPH_GRAPH_ID": "review-graph",
            "POLARIS_AI_LANGGRAPH_SERVICE": "review-service",
            "POLARIS_AI_LANGGRAPH_NAMESPACE": "production",
            "POLARIS_AI_LANGGRAPH_PATH": "/lg",
            "POLARIS_AI_LANGGRAPH_PROTOCOL": "https",
            "POLARIS_AI_LANGGRAPH_HEADERS": "X-Tenant=demo,Authorization=token",
            "POLARIS_AI_LANGGRAPH_TTL": "9",
        }
    )
    assert config.addresses == ("registry.example:8091",)
    assert config.graph_id == "review-graph"
    assert config.service == "review-service"
    assert config.namespace == "production"
    assert config.path == "/lg"
    assert config.protocol == "https"
    assert config.headers == (
        ("X-Tenant", "demo"),
        ("Authorization", "token"),
    )
    assert config.registry.ttl == 9


def test_registrar_writes_langgraph_metadata_and_deregisters():
    engine = FakeEngine()
    context = FakeContext(engine)
    registrar = PolarisLangGraphRegistrar(
        context,
        "production",
        service_token="service-token",
    )
    registered = registrar.register(
        "review-service",
        [
            LangGraphTransport(
                "10.0.0.8",
                8123,
                "/api",
                graph_id="review-graph",
            )
        ],
        version="1.2.3",
    )
    request = engine.register_calls[0]
    assert request.metadata == {
        "langgraph.graph-id": "review-graph",
        "langgraph.path": "/api",
        "langgraph.protocol": "http",
    }
    assert request.protocol == "http"
    assert request.version == "1.2.3"
    assert request.auto_heartbeat is True
    assert registered[0].instance_id == "id-1"

    registrar.close()
    assert registrar.registered == ()
    assert engine.deregister_calls[0].instance_id == "id-1"


def test_resolver_selects_matching_healthy_instance_and_keeps_sticky_host():
    engine = FakeEngine()
    context = FakeContext(engine)
    engine.snapshot = discovery_snapshot(
        [
            raw_instance("10.0.0.9", graph_id="other-graph"),
            raw_instance("10.0.0.8", healthy=False),
            raw_instance("10.0.0.7"),
        ]
    )
    resolver = PolarisLangGraphResolver(context, "production")
    endpoint = resolver.resolve("review-graph", "review-service")
    assert endpoint == LangGraphEndpoint(
        namespace="production",
        service="review-service",
        graph_id="review-graph",
        host="10.0.0.7",
        port=8123,
        protocol="http",
        path="/api",
    )
    assert endpoint.url == "http://10.0.0.7:8123/api"

    engine.snapshot = discovery_snapshot(
        [
            raw_instance("10.0.0.6"),
            raw_instance("10.0.0.7"),
        ]
    )
    assert resolver.resolve("review-graph", "review-service").host == "10.0.0.7"
    assert resolver.selected_endpoint("review-graph", "review-service") == endpoint


class RecordingReporter:
    def __init__(self):
        self.sync_calls = []
        self.async_calls = []

    def report_sync(self, **kwargs):
        self.sync_calls.append(kwargs)

    async def report(self, **kwargs):
        self.async_calls.append(kwargs)


class FakeResolver:
    namespace = "production"
    consumer = object()

    def __init__(self):
        self.endpoint = LangGraphEndpoint(
            "production",
            "review-service",
            "review-graph",
            "10.0.0.7",
            8123,
            "http",
            "/api",
        )
        self.invalidated = []

    def resolve(self, graph_id, service=""):
        assert (graph_id, service) == ("review-graph", "review-service")
        return self.endpoint

    async def async_resolve(self, graph_id, service=""):
        return self.resolve(graph_id, service)

    def invalidate(self, graph_id, service=""):
        self.invalidated.append((graph_id, service))


class FakeNativeGraph:
    def __init__(self):
        self.calls = []

    def invoke(self, input, config=None, **kwargs):
        self.calls.append(("invoke", input, config, kwargs))
        return {"ok": True}

    async def ainvoke(self, input, config=None, **kwargs):
        self.calls.append(("ainvoke", input, config, kwargs))
        return {"ok": True}

    def stream(self, input, config=None, **kwargs):
        self.calls.append(("stream", input, config, kwargs))
        yield {"step": 1}

    async def astream(self, input, config=None, **kwargs):
        self.calls.append(("astream", input, config, kwargs))
        yield {"step": 1}


def test_failover_closes_the_previous_sync_client():
    resolver = FakeResolver()
    reporter = RecordingReporter()
    clients = []

    class Client:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class Native(FakeNativeGraph):
        def __init__(self):
            super().__init__()
            self.sync_client = Client()
            clients.append(self)

    graph = PolarisRemoteGraph(
        resolver,
        "review-graph",
        service="review-service",
        graph_factory=lambda *_args, **_kwargs: Native(),
        reporter=reporter,
    )
    graph.invoke({"input": "one"})
    resolver.endpoint = LangGraphEndpoint(
        "production",
        "review-service",
        "review-graph",
        "10.0.0.8",
        8123,
        "http",
        "/api",
    )
    graph.invoke({"input": "two"})
    assert clients[0].sync_client.closed is True
    assert clients[1].sync_client.closed is False


def test_remote_graph_routes_native_client_and_reports_sync_call():
    resolver = FakeResolver()
    reporter = RecordingReporter()
    native = FakeNativeGraph()
    calls = []

    def factory(graph_id, **kwargs):
        calls.append((graph_id, kwargs))
        return native

    graph = PolarisRemoteGraph(
        resolver,
        "review-graph",
        service="review-service",
        graph_factory=factory,
        reporter=reporter,
        headers={"X-Test": "1"},
    )
    result = graph.invoke({"input": "hello"}, {"configurable": {"thread_id": "t1"}})
    assert result == {"ok": True}
    assert calls == [
        (
            "review-graph",
            {
                "url": "http://10.0.0.7:8123/api",
                "api_key": None,
                "headers": {"X-Test": "1"},
            },
        )
    ]
    assert reporter.sync_calls[0]["instance_type"] == InstanceType.LANGGRAPH
    assert reporter.sync_calls[0]["method"] == "langgraph.invoke"
    assert reporter.sync_calls[0]["success"] is True
    assert list(graph.stream({"input": "next"})) == [{"step": 1}]
    assert len(calls) == 1
    assert reporter.sync_calls[-1]["method"] == "langgraph.stream"
    assert reporter.sync_calls[-1]["success"] is True

    graph.invalidate()
    assert resolver.invalidated == [("review-graph", "review-service")]


def test_native_langgraph_remote_graph_type_is_importable():
    native = PolarisRemoteGraph._native_type()
    graph = native("review-graph", url="http://127.0.0.1:8123")
    assert graph.assistant_id == "review-graph"


def test_remote_graph_reports_async_success_and_timeout():
    async def run():
        resolver = FakeResolver()
        reporter = RecordingReporter()
        native = FakeNativeGraph()
        graph = PolarisRemoteGraph(
            resolver,
            "review-graph",
            service="review-service",
            graph_factory=lambda *_args, **_kwargs: native,
            reporter=reporter,
        )
        assert await graph.ainvoke({"input": "hello"}) == {"ok": True}
        chunks = [chunk async for chunk in graph.astream({"input": "next"})]
        assert chunks == [{"step": 1}]
        assert [call["success"] for call in reporter.async_calls] == [True, True]

        async def timeout(*_args, **_kwargs):
            raise asyncio.TimeoutError("timed out")

        native.ainvoke = timeout
        with pytest.raises(asyncio.TimeoutError):
            await graph.ainvoke({"input": "late"})
        assert reporter.async_calls[-1]["success"] is False
        assert reporter.async_calls[-1]["timeout"] is True

    asyncio.run(run())


def test_all_public_modules_share_the_single_distribution_version():
    import polaris_ai
    import polaris_ai.a2a
    import polaris_ai.agentscope
    import polaris_ai.langgraph

    root = Path(__file__).resolve().parents[1]
    version = polaris_ai.__version__
    assert version
    assert polaris_ai.a2a.__version__ == version
    assert polaris_ai.agentscope.__version__ == version
    assert polaris_ai.langgraph.__version__ == version
    assert (root / "src/polaris_ai/_version.py").exists()
    assert not (root / "src/polaris_ai/langgraph/_version.py").exists()
