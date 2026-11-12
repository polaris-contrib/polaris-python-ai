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

"""Reusable native AgentCard construction for AgentScope applications."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

try:
    from a2a.types import (
        AgentCapabilities,
        AgentCard,
        AgentInterface,
        AgentSkill,
    )
except ImportError as error:
    raise ImportError(
        "AgentCard construction requires pip install 'polaris-python-ai[a2a]'."
    ) from error


def _agent_skill(skill) -> AgentSkill:
    if isinstance(skill, AgentSkill):
        return skill
    name = getattr(skill, "name", "")
    description = getattr(skill, "description", "")
    if not name:
        raise ValueError("Agent Skill requires a name")
    return AgentSkill(id=name, name=name, description=description, tags=["polaris"])


def build_agent_card(
    *,
    name: str,
    url: str | None = None,
    interfaces: Sequence[AgentInterface] | None = None,
    description: str = "",
    version: str = "1.0.0",
    protocol_binding: str = "JSONRPC",
    protocol_version: str = "1.0",
    skills: Sequence = (),
    input_modes: Sequence[str] = ("text/plain",),
    output_modes: Sequence[str] = ("text/plain",),
    streaming: bool = True,
) -> AgentCard:
    """Build a native A2A card while preserving framework-owned types."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Agent name is required")
    if interfaces is not None and url:
        raise ValueError("provide either url or interfaces, not both")
    if interfaces is None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Agent URL or interfaces are required")
        selected_interfaces = [
            AgentInterface(
                url=url,
                protocol_binding=protocol_binding,
                protocol_version=protocol_version,
            )
        ]
    else:
        selected_interfaces = list(interfaces)
        if not selected_interfaces:
            raise ValueError("Agent interfaces must not be empty")
        if any(not isinstance(item, AgentInterface) for item in selected_interfaces):
            raise ValueError("interfaces must contain AgentInterface objects")
    return AgentCard(
        name=name.strip(),
        description=description,
        version=version,
        supported_interfaces=selected_interfaces,
        capabilities=AgentCapabilities(streaming=streaming),
        default_input_modes=list(input_modes),
        default_output_modes=list(output_modes),
        skills=[_agent_skill(skill) for skill in skills],
    )


@dataclass(frozen=True)
class PolarisAgentCardTemplate:
    """Reusable card defaults; only endpoint and runtime Skills vary per Agent."""

    description: str = ""
    version: str = "1.0.0"
    protocol_binding: str = "JSONRPC"
    protocol_version: str = "1.0"
    input_modes: tuple[str, ...] = ("text/plain",)
    output_modes: tuple[str, ...] = ("text/plain",)
    streaming: bool = True
    skills: tuple = field(default_factory=tuple)

    def build(self, name: str, url: str, *, skills: Sequence = ()) -> AgentCard:
        selected = tuple(skills) if skills else self.skills
        return build_agent_card(
            name=name,
            url=url,
            description=self.description,
            version=self.version,
            protocol_binding=self.protocol_binding,
            protocol_version=self.protocol_version,
            skills=selected,
            input_modes=self.input_modes,
            output_modes=self.output_modes,
            streaming=self.streaming,
        )
