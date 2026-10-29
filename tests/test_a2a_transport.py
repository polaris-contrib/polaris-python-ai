from unittest import IsolatedAsyncioTestCase

import pytest

pytest.importorskip("agentscope.agent")
pytest.importorskip("a2a.server.routes")

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.utils.constants import TransportProtocol
from agentscope.agent import A2AAgent
from agentscope.message import UserMsg

from examples.agentscope.a2a.provider.server import create_server
from polaris_ai.a2a import A2ATransport, PolarisA2ARegistrar, PolarisA2AResolver
from tests._support import FakeContext, FakeEngine, instance, snapshot


class A2ATransportTests(IsolatedAsyncioTestCase):
    async def test_registered_card_drives_real_jsonrpc_streaming_via_native_agentscope(self):
        app, card = create_server("weather-agent", "http://a2a.test/")
        engine = FakeEngine()
        context = FakeContext(engine)
        async with PolarisA2ARegistrar(context, service_token="token") as registrar:
            await registrar.async_register(card, [A2ATransport("a2a.test", 80)])
            metadata = engine.register_calls[0].metadata["a2a.agent.card"]
            engine.snapshot = snapshot([instance("a2a.test", metadata)])
            async with PolarisA2AResolver(context) as resolver:
                resolved = await resolver.async_resolve("weather-agent")
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), trust_env=False,
                ) as http_client:
                    client = ClientFactory(ClientConfig(
                        streaming=True, polling=False, httpx_client=http_client,
                        supported_protocol_bindings=[TransportProtocol.JSONRPC],
                    )).create(resolved)
                    async with A2AAgent(resolved, client=client) as agent:
                        reply = await agent.reply(UserMsg(name="user", content="Hello Polaris"))
                        self.assertEqual("Echo: Hello Polaris", reply.get_text_content())
        self.assertEqual((), registrar.registered)
        self.assertFalse(context.is_destroy())
