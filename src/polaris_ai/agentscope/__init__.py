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

"""AgentScope integrations; optional dependencies load only when requested."""

from importlib import import_module

__all__ = [
    "PolarisSkillLoader",
    "PolarisAgentContext",
    "PolarisA2AAgent",
    "PolarisAgentConfig",
    "PolarisAgentRuntime",
    "PolarisDynamicSkillMiddleware",
    "PolarisMCPResolver",
    "PolarisMCPClientPool",
    "PolarisAgentCardTemplate",
    "build_agent_card",
    "PolarisA2ARegistrar",
    "PolarisA2AResolver",
    "A2ATransport",
    "AgentCardNotFoundError",
    "RegisteredInstance",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name == "PolarisSkillLoader":
        module = ".skill"
    elif name == "PolarisAgentContext":
        module = ".context"
    elif name == "PolarisA2AAgent":
        module = ".a2a"
    elif name in ("PolarisAgentConfig",):
        module = ".config"
    elif name in ("PolarisAgentRuntime",):
        module = ".runtime"
    elif name in ("PolarisDynamicSkillMiddleware",):
        module = ".middleware"
    elif name in ("PolarisMCPResolver", "PolarisMCPClientPool"):
        module = ".mcp"
    elif name in ("PolarisAgentCardTemplate", "build_agent_card"):
        module = ".cards"
    else:
        module = "polaris_ai.a2a"
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value
