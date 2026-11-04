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

"""Application-side configuration for Polaris AgentScope integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool_env(value: str, *, default: bool) -> bool:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    if not lowered:
        return default
    raise ValueError(f"Invalid boolean environment value: {value!r}")


def _text_env(value: str) -> str:
    return value.strip()


def _list_env(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int_env(value: str, name: str, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _float_env(value: str, name: str, default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error


def _headers_env(value: str) -> tuple[tuple[str, str], ...]:
    result = []
    for item in _list_env(value):
        name, separator, header_value = item.partition("=")
        if not separator or not name.strip():
            raise ValueError("POLARIS_AI_MCP_HEADERS items must be name=value")
        result.append((name.strip(), header_value.strip()))
    return tuple(result)


@dataclass(frozen=True)
class PolarisSkillConfig:
    """Read-only Skill repository options."""

    enabled: bool = True
    addresses: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    version: str = ""
    list_limit: int = 50
    max_skills: int = 100
    refresh_interval: float = 30.0
    mounted_enabled: bool = False
    mounted_service_name: str = ""
    attach_to_agent: bool = True


@dataclass(frozen=True)
class PolarisA2ARegistryConfig:
    enabled: bool = True
    ttl: int = 5


@dataclass(frozen=True)
class PolarisA2ADiscoveryConfig:
    enabled: bool = True


@dataclass(frozen=True)
class PolarisA2AConfig:
    enabled: bool = True
    registry: PolarisA2ARegistryConfig = field(default_factory=PolarisA2ARegistryConfig)
    discovery: PolarisA2ADiscoveryConfig = field(default_factory=PolarisA2ADiscoveryConfig)


@dataclass(frozen=True)
class PolarisMCPConfig:
    enabled: bool = False
    protocol_version: str = ""
    scheme: str = ""
    timeout: float = 30.0
    filter_contract: bool = True
    headers: tuple[tuple[str, str], ...] = ()
    caller_service: str = ""
    labels: str = ""


@dataclass(frozen=True)
class PolarisAgentConfig:
    """Code-first options for an application; not part of polaris.yaml."""

    enabled: bool = True
    namespace: str = "default"
    addresses: tuple[str, ...] = ("127.0.0.1:8091",)
    connector_token: str = ""
    service_token: str = ""
    skill: PolarisSkillConfig = field(default_factory=PolarisSkillConfig)
    a2a: PolarisA2AConfig = field(default_factory=PolarisA2AConfig)
    mcp: PolarisMCPConfig = field(default_factory=PolarisMCPConfig)

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        *,
        agent_name: str = "",
    ) -> "PolarisAgentConfig":
        """Load application options with explicit code and SDK env fallbacks.

        `POLARIS_AI_*` always takes precedence. Existing `POLARIS_*` variables are
        read only as fallbacks so this helper can coexist with SDK examples.
        """
        env = os.environ if environ is None else environ

        def value(name: str, fallback: str = "") -> str:
            return env.get(name, env.get(fallback, "")).strip()

        addresses = _list_env(
            value("POLARIS_AI_ADDRESS", "POLARIS_SERVER_ADDRESS")
            or value("POLARIS_AI_ADDRESSES", "POLARIS_SERVER_ADDRESSES")
        ) or ("127.0.0.1:8091",)
        skill_addresses = _list_env(
            value("POLARIS_AI_SKILL_ADDRESS", "POLARIS_SKILL_SERVER_ADDRESS")
        )

        mounted_service = value("POLARIS_AI_MOUNTED_SKILL_SERVICE")
        if not mounted_service:
            mounted_service = value("POLARIS_AI_A2A_CARD_NAME")
        if not mounted_service:
            mounted_service = value("POLARIS_AI_AGENT_NAME") or agent_name.strip()

        skill = PolarisSkillConfig(
            enabled=_bool_env(env.get("POLARIS_AI_SKILL_ENABLED", ""), default=True),
            addresses=skill_addresses,
            names=_list_env(value("POLARIS_AI_SKILL_NAMES")),
            version=value("POLARIS_AI_SKILL_VERSION"),
            list_limit=_int_env(
                value("POLARIS_AI_SKILL_LIST_LIMIT"), "POLARIS_AI_SKILL_LIST_LIMIT", 50
            ),
            max_skills=_int_env(
                value("POLARIS_AI_SKILL_MAX_SKILLS"), "POLARIS_AI_SKILL_MAX_SKILLS", 100
            ),
            refresh_interval=_float_env(
                value("POLARIS_AI_SKILL_LIST_REFRESH_INTERVAL_SECONDS"),
                "POLARIS_AI_SKILL_LIST_REFRESH_INTERVAL_SECONDS",
                30.0,
            ),
            mounted_enabled=_bool_env(
                env.get("POLARIS_AI_MOUNTED_SKILL_ENABLED", ""), default=False
            ),
            mounted_service_name=mounted_service,
            attach_to_agent=_bool_env(
                env.get("POLARIS_AI_SKILL_ATTACH_TO_AGENT", ""), default=True
            ),
        )
        a2a = PolarisA2AConfig(
            enabled=_bool_env(env.get("POLARIS_AI_A2A_ENABLED", ""), default=True),
            registry=PolarisA2ARegistryConfig(
                enabled=_bool_env(
                    env.get("POLARIS_AI_A2A_REGISTRY_ENABLED", ""), default=True
                ),
                ttl=_int_env(value("POLARIS_AI_A2A_TTL"), "POLARIS_AI_A2A_TTL", 5),
            ),
            discovery=PolarisA2ADiscoveryConfig(
                enabled=_bool_env(
                    env.get("POLARIS_AI_A2A_DISCOVERY_ENABLED", ""), default=True
                ),
            ),
        )
        headers = _headers_env(value("POLARIS_AI_MCP_HEADERS"))
        mcp = PolarisMCPConfig(
            enabled=_bool_env(env.get("POLARIS_AI_MCP_ENABLED", ""), default=False),
            protocol_version=value("POLARIS_AI_MCP_PROTOCOL_VERSION"),
            scheme=value("POLARIS_AI_MCP_SCHEME"),
            timeout=_float_env(value("POLARIS_AI_MCP_TIMEOUT"), "POLARIS_AI_MCP_TIMEOUT", 30.0),
            filter_contract=_bool_env(
                env.get("POLARIS_AI_MCP_FILTER_CONTRACT", ""), default=True
            ),
            headers=headers,
            caller_service=value("POLARIS_AI_MCP_CALLER_SERVICE"),
            labels=value("POLARIS_AI_MCP_LABELS"),
        )
        return cls(
            enabled=_bool_env(env.get("POLARIS_AI_ENABLED", ""), default=True),
            namespace=value("POLARIS_AI_NAMESPACE", "default") or "default",
            addresses=addresses,
            connector_token=value("POLARIS_AI_CONNECTOR_TOKEN", "POLARIS_TOKEN"),
            service_token=value("POLARIS_AI_SERVICE_TOKEN", "POLARIS_SERVICE_TOKEN"),
            skill=skill,
            a2a=a2a,
            mcp=mcp,
        )
