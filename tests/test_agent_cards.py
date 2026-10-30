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

import pytest

pytest.importorskip("a2a.types")

from a2a.types import AgentCard, AgentSkill
from agentscope.skill import Skill

from polaris_ai.agentscope import PolarisAgentCardTemplate, build_agent_card


def skill(name="weather"):
    return Skill(
        name=name,
        description=f"{name} lookup",
        dir=".",
        markdown="instructions",
        updated_at=0,
    )


def test_build_agent_card_maps_native_skills_and_modes():
    native = AgentSkill(id="native", name="native", description="native skill", tags=["x"])
    card = build_agent_card(
        name="weather-agent",
        url="https://agent.example/a2a",
        description="Weather",
        skills=[native, skill()],
        input_modes=["text/plain", "application/json"],
        output_modes=["text/plain"],
        streaming=False,
    )
    assert isinstance(card, AgentCard)
    assert card.name == "weather-agent"
    assert card.supported_interfaces[0].url == "https://agent.example/a2a"
    assert [item.name for item in card.skills] == ["native", "weather"]
    assert card.default_input_modes == ["text/plain", "application/json"]
    assert not card.capabilities.streaming


def test_card_template_can_override_skills_per_agent():
    template = PolarisAgentCardTemplate(
        description="Template",
        version="2.0",
        protocol_binding="HTTP+JSON",
        skills=(skill("default-skill"),),
    )
    card = template.build("agent", "http://127.0.0.1:8080/a2a", skills=[skill("runtime")])
    assert card.version == "2.0"
    assert card.supported_interfaces[0].protocol_binding == "HTTP+JSON"
    assert [item.name for item in card.skills] == ["runtime"]
