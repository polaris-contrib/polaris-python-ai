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
from unittest import IsolatedAsyncioTestCase

from agentscope.message import Msg, TextBlock

from polaris_ai.agentscope import PolarisA2AAgent


class FakeResolver:
    def __init__(self, cards):
        self.cards = list(cards)
        self.resolve_calls = 0
        self.invalidated = []
        self.closed = False

    async def async_resolve(self, agent_name):
        self.resolve_calls += 1
        return self.cards.pop(0)

    def invalidate(self, agent_name):
        self.invalidated.append(agent_name)

    async def async_close(self):
        self.closed = True


class FakeAgent:
    def __init__(self, card, *, error=None, error_after_event=False):
        self.card = card
        self.error = error
        self.error_after_event = error_after_event
        self.closed = False

    async def __aenter__(self):
        return self

    async def aclose(self):
        self.closed = True

    async def reply_stream(self, inputs, *, yield_final_msg=False):
        if self.error_after_event:
            yield "event"
        if self.error is not None:
            raise self.error
        yield "event"
        yield Msg(name="assistant", role="assistant", content=[TextBlock(text="ok")])

    async def reply(self, inputs):
        return Msg(name="assistant", role="assistant", content=[TextBlock(text="replaced")])


class BlockingAgent:
    def __init__(self):
        self.started = asyncio.Event()
        self.closed = False

    async def __aenter__(self):
        return self

    async def aclose(self):
        self.closed = True

    async def reply_stream(self, inputs, *, yield_final_msg=False):
        self.started.set()
        await asyncio.sleep(30)
        yield Msg(name="assistant", role="assistant", content=[TextBlock(text="late")])


class FakeReporter:
    def __init__(self):
        self.calls = []

    async def report(self, **kwargs):
        self.calls.append(kwargs)


class PolarisA2AAgentTests(IsolatedAsyncioTestCase):
    async def test_first_call_resolves_once_and_network_error_rebuilds_client(self):
        first = FakeAgent("card-1", error=OSError("connection reset"))
        second = FakeAgent("card-2")
        agents = [first, second]
        resolver = FakeResolver(["card-1", "card-2"])
        async with PolarisA2AAgent(
            resolver,
            "weather-agent",
            agent_factory=lambda card: agents.pop(0),
        ) as agent:
            reply = await agent.reply("hello")
            self.assertEqual("replaced", reply.get_text_content())
            self.assertEqual(2, resolver.resolve_calls)
            self.assertTrue(first.closed)
            self.assertFalse(second.closed)
        self.assertTrue(second.closed)
        self.assertTrue(resolver.closed)

    async def test_business_error_does_not_switch_instance(self):
        first = FakeAgent("card-1", error=RuntimeError("business failure"))
        resolver = FakeResolver(["card-1"])
        agent = PolarisA2AAgent(resolver, "weather-agent", agent_factory=lambda card: first)
        with self.assertRaisesRegex(RuntimeError, "business failure"):
            await agent.reply("hello")
        self.assertEqual(1, resolver.resolve_calls)
        self.assertFalse(first.closed)
        await agent.aclose()

    async def test_stream_does_not_retry_after_delivering_an_event(self):
        first = FakeAgent("card-1", error=OSError("connection reset"), error_after_event=True)
        resolver = FakeResolver(["card-1"])
        agent = PolarisA2AAgent(resolver, "weather-agent", agent_factory=lambda card: first)
        events = []
        with self.assertRaises(OSError):
            async for event in agent.reply_stream("hello"):
                events.append(event)
        self.assertEqual(["event"], events)
        self.assertEqual(1, resolver.resolve_calls)
        await agent.aclose()

    async def test_explicit_invalidation_forces_next_call_to_resolve(self):
        first = FakeAgent("card-1")
        second = FakeAgent("card-2")
        agents = [first, second]
        resolver = FakeResolver(["card-1", "card-2"])
        agent = PolarisA2AAgent(resolver, "weather-agent", agent_factory=lambda card: agents.pop(0))
        await agent.reply("hello")
        await agent.invalidate()
        self.assertTrue(first.closed)
        self.assertEqual(["weather-agent"], resolver.invalidated)
        await agent.reply("hello")
        self.assertEqual(2, resolver.resolve_calls)
        await agent.aclose()

    async def test_cancellation_closes_current_client_and_resolver(self):
        first = BlockingAgent()
        resolver = FakeResolver(["card-1"])
        async with PolarisA2AAgent(
            resolver,
            "weather-agent",
            agent_factory=lambda card: first,
        ) as agent:
            task = asyncio.create_task(agent.reply("hello"))
            self.assertTrue(await asyncio.wait_for(first.started.wait(), 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(first.closed)
        self.assertTrue(resolver.closed)

    async def test_successful_reply_reports_a2a_method_and_endpoint(self):
        resolver = FakeResolver(["card-1"])
        resolver.selected_endpoint = lambda name: ("10.0.0.1", 8080)
        reporter = FakeReporter()
        agent = PolarisA2AAgent(
            resolver,
            "weather-agent",
            agent_factory=lambda card: FakeAgent(card),
            reporter=reporter,
        )
        await agent.reply("hello")
        await agent.aclose()
        self.assertEqual(1, len(reporter.calls))
        self.assertEqual("message/send", reporter.calls[0]["method"])
        self.assertEqual("a2a", reporter.calls[0]["instance_type"])
        self.assertEqual("10.0.0.1", reporter.calls[0]["host"])
        self.assertTrue(reporter.calls[0]["success"])
