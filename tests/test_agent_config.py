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

from polaris_ai.agentscope import PolarisAgentConfig


def test_env_values_take_precedence_and_fall_back_to_sdk_variables():
    config = PolarisAgentConfig.from_env(
        {
            "POLARIS_AI_ADDRESS": "10.0.0.1:8091,10.0.0.2:8091",
            "POLARIS_AI_CONNECTOR_TOKEN": "connector",
            "POLARIS_AI_SERVICE_TOKEN": "service",
            "POLARIS_AI_SKILL_ADDRESS": "10.0.0.1:8094",
            "POLARIS_AI_SKILL_NAMES": "weather, lookup",
            "POLARIS_AI_SKILL_VERSION": "v1",
            "POLARIS_AI_SKILL_LIST_LIMIT": "2",
            "POLARIS_AI_SKILL_MAX_SKILLS": "3",
            "POLARIS_AI_SKILL_LIST_REFRESH_INTERVAL_SECONDS": "12.5",
            "POLARIS_AI_MOUNTED_SKILL_ENABLED": "true",
            "POLARIS_AI_A2A_ENABLED": "true",
            "POLARIS_AI_A2A_REGISTRY_ENABLED": "true",
            "POLARIS_AI_A2A_DISCOVERY_ENABLED": "false",
            "POLARIS_AI_A2A_TTL": "7",
            "POLARIS_AI_MCP_ENABLED": "true",
            "POLARIS_AI_MCP_PROTOCOL_VERSION": "2025-06-18",
            "POLARIS_AI_MCP_SCHEME": "https",
            "POLARIS_AI_MCP_TIMEOUT": "12.5",
            "POLARIS_AI_MCP_FILTER_CONTRACT": "false",
            "POLARIS_AI_MCP_HEADERS": "Authorization=Bearer token,X-Env=test",
            "POLARIS_AI_MCP_CALLER_SERVICE": "agent",
            "POLARIS_AI_MCP_LABELS": "env=test",
            "POLARIS_SERVER_ADDRESS": "ignored:8091",
            "POLARIS_TOKEN": "ignored",
            "POLARIS_SERVICE_TOKEN": "ignored",
        }
    )
    assert config.addresses == ("10.0.0.1:8091", "10.0.0.2:8091")
    assert config.connector_token == "connector"
    assert config.service_token == "service"
    assert config.skill.addresses == ("10.0.0.1:8094",)
    assert config.skill.names == ("weather", "lookup")
    assert config.skill.version == "v1"
    assert config.skill.list_limit == 2
    assert config.skill.max_skills == 3
    assert config.skill.refresh_interval == 12.5
    assert config.skill.mounted_enabled
    assert config.a2a.enabled
    assert config.a2a.registry.enabled
    assert not config.a2a.discovery.enabled
    assert config.a2a.registry.ttl == 7
    assert config.mcp.enabled
    assert config.mcp.protocol_version == "2025-06-18"
    assert config.mcp.scheme == "https"
    assert config.mcp.timeout == 12.5
    assert not config.mcp.filter_contract
    assert config.mcp.headers == (
        ("Authorization", "Bearer token"),
        ("X-Env", "test"),
    )
    assert config.mcp.caller_service == "agent"
    assert config.mcp.labels == "env=test"


def test_env_fallbacks_and_mounted_service_order():
    fallback = PolarisAgentConfig.from_env(
        {
            "POLARIS_SERVER_ADDRESS": "registry:8091",
            "POLARIS_TOKEN": "connector",
            "POLARIS_SERVICE_TOKEN": "service",
        },
        agent_name="agent-name",
    )
    assert fallback.addresses == ("registry:8091",)
    assert fallback.connector_token == "connector"
    assert fallback.service_token == "service"
    assert fallback.skill.mounted_service_name == "agent-name"

    card_name = PolarisAgentConfig.from_env(
        {"POLARIS_AI_AGENT_NAME": "agent-name", "POLARIS_AI_A2A_CARD_NAME": "card-name"}
    )
    assert card_name.skill.mounted_service_name == "card-name"

    explicit = PolarisAgentConfig.from_env(
        {
            "POLARIS_AI_MOUNTED_SKILL_SERVICE": "mounted-name",
            "POLARIS_AI_AGENT_NAME": "agent-name",
            "POLARIS_AI_A2A_CARD_NAME": "card-name",
        }
    )
    assert explicit.skill.mounted_service_name == "mounted-name"


def test_invalid_environment_scalars_are_rejected():
    with pytest.raises(ValueError, match="boolean"):
        PolarisAgentConfig.from_env({"POLARIS_AI_ENABLED": "maybe"})
    with pytest.raises(ValueError, match="POLARIS_AI_A2A_TTL"):
        PolarisAgentConfig.from_env({"POLARIS_AI_A2A_TTL": "five"})
    with pytest.raises(ValueError, match="must be a number"):
        PolarisAgentConfig.from_env({"POLARIS_AI_SKILL_LIST_REFRESH_INTERVAL_SECONDS": "never"})
    with pytest.raises(ValueError, match="name=value"):
        PolarisAgentConfig.from_env({"POLARIS_AI_MCP_HEADERS": "invalid"})
