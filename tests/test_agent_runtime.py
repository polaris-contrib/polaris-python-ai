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
from unittest.mock import patch

import pytest
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import ToolBase, Toolkit

from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime
from polaris_ai.agentscope.config import (
    PolarisA2AConfig,
    PolarisMCPConfig,
    PolarisSkillConfig,
)
from polaris_ai.agentscope.middleware import PolarisDynamicSkillMiddleware
from tests._support import FakeContext, FakeEngine


def test_runtime_composes_skill_loader_and_borrowed_context_is_not_destroyed():
    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig(
        namespace="production",
        addresses=("registry:8091",),
        skill=PolarisSkillConfig(addresses=("registry:8094",)),
        a2a=PolarisA2AConfig(enabled=False),
    )
    runtime = PolarisAgentRuntime(config, sdk_context=context)
    assert runtime.skill_loader is not None
    assert runtime.resolver is None
    assert runtime.registrar is None
    assert runtime.provider.context is context
    runtime.close()
    runtime.close()
    assert not context.is_destroy()


def test_runtime_closes_owned_context_and_adapter_resources():
    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig(a2a=PolarisA2AConfig(enabled=False))
    with patch("polaris_ai.agentscope.context.init_context_by_config", return_value=context):
        runtime = PolarisAgentRuntime(config)
    assert runtime.context.owns_context
    runtime.close()
    assert context.is_destroy()


def test_runtime_allows_empty_registry_service_token():
    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig()
    with patch("polaris_ai.agentscope.context.init_context_by_config", return_value=context):
        runtime = PolarisAgentRuntime(config)
    assert runtime.registrar is not None
    assert runtime.registrar.service_token == ""
    runtime.close()
    assert context.is_destroy()


def test_attach_to_agent_builds_toolkit_and_dynamic_middleware():
    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig(a2a=PolarisA2AConfig(enabled=False))
    runtime = PolarisAgentRuntime(config, sdk_context=context)
    with patch("agentscope.agent.Agent") as agent:
        runtime.create_agent(name="weather-agent", system_prompt="Use skills", model="model")
    assert agent.call_args.kwargs["toolkit"] is runtime.skill_toolkit
    assert isinstance(agent.call_args.kwargs["middlewares"][-1], PolarisDynamicSkillMiddleware)
    runtime.close()


def test_attach_to_agent_can_be_disabled():
    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig(
        a2a=PolarisA2AConfig(enabled=False),
        skill=PolarisSkillConfig(attach_to_agent=False),
    )
    runtime = PolarisAgentRuntime(config, sdk_context=context)
    assert runtime.skill_toolkit is None
    with patch("agentscope.agent.Agent") as agent:
        runtime.create_agent(name="weather-agent", system_prompt="No skills", model="model")
    assert agent.call_args.kwargs["toolkit"] is None
    assert agent.call_args.kwargs["middlewares"] == []
    runtime.close()


def test_attach_to_agent_merges_loader_into_custom_toolkit():
    class EchoTool(ToolBase):
        name = "echo"
        description = "Echo input"
        input_schema = {"type": "object", "properties": {}}
        is_concurrency_safe = True
        is_read_only = True

        async def call(self, **kwargs):
            return kwargs

        async def check_permissions(self, tool_input, context):
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                message="Allowed by the test tool",
            )

    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig(a2a=PolarisA2AConfig(enabled=False))
    runtime = PolarisAgentRuntime(config, sdk_context=context)
    toolkit = Toolkit(tools=[EchoTool()])
    with patch("agentscope.agent.Agent") as agent:
        runtime.create_agent(
            name="weather-agent", system_prompt="Use skills", model="model", toolkit=toolkit,
        )
        runtime.create_agent(
            name="weather-agent", system_prompt="Use skills", model="model", toolkit=toolkit,
        )

    assert agent.call_args.kwargs["toolkit"] is toolkit
    basic = next(group for group in toolkit.tool_groups if group.name == "basic")
    assert basic.tools
    assert [runtime.skill_loader] == [
        loader for loader in basic.skills_or_loaders if loader is runtime.skill_loader
    ]
    runtime.close()


def test_runtime_builds_mcp_resolver_only_when_enabled():
    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig(
        a2a=PolarisA2AConfig(enabled=False),
        skill=PolarisSkillConfig(enabled=False),
        mcp=PolarisMCPConfig(enabled=True, scheme="https", timeout=5),
    )
    runtime = PolarisAgentRuntime(config, sdk_context=context)
    assert runtime.mcp_resolver is not None
    assert runtime.mcp_resolver.scheme == "https"
    assert runtime.mcp_resolver.timeout == 5
    runtime.close()


def test_cancelled_async_close_still_closes_owned_context():
    asyncio.run(_cancelled_async_close_still_closes_owned_context())


async def _cancelled_async_close_still_closes_owned_context():
    started = asyncio.Event()
    release = asyncio.Event()

    class Registrar:
        async def async_close(self):
            started.set()
            await release.wait()

    class OwnedContext:
        closed = False

        async def async_close(self):
            self.closed = True

    runtime = object.__new__(PolarisAgentRuntime)
    runtime.registrar = Registrar()
    runtime.resolver = None
    runtime.skill_loader = None
    runtime.context = OwnedContext()
    runtime._closed = False

    closing = asyncio.create_task(runtime.async_close())
    await started.wait()
    closing.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing

    assert runtime.context.closed
    assert runtime._closed
    await runtime.async_close()
