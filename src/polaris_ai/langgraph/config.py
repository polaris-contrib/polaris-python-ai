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

"""Application options for Polaris-managed LangGraph deployments."""

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


def _list_env(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int_env(value: str, name: str, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _headers_env(value: str) -> tuple[tuple[str, str], ...]:
    headers = []
    for item in _list_env(value):
        name, separator, header_value = item.partition("=")
        if not separator or not name.strip():
            raise ValueError("POLARIS_AI_LANGGRAPH_HEADERS items must be name=value")
        headers.append((name.strip(), header_value.strip()))
    return tuple(headers)


@dataclass(frozen=True)
class PolarisLangGraphRegistryConfig:
    enabled: bool = True
    ttl: int = 5


@dataclass(frozen=True)
class PolarisLangGraphDiscoveryConfig:
    enabled: bool = True
    timeout: int = 0


@dataclass(frozen=True)
class PolarisLangGraphConfig:
    """Code-first settings for registration, discovery, and RemoteGraph calls."""

    enabled: bool = True
    namespace: str = "default"
    addresses: tuple[str, ...] = ("127.0.0.1:8091",)
    connector_token: str = ""
    service_token: str = ""
    graph_id: str = ""
    service: str = ""
    path: str = "/"
    protocol: str = "http"
    api_key: str = ""
    headers: tuple[tuple[str, str], ...] = ()
    caller_service: str = ""
    labels: str = ""
    registry: PolarisLangGraphRegistryConfig = field(
        default_factory=PolarisLangGraphRegistryConfig,
    )
    discovery: PolarisLangGraphDiscoveryConfig = field(
        default_factory=PolarisLangGraphDiscoveryConfig,
    )

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        *,
        graph_id: str = "",
        service: str = "",
    ) -> "PolarisLangGraphConfig":
        """Load LangGraph options with ``POLARIS_AI_*`` precedence."""
        env = os.environ if environ is None else environ

        def value(name: str, fallback: str = "") -> str:
            return env.get(name, env.get(fallback, "")).strip()

        configured_graph = value("POLARIS_AI_LANGGRAPH_GRAPH_ID") or graph_id.strip()
        configured_service = value("POLARIS_AI_LANGGRAPH_SERVICE") or service.strip()
        addresses = _list_env(
            value("POLARIS_AI_LANGGRAPH_ADDRESS", "POLARIS_SERVER_ADDRESS")
        ) or _list_env(
            value("POLARIS_AI_LANGGRAPH_ADDRESSES", "POLARIS_SERVER_ADDRESSES")
        ) or _list_env(value("POLARIS_AI_ADDRESS", "POLARIS_SERVER_ADDRESS"))
        return cls(
            enabled=_bool_env(env.get("POLARIS_AI_LANGGRAPH_ENABLED", ""), default=True),
            namespace=(
                value("POLARIS_AI_LANGGRAPH_NAMESPACE", "POLARIS_NAMESPACE")
                or "default"
            ),
            addresses=addresses or ("127.0.0.1:8091",),
            connector_token=value(
                "POLARIS_AI_LANGGRAPH_CONNECTOR_TOKEN",
                "POLARIS_TOKEN",
            ),
            service_token=value(
                "POLARIS_AI_LANGGRAPH_SERVICE_TOKEN",
                "POLARIS_SERVICE_TOKEN",
            ),
            graph_id=configured_graph,
            service=configured_service or configured_graph,
            path=value("POLARIS_AI_LANGGRAPH_PATH") or "/",
            protocol=value("POLARIS_AI_LANGGRAPH_PROTOCOL") or "http",
            api_key=value("POLARIS_AI_LANGGRAPH_API_KEY", "LANGGRAPH_API_KEY"),
            headers=_headers_env(value("POLARIS_AI_LANGGRAPH_HEADERS")),
            caller_service=value("POLARIS_AI_LANGGRAPH_CALLER_SERVICE"),
            labels=value("POLARIS_AI_LANGGRAPH_LABELS"),
            registry=PolarisLangGraphRegistryConfig(
                enabled=_bool_env(
                    env.get("POLARIS_AI_LANGGRAPH_REGISTRY_ENABLED", ""),
                    default=True,
                ),
                ttl=_int_env(
                    value("POLARIS_AI_LANGGRAPH_TTL"),
                    "POLARIS_AI_LANGGRAPH_TTL",
                    5,
                ),
            ),
            discovery=PolarisLangGraphDiscoveryConfig(
                enabled=_bool_env(
                    env.get("POLARIS_AI_LANGGRAPH_DISCOVERY_ENABLED", ""),
                    default=True,
                ),
                timeout=_int_env(
                    value("POLARIS_AI_LANGGRAPH_DISCOVERY_TIMEOUT"),
                    "POLARIS_AI_LANGGRAPH_DISCOVERY_TIMEOUT",
                    0,
                ),
            ),
        )
