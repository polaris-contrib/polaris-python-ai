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

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

import pytest

pytest.importorskip("agentscope.middleware")

from agentscope.skill import Skill, SkillLoaderBase
from agentscope.tool import Toolkit
from polaris.pkg.model.skill import (
    SkillDownloadResponse,
    SkillListResponse,
    SkillResource,
    SkillVersionInfo,
)

from polaris_ai.agentscope import PolarisDynamicSkillMiddleware, PolarisSkillLoader
from tests._support import FakeContext, FakeEngine, skill_zip


class DynamicSkillMiddlewareTests(IsolatedAsyncioTestCase):
    async def test_multiple_middlewares_share_one_toolkit_snapshot(self):
        class FixedLoader(SkillLoaderBase):
            def __init__(self):
                self.skills = []

            async def list_skills(self):
                return list(self.skills)

        def skill(description):
            return Skill(
                name="weather",
                description=description,
                dir=f"/tmp/{description}",
                markdown=description,
                updated_at=0,
            )

        loader = FixedLoader()
        toolkit = Toolkit(skills_or_loaders=[loader])
        first = PolarisDynamicSkillMiddleware(loader)
        second = PolarisDynamicSkillMiddleware(loader)

        async def next_handler():
            yield "reply"

        agent = SimpleNamespace(toolkit=toolkit)
        loader.skills = [skill("version-v1")]
        [event async for event in first.on_reply(agent, {}, next_handler)]
        self.assertIn("version-v1", await toolkit.get_skill_instructions())

        loader.skills = [skill("version-v2")]
        [event async for event in second.on_reply(agent, {}, next_handler)]
        prompt = await toolkit.get_skill_instructions()
        self.assertIn("version-v2", prompt)
        self.assertNotIn("version-v1", prompt)

    async def test_refreshes_skills_before_reply(self):
        engine = FakeEngine()
        context = FakeContext(engine)
        engine.pages = [
            SkillListResponse(
                1,
                [SkillResource(name="weather", version_info=SkillVersionInfo(active_version="v1"))],
            )
        ]
        engine.downloads[("weather", "v1")] = SkillDownloadResponse(
            version="v1", content_type="application/zip", data=skill_zip(name="weather")
        )
        async with PolarisSkillLoader(context) as loader:
            middleware = PolarisDynamicSkillMiddleware(loader)

            async def next_handler():
                yield "reply"

            events = [event async for event in middleware.on_reply(None, {}, next_handler)]
            self.assertEqual(["reply"], events)
            self.assertEqual(["weather"], [skill.name for skill in middleware.last_skills])

    async def test_refresh_failure_does_not_block_reply(self):
        engine = FakeEngine()
        context = FakeContext(engine)
        async with PolarisSkillLoader(context) as loader:
            middleware = PolarisDynamicSkillMiddleware(loader)

            async def next_handler():
                yield "reply"

            events = [event async for event in middleware.on_reply(None, {}, next_handler)]
            self.assertEqual(["reply"], events)
            self.assertEqual((), middleware.last_skills)

    async def test_refresh_failure_falls_back_in_real_toolkit(self):
        engine = FakeEngine()
        context = FakeContext(engine)
        engine.pages = [
            SkillListResponse(
                1,
                [SkillResource(name="weather", version_info=SkillVersionInfo(active_version="v1"))],
            )
        ]
        engine.downloads[("weather", "v1")] = SkillDownloadResponse(
            version="v1", content_type="application/zip", data=skill_zip(name="weather")
        )
        async with PolarisSkillLoader(context) as loader:
            toolkit = Toolkit(skills_or_loaders=[loader])
            agent = SimpleNamespace(toolkit=toolkit)
            middleware = PolarisDynamicSkillMiddleware(loader)

            async def next_handler():
                yield "reply"

            [event async for event in middleware.on_reply(agent, {}, next_handler)]
            self.assertIn("weather", await toolkit.get_skill_instructions())

            loader.refresh_interval = 0
            engine.pages = [RuntimeError("Polaris unavailable")]
            [event async for event in middleware.on_reply(agent, {}, next_handler)]
            self.assertIn("weather", await toolkit.get_skill_instructions())

            engine.pages = [
                SkillListResponse(
                    1,
                    [SkillResource(name="weather", version_info=SkillVersionInfo(active_version="v2"))],
                )
            ]
            engine.downloads[("weather", "v2")] = SkillDownloadResponse(
                version="v2", content_type="application/zip", data=skill_zip(name="weather")
            )
            [event async for event in middleware.on_reply(agent, {}, next_handler)]
            self.assertIn("weather", await toolkit.get_skill_instructions())
            basic = toolkit.tool_groups[0]
            self.assertNotIn(loader, basic.skills_or_loaders)
