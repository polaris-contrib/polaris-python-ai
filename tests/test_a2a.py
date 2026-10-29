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
import json
from threading import Event
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import pytest

pytest.importorskip("a2a")

from a2a.types import AgentCard, AgentInterface
from polaris.pkg.model.error import ErrorCode, SDKError

from polaris_ai.a2a import (
    A2ATransport,
    AgentCardNotFoundError,
    PolarisA2ARegistrar,
    PolarisA2AResolver,
)
from polaris_ai.a2a._card import decode_card, encode_card
from tests._support import FakeContext, FakeEngine, instance, snapshot


def card(name="weather-agent", version="1.0", host="10.0.0.1", description="Weather agent"):
    return AgentCard(
        name=name, description=description, version=version,
        supported_interfaces=[AgentInterface(
            url=f"http://{host}:8080/", protocol_binding="JSONRPC", protocol_version="1.0",
        )],
    )


class RegistrarTests(TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.context = FakeContext(self.engine)
        self.registrar = PolarisA2ARegistrar(self.context, service_token="service-token")

    def test_register_transports_has_java_metadata_token_and_heartbeat(self):
        result = self.registrar.register(card(), [
            A2ATransport("10.0.0.1", 8080),
            A2ATransport("10.0.0.1", 8443, "HTTP+JSON", "/api", True),
        ])
        self.assertEqual(2, len(result))
        self.assertEqual(result, self.registrar.registered)
        first, second = self.engine.register_calls
        self.assertTrue(first.auto_heartbeat)
        self.assertEqual(5, first.ttl)
        self.assertEqual("service-token", first.service_token)
        self.assertEqual("weather-agent", first.service)
        self.assertEqual("1.0", first.version)
        self.assertEqual("http", first.protocol)
        self.assertEqual("https", second.protocol)
        self.assertEqual("HTTP+JSON", second.metadata["a2a.transport"])
        self.assertEqual("/api", second.metadata["a2a.path"])
        self.assertEqual("weather-agent", first.metadata["ai-agent-name"])
        self.assertEqual(card(), decode_card(first.metadata["a2a.agent.card"]))
        self.registrar.close()
        self.assertEqual((), self.registrar.registered)
        self.assertEqual(["service-token", "service-token"],
                         [r.service_token for r in self.engine.deregister_calls])
        self.assertFalse(self.context.is_destroy())

    def test_partial_failure_rolls_back_only_current_call(self):
        self.registrar.register(card(), [A2ATransport("10.0.0.3", 8080)])
        self.engine.register_failure_at = 3
        with self.assertRaisesRegex(RuntimeError, "registration failed"):
            self.registrar.register(card(), [
                A2ATransport("10.0.0.1", 8080), A2ATransport("10.0.0.2", 8080),
            ])
        self.assertEqual(["id-2"], [r.instance_id for r in self.engine.deregister_calls])
        self.assertEqual(["id-1"], [r.instance_id for r in self.registrar.registered])

    def test_failed_rollback_and_close_can_be_retried(self):
        self.engine.register_failure_at = 2
        self.engine.deregister_failures.add("id-1")
        with self.assertRaises(RuntimeError):
            self.registrar.register(card(), [
                A2ATransport("10.0.0.1", 8080), A2ATransport("10.0.0.2", 8080),
            ])
        self.assertEqual(1, len(self.registrar.registered))
        self.registrar.close()
        self.assertEqual(1, len(self.registrar.registered))
        self.engine.deregister_failures.clear()
        self.registrar.close()
        self.registrar.close()
        self.assertEqual((), self.registrar.registered)
        self.assertEqual(3, len(self.engine.deregister_calls))
        self.assertFalse(self.context.is_destroy())

    def test_invalid_transport_and_oversize_card_fail_before_rpc(self):
        with self.assertRaises(ValueError):
            self.registrar.register(card(), [])
        with self.assertRaises(ValueError):
            self.registrar.register(card(), [A2ATransport("10.0.0.1", 8080),
                                            A2ATransport("10.0.0.2", 65536)])
        with self.assertRaisesRegex(ValueError, "65535"):
            self.registrar.register(card(description="x" * 65536), [A2ATransport("10.0.0.1", 8080)])
        self.assertEqual([], self.engine.register_calls)

    def test_sync_context_manager_cleanup_and_closed_state(self):
        with self.registrar as registrar:
            registrar.register(card(), [A2ATransport("10.0.0.1", 8080)])
        with self.assertRaises(RuntimeError):
            self.registrar.register(card(), [A2ATransport("10.0.0.1", 8080)])
        self.assertFalse(self.context.is_destroy())


class ResolverTests(TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.context = FakeContext(self.engine)
        self.resolver = PolarisA2AResolver(self.context)
        self.first = instance("10.0.0.1", encode_card(card()))
        self.second = instance("10.0.0.2", encode_card(card(version="2.0", host="10.0.0.2")))
        self.engine.snapshot = snapshot([self.first, self.second])

    def test_native_card_stickiness_and_in_place_updates(self):
        first = self.resolver.resolve("weather-agent")
        self.engine.snapshot = snapshot([self.second, self.first])
        second = self.resolver.resolve("weather-agent")
        self.assertEqual(first, second)
        self.first.instance.metadata["a2a.agent.card"] = encode_card(card(version="1.1"))
        updated = self.resolver.resolve("weather-agent")
        self.assertEqual("1.1", updated.version)
        self.assertEqual("http://10.0.0.1:8080/", updated.supported_interfaces[0].url)
        self.assertTrue(all(r.exclude_offline_service for r in self.engine.discovery_calls))

    def test_removed_or_unhealthy_or_invalid_sticky_instance_switches(self):
        self.resolver.resolve("weather-agent")
        self.first.instance.healthy.value = False
        self.assertEqual("2.0", self.resolver.resolve("weather-agent").version)
        self.second.instance.metadata["a2a.agent.card"] = "broken"
        self.first.instance.healthy.value = True
        self.assertEqual("1.0", self.resolver.resolve("weather-agent").version)
        self.engine.snapshot = snapshot([self.second])
        with self.assertRaises(AgentCardNotFoundError):
            self.resolver.resolve("weather-agent")

    def test_sdk_failure_reuses_cache_and_cold_failure_propagates(self):
        cached = self.resolver.resolve("weather-agent")
        self.engine.discovery_error = SDKError(ErrorCode.ErrCodeAPIInstanceNotFound, "offline")
        self.assertIs(cached, self.resolver.resolve("weather-agent"))
        with self.assertRaises(SDKError):
            self.resolver.resolve("other-agent")
        self.resolver.invalidate("weather-agent")
        with self.assertRaises(SDKError):
            self.resolver.resolve("weather-agent")

    def test_successful_empty_discovery_does_not_use_stale_card(self):
        self.resolver.resolve("weather-agent")
        self.engine.snapshot = snapshot([])
        with self.assertRaises(AgentCardNotFoundError):
            self.resolver.resolve("weather-agent")

    def test_malformed_json_proto_mismatch_name_and_isolation_are_skipped(self):
        invalid = [
            instance("1", ""), instance("2", "[]"), instance("3", "null"),
            instance("4", '{"name":"weather-agent","supportedInterfaces":"invalid"}'),
            instance("5", encode_card(card(name="other"))),
            instance("6", encode_card(card()), isolated=True),
            instance("7", '{"name":"weather-agent"}'),
        ]
        self.engine.snapshot = snapshot(invalid + [self.second])
        self.assertEqual("2.0", self.resolver.resolve("weather-agent").version)

    def test_java_legacy_card_uses_official_compatibility_parser(self):
        legacy = {
            "name": "weather-agent", "description": "Weather", "version": "java",
            "url": "http://10.0.0.1:8080/", "protocolVersion": "0.3.0",
            "preferredTransport": "JSONRPC", "capabilities": {"streaming": True},
            "defaultInputModes": ["text"], "defaultOutputModes": ["text"], "skills": [],
        }
        self.first.instance.metadata["a2a.agent.card"] = json.dumps(legacy)
        resolved = self.resolver.resolve("weather-agent")
        self.assertIsInstance(resolved, AgentCard)
        self.assertEqual("0.3.0", resolved.supported_interfaces[0].protocol_version)
        self.assertEqual(legacy["url"], resolved.supported_interfaces[0].url)

    def test_close_preserves_context_and_rejects_queries(self):
        self.resolver.resolve("weather-agent")
        self.resolver.close()
        self.assertFalse(self.context.is_destroy())
        with self.assertRaises(RuntimeError):
            self.resolver.resolve("weather-agent")


class AsyncA2ATests(IsolatedAsyncioTestCase):
    async def test_async_context_manager_and_native_agentscope_agent(self):
        pytest.importorskip("agentscope.agent")
        from agentscope.agent import A2AAgent

        engine = FakeEngine()
        context = FakeContext(engine)
        engine.snapshot = snapshot([instance("10.0.0.1", encode_card(card()))])
        async with PolarisA2ARegistrar(context, service_token="token") as registrar:
            await registrar.async_register(card(), [A2ATransport("10.0.0.1", 8080)])
            async with PolarisA2AResolver(context) as resolver:
                resolved = await resolver.async_resolve("weather-agent")

                class Client:
                    closed = False

                    async def close(self):
                        self.closed = True

                client = Client()
                async with A2AAgent(resolved, client=client) as remote:
                    self.assertEqual("weather-agent", remote.name)
                self.assertTrue(client.closed)
        self.assertEqual((), registrar.registered)
        self.assertFalse(context.is_destroy())

    async def test_registration_cancellation_waits_for_in_flight_rpc_and_rolls_back(self):
        entered = Event()
        release = Event()

        class BlockingEngine(FakeEngine):
            def sync_register(self, request):
                entered.set()
                release.wait(timeout=5)
                return super().sync_register(request)

        engine = BlockingEngine()
        registrar = PolarisA2ARegistrar(FakeContext(engine), service_token="token")
        task = asyncio.create_task(registrar.async_register(card(), [
            A2ATransport("10.0.0.1", 8080), A2ATransport("10.0.0.2", 8080),
        ]))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual((), registrar.registered)
        self.assertEqual(1, len(engine.register_calls))
        self.assertEqual(["id-1"], [r.instance_id for r in engine.deregister_calls])

    async def test_cancellation_after_worker_succeeds_rolls_back_delivered_result(self):
        engine = FakeEngine()
        registrar = PolarisA2ARegistrar(FakeContext(engine), service_token="token")
        registered = registrar.register(card(), [A2ATransport("10.0.0.1", 8080)])

        calls = 0

        async def completed_worker(function, *args):
            nonlocal calls
            calls += 1
            if calls == 1:
                task.cancel()
                return registered
            return function(*args)

        with patch("polaris_ai.a2a.registry.asyncio.to_thread", side_effect=completed_worker):
            task = asyncio.create_task(registrar.async_register(card(), [A2ATransport("10.0.0.1", 8080)]))
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual((), registrar.registered)
        self.assertEqual(["id-1"], [r.instance_id for r in engine.deregister_calls])
