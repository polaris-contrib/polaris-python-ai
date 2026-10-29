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
