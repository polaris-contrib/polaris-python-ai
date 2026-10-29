from unittest.mock import patch

from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime
from polaris_ai.agentscope.config import (
    PolarisA2AConfig,
    PolarisMCPConfig,
    PolarisSkillConfig,
)
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


def test_missing_registry_token_fails_and_cleans_created_context():
    context = FakeContext(FakeEngine())
    config = PolarisAgentConfig()
    with patch("polaris_ai.agentscope.context.init_context_by_config", return_value=context):
        try:
            PolarisAgentRuntime(config)
        except ValueError as error:
            assert "service_token" in str(error)
        else:
            raise AssertionError("Expected missing service token to fail")
    assert context.is_destroy()


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
