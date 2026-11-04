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

from unittest import IsolatedAsyncioTestCase

import pytest
from agentscope.message import UserMsg
from agentscope.skill import Skill, SkillLoaderBase

pytest.importorskip("agentscope.agent")

from examples.agentscope.a2a.provider.skill_agent import create_skill_agent


class FixedLoader(SkillLoaderBase):
    async def list_skills(self):
        return [self.skill]

    async def async_get_skill(self, name, *, version=None):
        if name != self.skill.name:
            raise LookupError(name)
        return self.skill


class SkillAgentTests(IsolatedAsyncioTestCase):
    async def test_model_free_agent_answers_skill_commands(self):
        loader = FixedLoader()
        loader.skill = Skill(
            name="weather",
            description="Weather lookup",
            dir=".",
            markdown="Use the weather reference.",
            updated_at=0,
        )
        agent = create_skill_agent("skill-agent", loader)
        listing = await agent.reply(UserMsg(name="user", content="/skill-list"))
        detail = await agent.reply(UserMsg(name="user", content="/skill weather"))
        echo = await agent.reply(UserMsg(name="user", content="Hello Polaris"))
        self.assertEqual("weather", listing.get_text_content())
        self.assertIn("Use the weather reference.", detail.get_text_content())
        self.assertEqual("Echo: Hello Polaris", echo.get_text_content())
