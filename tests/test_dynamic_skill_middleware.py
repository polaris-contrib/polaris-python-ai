from unittest import IsolatedAsyncioTestCase

import pytest

pytest.importorskip("agentscope.middleware")

from polaris.pkg.model.skill import (
    SkillDownloadResponse,
    SkillListResponse,
    SkillResource,
    SkillVersionInfo,
)

from polaris_ai.agentscope import PolarisDynamicSkillMiddleware, PolarisSkillLoader
from tests._support import FakeContext, FakeEngine, skill_zip


class DynamicSkillMiddlewareTests(IsolatedAsyncioTestCase):
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
