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

"""Model-free AgentScope agent backed by Polaris Skills."""

from types import SimpleNamespace

from agentscope.agent import Agent
from agentscope.credential import CredentialBase
from agentscope.message import TextBlock
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason
from agentscope.tool import Toolkit
from pydantic import BaseModel

from polaris_ai.agentscope import PolarisDynamicSkillMiddleware


class SkillRouterModel(ChatModelBase):
    """Route a small command vocabulary without an external model API."""

    class Parameters(BaseModel):
        pass

    def __init__(self, loader):
        super().__init__(
            credential=CredentialBase(),
            model="polaris-skill-router",
            parameters=self.Parameters(),
            stream=False,
            max_retries=0,
            retry_delay=0,
        )
        self.loader = loader
        self.formatter = SimpleNamespace(supported_input_media_types=["text"])

    async def _call_api(self, model, messages, tools=None, tool_choice=None, **kwargs):
        text = next((message.get_text_content() for message in reversed(messages)
                     if message.get_text_content()), "")
        if text == "/skill-list":
            skills = await self.loader.list_skills()
            reply = "\n".join(skill.name for skill in skills) or "No skills"
        elif text.startswith("/skill "):
            name = text.split(None, 1)[1].strip()
            try:
                skill = await self.loader.async_get_skill(name)
            except (LookupError, ValueError):
                reply = f"Skill not found: {name}"
            else:
                reply = f"{skill.name}\n\n{skill.markdown}"
        else:
            reply = "Echo: " + text
        return ChatResponse(
            content=[TextBlock(text=reply)],
            is_last=True,
            finished_reason=FinishedReason.COMPLETED,
        )


def create_skill_agent(name: str, loader) -> Agent:
    toolkit = Toolkit(skills_or_loaders=[loader])
    return Agent(
        name=name,
        system_prompt="Answer with the selected Polaris Skill or an echo.",
        model=SkillRouterModel(loader),
        toolkit=toolkit,
        middlewares=[PolarisDynamicSkillMiddleware(loader)],
    )
