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
import tempfile
import warnings
from threading import Event
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import pytest

pytest.importorskip("a2a")

from a2a.types import AgentCard, AgentInterface
from polaris.pkg.model.error import ErrorCode, SDKError
from polaris.pkg.model.server import InstanceRegisterResponse

from polaris_ai.a2a import (
    A2ATransport,
    AgentCardNotFoundError,
    PolarisA2ARegistrar,
    PolarisA2AResolver,
    PolarisA2AServerRegistration,
)
from polaris_ai.a2a._card import (
    META_A2A_VERSION,
    META_AGENT_CARD,
    META_AGENT_NAME,
    encode_card,
)
from polaris_ai.log import PolarisAILogOptions, configure_ai_logging
from tests._support import FakeContext, FakeEngine, instance, snapshot


def card(
    name="weather-agent",
    version="1.0",
    host="10.0.0.1",
    *,
    interfaces=None,
    description="Weather agent",
):
    if interfaces is None:
        interfaces = [
            AgentInterface(
                url=f"http://{host}:8080/",
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ]
    return AgentCard(
        name=name,
        description=description,
        version=version,
        supported_interfaces=interfaces,
    )


def legacy_card(
    name="weather-agent",
    version="0.3-service",
    *,
    host="10.0.0.1",
    extra_host=None,
):
    value = {
        "name": name,
        "description": "Weather",
        "version": version,
        "url": f"http://{host}:8080/",
        "protocolVersion": "0.3.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {"streaming": True},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [],
    }
    if extra_host is not None:
        value["additionalInterfaces"] = [
            {"url": f"http://{extra_host}:9090/a2a", "transport": "GRPC"}
        ]
    return value


class RegistrarTests(TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.context = FakeContext(self.engine)
        self.registrar = PolarisA2ARegistrar(self.context, service_token="service-token")

    def test_register_one_instance_with_exact_metadata_and_empty_protocol(self):
        result = self.registrar.register(card())
        self.assertEqual(1, len(result))
        self.assertEqual(result, self.registrar.registered)
        request = self.engine.register_calls[0]
        self.assertTrue(request.auto_heartbeat)
        self.assertEqual(5, request.ttl)
        self.assertEqual("service-token", request.service_token)
        self.assertEqual("weather-agent", request.service)
        self.assertEqual("10.0.0.1", request.host)
        self.assertEqual(1, request.port)
        self.assertEqual("1.0", request.version)
        self.assertEqual("", request.protocol)
        self.assertEqual(
            {META_AGENT_NAME, META_AGENT_CARD, META_A2A_VERSION},
            set(request.metadata),
        )
        self.assertEqual("1.0", request.metadata[META_A2A_VERSION])
        encoded = json.loads(request.metadata[META_AGENT_CARD])
        self.assertEqual("weather-agent", encoded["name"])
        self.assertEqual(1, len(encoded["supportedInterfaces"]))
        self.registrar.close()
        self.assertEqual((), self.registrar.registered)
        self.assertEqual("service-token", self.engine.deregister_calls[0].service_token)
        self.assertFalse(self.context.is_destroy())

    def test_multiple_interfaces_on_same_ip_still_create_one_instance(self):
        interfaces = [
            AgentInterface(
                url="http://10.0.0.1:8080/a2a",
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            ),
            AgentInterface(
                url="http://10.0.0.1:9090/a2a",
                protocol_binding="GRPC",
                protocol_version="1.0",
            ),
            AgentInterface(
                url="http://10.0.0.1:7070/a2a",
                protocol_binding="HTTP+JSON",
                protocol_version="0.3",
            ),
        ]
        result = self.registrar.register(card(interfaces=interfaces))
        self.assertEqual(1, len(result))
        self.assertEqual(1, len(self.engine.register_calls))
        self.assertEqual(
            ["JSONRPC", "GRPC", "HTTP+JSON"],
            [
                item["protocolBinding"]
                for item in json.loads(self.engine.register_calls[0].metadata[META_AGENT_CARD])[
                    "supportedInterfaces"
                ]
            ],
        )

    def test_scheme_less_and_ipv6_interface_urls_are_supported(self):
        self.registrar.register(
            card(
                interfaces=[
                    AgentInterface(
                        url="10.0.0.1:9090",
                        protocol_binding="GRPC",
                        protocol_version="1.0",
                    )
                ]
            )
        )
        self.assertEqual("10.0.0.1", self.engine.register_calls[0].host)

        ipv6 = AgentInterface(
            url="[2001:db8::1]:8443/a2a",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )
        self.registrar.register(card(interfaces=[ipv6]))
        self.assertEqual("2001:db8::1", self.engine.register_calls[1].host)

    def test_explicit_zero_callable_ports_are_rejected_before_rpc(self):
        for url in (
            "http://10.0.0.1:0/a2a",
            "10.0.0.1:0",
            "http://[2001:db8::1]:0/a2a",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "1..65535"):
                    self.registrar.register(
                        card(
                            interfaces=[
                                AgentInterface(
                                    url=url,
                                    protocol_binding="JSONRPC",
                                    protocol_version="1.0",
                                )
                            ]
                        )
                    )
        self.assertEqual([], self.engine.register_calls)

    def test_unspecified_ipv4_and_ipv6_are_rejected(self):
        for host, url in (
            ("0.0.0.0", "http://0.0.0.0:8080/a2a"),
            ("::", "http://[::]:8080/a2a"),
        ):
            with self.assertRaisesRegex(ValueError, "unspecified"):
                self.registrar.register(
                    card(
                        host=host,
                        interfaces=[
                            AgentInterface(
                                url=url,
                                protocol_binding="JSONRPC",
                                protocol_version="1.0",
                            )
                        ],
                    )
                )

    def test_registration_port_is_independent_from_card_url_port(self):
        registrar = PolarisA2ARegistrar(self.context, registration_port=18080)
        registrar.register(card(host="10.0.0.1"))
        request = self.engine.register_calls[0]
        self.assertEqual(18080, request.port)
        encoded = json.loads(request.metadata[META_AGENT_CARD])
        self.assertEqual("http://10.0.0.1:8080/", encoded["supportedInterfaces"][0]["url"])

    def test_raw_10_card_and_signatures_are_preserved(self):
        raw_card = {
            "name": "signed-agent",
            "description": "Signed",
            "version": "2.0",
            "supportedInterfaces": [
                {
                    "url": "https://10.0.0.1:8443/a2a",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0",
                }
            ],
            "signatures": [
                {
                    "protected": "protected-value",
                    "signature": "signature-value",
                }
            ],
        }
        self.registrar.register(raw_card)
        registered = self.engine.register_calls[0]
        self.assertEqual("2.0", registered.version)
        self.assertEqual(raw_card, json.loads(registered.metadata[META_AGENT_CARD]))

    def test_same_identity_replaces_tracked_registration(self):
        self.registrar.register(card(version="1.0"))
        self.registrar.register(card(version="2.0"))
        self.assertEqual(1, len(self.registrar.registered))
        self.assertEqual("2.0", self.engine.register_calls[-1].version)
        self.assertEqual("id-2", self.registrar.registered[0].instance_id)
        self.registrar.close()
        self.assertEqual(["id-2"], [item.instance_id for item in self.engine.deregister_calls])

    def test_different_registration_ports_can_hold_parallel_versions(self):
        first = PolarisA2ARegistrar(self.context, registration_port=1)
        second = PolarisA2ARegistrar(self.context, registration_port=18080)
        first.register(card(version="1.0"))
        second.register(card(version="2.0"))
        self.assertEqual([1, 18080], [item.port for item in self.engine.register_calls])
        self.assertEqual(["1.0", "2.0"], [item.version for item in self.engine.register_calls])

    def test_legacy_03_schema_is_preserved_and_metadata_version_is_canonical(self):
        self.registrar.register(
            legacy_card(extra_host="10.0.0.1"),
            a2a_version="0.3.0",
        )
        request = self.engine.register_calls[0]
        self.assertEqual("0.3", request.metadata[META_A2A_VERSION])
        encoded = json.loads(request.metadata[META_AGENT_CARD])
        self.assertEqual("http://10.0.0.1:8080/", encoded["url"])
        self.assertNotIn("supportedInterfaces", encoded)
        self.assertEqual("0.3.0", encoded["protocolVersion"])
        self.assertEqual(
            "http://10.0.0.1:9090/a2a",
            encoded["additionalInterfaces"][0]["url"],
        )
        self.assertEqual("0.3-service", request.version)

    def test_legacy_03_defaults_may_be_omitted_without_rewriting_payload(self):
        legacy = legacy_card()
        legacy.pop("preferredTransport")
        legacy.pop("protocolVersion")

        self.registrar.register(legacy, a2a_version="0.3")

        encoded = json.loads(self.engine.register_calls[0].metadata[META_AGENT_CARD])
        self.assertNotIn("preferredTransport", encoded)
        self.assertNotIn("protocolVersion", encoded)
        self.assertEqual("0.3-service", self.engine.register_calls[0].version)

    def test_protobuf_snake_case_aliases_are_accepted_without_rewriting_payload(self):
        aliased = {
            "name": "weather-agent",
            "description": "Weather",
            "version": "2.0",
            "supported_interfaces": [
                {
                    "url": "http://10.0.0.1:8080/a2a",
                    "protocol_binding": "JSONRPC",
                    "protocol_version": "1.0",
                }
            ],
        }

        self.registrar.register(aliased)

        encoded = json.loads(self.engine.register_calls[0].metadata[META_AGENT_CARD])
        self.assertEqual(aliased, encoded)

    def test_legacy_03_card_with_multiple_ip_addresses_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "same IP"):
            self.registrar.register(
                legacy_card(extra_host="10.0.0.2"),
                a2a_version="0.3",
            )

    def test_schema_versions_reject_mixed_connection_structures(self):
        modern = {
            "name": "weather-agent",
            "description": "Weather",
            "version": "1.0",
            "supportedInterfaces": [
                {
                    "url": "http://10.0.0.1:8080/a2a",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0",
                }
            ],
            "additionalInterfaces": [
                {"url": "http://10.0.0.2:9090/a2a", "transport": "GRPC"}
            ],
        }
        with self.assertRaisesRegex(ValueError, "legacy connection fields"):
            self.registrar.register(modern)

        legacy = legacy_card()
        legacy["supportedInterfaces"] = modern["supportedInterfaces"]
        with self.assertRaisesRegex(ValueError, "supportedInterfaces"):
            self.registrar.register(legacy, a2a_version="0.3")

        legacy_alias = legacy_card()
        legacy_alias["supported_interfaces"] = modern["supportedInterfaces"]
        with self.assertRaisesRegex(ValueError, "supportedInterfaces"):
            self.registrar.register(legacy_alias, a2a_version="0.3")

        modern_alias = dict(modern)
        modern_alias.pop("additionalInterfaces")
        modern_alias["additional_interfaces"] = [
            {"url": "http://10.0.0.2:9090/a2a", "transport": "GRPC"}
        ]
        with self.assertRaisesRegex(ValueError, "legacy connection fields"):
            self.registrar.register(modern_alias)

    def test_duplicate_json_field_aliases_are_rejected_before_rpc(self):
        duplicate_interfaces = {
            "name": "weather-agent",
            "description": "Weather",
            "version": "1.0",
            "supportedInterfaces": [
                {
                    "url": "http://10.0.0.1:8080/a2a",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0",
                }
            ],
            "supported_interfaces": [
                {
                    "url": "http://10.0.0.2:9090/a2a",
                    "protocolBinding": "GRPC",
                    "protocolVersion": "1.0",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "aliases"):
            self.registrar.register(duplicate_interfaces)

        duplicate_interface_field = {
            "name": "weather-agent",
            "description": "Weather",
            "version": "1.0",
            "supportedInterfaces": [
                {
                    "url": "http://10.0.0.1:8080/a2a",
                    "protocolBinding": "JSONRPC",
                    "protocol_binding": "GRPC",
                    "protocolVersion": "1.0",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "aliases"):
            self.registrar.register(duplicate_interface_field)
        self.assertEqual([], self.engine.register_calls)

    def test_invalid_card_inputs_fail_before_rpc(self):
        invalid_cards = [
            card(
                interfaces=[
                    AgentInterface(
                        url="http://10.0.0.1:8080/a2a",
                        protocol_binding="JSONRPC",
                        protocol_version="1.0",
                    ),
                    AgentInterface(
                        url="http://10.0.0.2:8080/a2a",
                        protocol_binding="JSONRPC",
                        protocol_version="1.0",
                    ),
                ]
            ),
            card(
                interfaces=[
                    AgentInterface(
                        url="http://agent.example.com:8080/a2a",
                        protocol_binding="JSONRPC",
                        protocol_version="1.0",
                    )
                ]
            ),
            card(interfaces=[]),
            card(
                interfaces=[
                    AgentInterface(
                        url="http://10.0.0.1:8080/a2a",
                        protocol_binding="",
                        protocol_version="1.0",
                    )
                ]
            ),
        ]
        for value in invalid_cards:
            with self.assertRaises(ValueError):
                self.registrar.register(value)
        with self.assertRaises(ValueError):
            self.registrar.register(legacy_card(), a2a_version="9.9")
        with self.assertRaises(ValueError):
            self.registrar.register(legacy_card(), a2a_version="1.0")
        with self.assertRaisesRegex(ValueError, "65535"):
            self.registrar.register(card(description="x" * 65536))
        self.assertEqual([], self.engine.register_calls)

    def test_registration_port_validation_rejects_bool_zero_and_overflow(self):
        for value in (True, 0, -1, 65536):
            with self.assertRaises(ValueError):
                PolarisA2ARegistrar(self.context, registration_port=value)

    def test_legacy_transport_is_one_transport_compatibility_only(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.registrar.register(card(), [A2ATransport("10.0.0.1", 8080)])
            self.assertTrue(any(item.category is DeprecationWarning for item in caught))
            self.assertEqual(1, len(self.engine.register_calls))

            with self.assertRaises(ValueError):
                self.registrar.register(
                    card(),
                    [
                        A2ATransport("10.0.0.1", 8080),
                        A2ATransport("10.0.0.1", 8081),
                    ],
                )
            with self.assertRaises(ValueError):
                self.registrar.register(card(), [A2ATransport("10.0.0.2", 8080)])

    def test_empty_service_token_and_cleanup_retry_are_preserved(self):
        registrar = PolarisA2ARegistrar(self.context, service_token="")
        registrar.register(card())
        registrar.close()
        self.assertEqual("", self.engine.register_calls[0].service_token)
        self.assertEqual("", self.engine.deregister_calls[0].service_token)

        self.engine.deregister_failures.add("id-2")
        self.registrar.register(card(version="2.0"))
        self.registrar.close()
        self.assertEqual(1, len(self.registrar.registered))
        self.engine.deregister_failures.clear()
        self.registrar.close()
        self.assertEqual((), self.registrar.registered)

    def test_closed_logger_does_not_block_cleanup_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = configure_ai_logging(
                "registrar-retry",
                PolarisAILogOptions(log_dir=directory, max_age_days=0),
            )
            registrar = PolarisA2ARegistrar(
                self.context,
                service_token="token",
                logger=manager.get_logger("a2a"),
            )
            registrar.register(card())
            self.engine.deregister_failures.add("id-1")
            registrar.close()
            self.assertEqual(1, len(registrar.registered))
            manager.close()
            self.engine.deregister_failures.clear()
            registrar.close()
            self.assertEqual((), registrar.registered)

    def test_sync_context_manager_cleanup_and_closed_state(self):
        with self.registrar as registrar:
            registrar.register(card())
        with self.assertRaises(RuntimeError):
            self.registrar.register(card())
        self.assertFalse(self.context.is_destroy())


class ResolverTests(TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.context = FakeContext(self.engine)
        self.resolver = PolarisA2AResolver(self.context)
        self.first = instance("10.0.0.1", encode_card(card()), version="1.0")
        self.second = instance(
            "10.0.0.2",
            encode_card(card(version="2.0", host="10.0.0.2")),
            version="2.0",
        )
        self.engine.snapshot = snapshot([self.first, self.second])

    def test_native_card_stickiness_and_in_place_updates(self):
        first = self.resolver.resolve("weather-agent")
        self.engine.snapshot = snapshot([self.second, self.first])
        second = self.resolver.resolve("weather-agent")
        self.assertEqual(first, second)
        self.first.instance.version.value = "1.1"
        self.first.instance.metadata[META_AGENT_CARD] = encode_card(card(version="1.1"))
        updated = self.resolver.resolve("weather-agent")
        self.assertEqual("1.1", updated.version)
        self.assertEqual("http://10.0.0.1:8080/", updated.supported_interfaces[0].url)
        self.assertTrue(all(r.exclude_offline_service for r in self.engine.discovery_calls))

    def test_legacy_03_card_uses_declared_schema_version(self):
        legacy = legacy_card(version="java")
        self.first.instance.version.value = "java"
        self.first.instance.metadata[META_AGENT_CARD] = json.dumps(legacy)
        self.first.instance.metadata[META_A2A_VERSION] = "0.3"
        resolved = self.resolver.resolve("weather-agent")
        self.assertEqual("java", resolved.version)
        self.assertEqual("http://10.0.0.1:8080/", resolved.supported_interfaces[0].url)

    def test_legacy_defaults_and_protobuf_aliases_are_resolved(self):
        legacy = legacy_card(version="legacy")
        legacy.pop("preferredTransport")
        legacy.pop("protocolVersion")
        self.first.instance.version.value = "legacy"
        self.first.instance.metadata[META_AGENT_CARD] = json.dumps(legacy)
        self.first.instance.metadata[META_A2A_VERSION] = "0.3"

        resolved = self.resolver.resolve("weather-agent")
        self.assertEqual("JSONRPC", resolved.supported_interfaces[0].protocol_binding)
        self.assertEqual("0.3.0", resolved.supported_interfaces[0].protocol_version)

        aliased = {
            "name": "weather-agent",
            "description": "Weather",
            "version": "1.0",
            "supported_interfaces": [
                {
                    "url": "http://10.0.0.1:8080/a2a",
                    "protocol_binding": "JSONRPC",
                    "protocol_version": "1.0",
                }
            ],
        }
        self.engine.snapshot = snapshot([
            instance("10.0.0.1", json.dumps(aliased), version="1.0"),
        ])
        resolved = self.resolver.resolve("weather-agent")
        self.assertEqual("JSONRPC", resolved.supported_interfaces[0].protocol_binding)
        self.assertEqual("1.0", resolved.supported_interfaces[0].protocol_version)

    def test_bad_schema_host_version_name_and_metadata_are_skipped(self):
        bad = []
        bad_card = card()

        wrong_schema = instance("10.0.0.1", encode_card(bad_card))
        wrong_schema.instance.metadata[META_A2A_VERSION] = "9.9"
        bad.append(wrong_schema)

        wrong_host = instance("10.0.0.2", encode_card(card()), version="1.0")
        wrong_host.instance.host.value = "10.0.0.3"
        bad.append(wrong_host)

        wrong_version = instance("10.0.0.2", encode_card(card()), version="2.0")
        bad.append(wrong_version)

        wrong_name = instance(
            "10.0.0.1",
            encode_card(card(name="other")),
            version="1.0",
        )
        bad.append(wrong_name)

        missing_metadata = instance("10.0.0.1", encode_card(card()))
        del missing_metadata.instance.metadata[META_A2A_VERSION]
        bad.append(missing_metadata)

        self.engine.snapshot = snapshot(bad + [self.second])
        self.assertEqual("2.0", self.resolver.resolve("weather-agent").version)

    def test_removed_unhealthy_and_isolated_instances_switch_or_fail(self):
        self.resolver.resolve("weather-agent")
        self.first.instance.healthy.value = False
        self.assertEqual("2.0", self.resolver.resolve("weather-agent").version)
        self.engine.snapshot = snapshot([instance("10.0.0.2", "broken", isolated=True)])
        with self.assertRaises(AgentCardNotFoundError):
            self.resolver.resolve("weather-agent")

    def test_sdk_failure_reuses_cache_and_cold_failure_propagates(self):
        cached = self.resolver.resolve("weather-agent")
        self.engine.discovery_error = SDKError(
            ErrorCode.ErrCodeAPIInstanceNotFound,
            "offline",
        )
        self.assertIs(cached, self.resolver.resolve("weather-agent"))
        with self.assertRaises(SDKError):
            self.resolver.resolve("other-agent")
        self.resolver.invalidate("weather-agent")
        with self.assertRaises(SDKError):
            self.resolver.resolve("weather-agent")

    def test_selected_endpoint_uses_registration_identity(self):
        self.resolver.resolve("weather-agent")
        self.assertEqual(("10.0.0.1", 8080), self.resolver.selected_endpoint("weather-agent"))

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
            await registrar.async_register(card())
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

    async def test_registration_cancellation_rolls_back_the_single_instance(self):
        entered = Event()
        release = Event()

        class BlockingEngine(FakeEngine):
            def sync_register(self, request):
                entered.set()
                release.wait(timeout=5)
                return super().sync_register(request)

        engine = BlockingEngine()
        registrar = PolarisA2ARegistrar(FakeContext(engine), service_token="token")
        task = asyncio.create_task(registrar.async_register(card()))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual((), registrar.registered)
        self.assertEqual(1, len(engine.register_calls))
        self.assertEqual(["id-1"], [item.instance_id for item in engine.deregister_calls])

    async def test_cancellation_after_worker_succeeds_rolls_back_delivered_result(self):
        engine = FakeEngine()
        registrar = PolarisA2ARegistrar(FakeContext(engine), service_token="token")
        registered = registrar.register(card())
        calls = 0

        async def completed_worker(function, *args):
            nonlocal calls
            calls += 1
            if calls == 1:
                task.cancel()
                return registered
            return function(*args)

        with patch("polaris_ai.a2a.registry.asyncio.to_thread", side_effect=completed_worker):
            task = asyncio.create_task(registrar.async_register(card()))
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual((), registrar.registered)
        self.assertEqual(["id-1"], [item.instance_id for item in engine.deregister_calls])

    async def test_cancelled_registration_keeps_same_id_replacement(self):
        class StableIdEngine(FakeEngine):
            def sync_register(self, request):
                self.register_calls.append(request)
                return InstanceRegisterResponse("stable-instance-id")

        rollback_started = asyncio.Event()
        allow_rollback = asyncio.Event()
        engine = StableIdEngine()
        registrar = PolarisA2ARegistrar(FakeContext(engine), service_token="token")
        calls = 0

        async def controlled_worker(function, *args):
            nonlocal calls
            calls += 1
            if calls == 1:
                result = function(*args)
                task.cancel()
                return result
            rollback_started.set()
            await allow_rollback.wait()
            return function(*args)

        with patch("polaris_ai.a2a.registry.asyncio.to_thread", side_effect=controlled_worker):
            task = asyncio.create_task(registrar.async_register(card(version="1.0")))
            await asyncio.wait_for(rollback_started.wait(), timeout=2)
            replacement = registrar.register(card(version="2.0"))
            allow_rollback.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)

        self.assertEqual(replacement, registrar.registered)
        self.assertEqual("2.0", engine.register_calls[-1].version)
        self.assertEqual([], engine.deregister_calls)

    async def test_server_registration_waits_for_ready_and_supports_legacy_transport(self):
        engine = FakeEngine()
        context = FakeContext(engine)
        registrar = PolarisA2ARegistrar(context, service_token="")
        ready = asyncio.Event()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            registration = PolarisA2AServerRegistration(
                registrar,
                card(),
                [A2ATransport("10.0.0.1", 8080)],
                server_ready=ready,
            )
        starting = asyncio.create_task(registration.async_start())
        await asyncio.sleep(0)
        self.assertFalse(registration.registered)
        self.assertEqual([], engine.register_calls)
        ready.set()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertIs(registration, await starting)
        self.assertTrue(registration.registered)
        await registration.async_close()
        self.assertEqual((), registrar.registered)
        self.assertEqual(1, len(engine.deregister_calls))

    async def test_server_registration_cleans_up_when_body_raises(self):
        engine = FakeEngine()
        registrar = PolarisA2ARegistrar(FakeContext(engine), service_token="token")
        registration = PolarisA2AServerRegistration(registrar, card())
        with self.assertRaises(RuntimeError):
            async with registration:
                raise RuntimeError("server failed")
        self.assertEqual((), registrar.registered)
        self.assertEqual(1, len(engine.deregister_calls))

    async def test_server_registration_partial_cleanup_retries(self):
        engine = FakeEngine()
        registrar = PolarisA2ARegistrar(FakeContext(engine), service_token="token")
        registration = PolarisA2AServerRegistration(registrar, card())
        await registration.async_start()
        engine.deregister_failures.add("id-1")
        await registration.async_close()
        self.assertEqual(1, len(registrar.registered))
        self.assertTrue(registration.registered)
        engine.deregister_failures.clear()
        await registration.async_close()
        self.assertEqual((), registrar.registered)
        self.assertFalse(registration.registered)
