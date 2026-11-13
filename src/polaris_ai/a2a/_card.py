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

"""Validate, encode and decode versioned A2A AgentCards."""

from __future__ import annotations

import copy
import ipaddress
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from a2a.client.card_resolver import parse_agent_card
from a2a.types import AgentCard
from google.protobuf.descriptor import Descriptor
from google.protobuf.json_format import MessageToDict, ParseError

META_AGENT_NAME = "ai-agent-name"
META_AGENT_CARD = "ai-agent-card"
META_A2A_VERSION = "ai-a2a-version"
MAX_METADATA_VALUE_CHARS = 65535

A2A_VERSION_03 = "0.3"
A2A_VERSION_10 = "1.0"
SUPPORTED_A2A_VERSIONS = (A2A_VERSION_03, A2A_VERSION_10)
_MISSING = object()


@dataclass(frozen=True)
class PreparedAgentCard:
    """One validated instance-level AgentCard and its registration fields."""

    card: AgentCard
    payload: str
    a2a_version: str
    host: str


def normalize_a2a_version(value: str) -> str:
    """Return the canonical AgentCard schema version."""
    if not isinstance(value, str):
        raise ValueError("a2a_version must be a string")
    normalized = value.strip()
    if normalized in ("0.3.0", A2A_VERSION_03):
        return A2A_VERSION_03
    if normalized in ("1.0.0", A2A_VERSION_10):
        return A2A_VERSION_10
    raise ValueError(f"a2a_version must be one of {SUPPORTED_A2A_VERSIONS}")


def normalize_ip_address(value: str) -> str:
    """Validate a single IP address and return its compressed representation."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Agent interface host is required")
    host = value.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if "%" in host:
        raise ValueError("Agent interface host must not contain an IPv6 zone")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ValueError(f"Agent interface host must be an IP address: {value!r}") from error
    if address.is_unspecified:
        raise ValueError("Agent interface host must not be an unspecified address")
    if address.is_multicast:
        raise ValueError("Agent interface host must not be a multicast address")
    return address.compressed


def interface_host(url: str) -> str:
    """Extract and validate the IP host from an A2A interface URL."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Agent interface URL is required")
    original = url.strip()
    parsed_url = original
    if "://" not in parsed_url and not parsed_url.startswith("//"):
        parsed_url = "//" + parsed_url
    parsed = urlsplit(parsed_url)
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Unsupported Agent interface URL scheme: {parsed.scheme!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Agent interface URL must not contain userinfo")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"Invalid Agent interface URL port: {url!r}") from error
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Agent interface URL port must be in 1..65535")
    if not parsed.hostname:
        raise ValueError(f"Agent interface URL has no host: {url!r}")
    return normalize_ip_address(parsed.hostname)


def _load_mapping(value: Any) -> tuple[dict[str, Any], bool]:
    is_native = isinstance(value, AgentCard)
    if is_native:
        return MessageToDict(value), True
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("AgentCard payload must be valid JSON") from error
    if not isinstance(value, Mapping):
        raise ValueError("AgentCard must be a native AgentCard, mapping or JSON object")
    return copy.deepcopy(dict(value)), False


def _reject_duplicate_field_aliases(
    value: Any,
    descriptor: Descriptor,
    *,
    path: str = "AgentCard",
) -> None:
    if not isinstance(value, Mapping):
        return
    for field in descriptor.fields:
        aliases = tuple(dict.fromkeys((field.name, field.json_name)))
        present = [alias for alias in aliases if alias in value]
        if len(present) > 1:
            raise ValueError(
                f"AgentCard field {path}.{field.json_name} must not define "
                f"aliases {present[0]!r} and {present[1]!r} together"
            )
        if not present or field.message_type is None:
            continue
        if field.message_type.GetOptions().map_entry:
            continue
        field_value = value[present[0]]
        field_path = f"{path}.{field.json_name}"
        items = field_value if isinstance(field_value, list) else [field_value]
        for index, item in enumerate(items):
            item_path = f"{field_path}[{index}]" if isinstance(field_value, list) else field_path
            _reject_duplicate_field_aliases(
                item,
                field.message_type,
                path=item_path,
            )


def _reject_duplicate_legacy_aliases(payload: dict[str, Any]) -> None:
    for name, alias in (
        ("protocolVersion", "protocol_version"),
        ("preferredTransport", "preferred_transport"),
        ("additionalInterfaces", "additional_interfaces"),
    ):
        if name in payload and alias in payload:
            raise ValueError(
                f"AgentCard field {name} must not define aliases {name!r} and {alias!r} together"
            )


def _aliased_value(
    payload: Mapping[str, Any],
    *names: str,
    default: Any = _MISSING,
) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    return default


def _validate_schema_shape(
    payload: dict[str, Any],
    a2a_version: str,
    *,
    is_native: bool,
) -> None:
    if a2a_version == A2A_VERSION_03:
        if is_native:
            raise ValueError("A native AgentCard must use a2a_version='1.0'")
        if not isinstance(payload.get("url"), str) or not payload["url"].strip():
            raise ValueError("AgentCard 0.3 requires a non-empty top-level url")
        if any(
            key in payload
            for key in ("supportedInterfaces", "supported_interfaces")
        ):
            raise ValueError("AgentCard 0.3 must not use supportedInterfaces")
        preferred_transport = _aliased_value(
            payload,
            "preferredTransport",
            "preferred_transport",
        )
        if preferred_transport is not _MISSING and (
            not isinstance(preferred_transport, str) or not preferred_transport.strip()
        ):
            raise ValueError("AgentCard 0.3 preferredTransport must be a non-empty string")
        protocol_version = _aliased_value(
            payload,
            "protocolVersion",
            "protocol_version",
        )
        if protocol_version is not _MISSING:
            if not isinstance(protocol_version, str) or not protocol_version.strip():
                raise ValueError("AgentCard 0.3 protocolVersion must be a non-empty string")
            if normalize_a2a_version(protocol_version) != A2A_VERSION_03:
                raise ValueError("AgentCard 0.3 protocolVersion must resolve to 0.3")
        additional = _aliased_value(
            payload,
            "additionalInterfaces",
            "additional_interfaces",
            default=[],
        )
        if not isinstance(additional, list):
            raise ValueError("AgentCard 0.3 additionalInterfaces must be a list")
        if any(
            not isinstance(item, Mapping)
            or not isinstance(item.get("url"), str)
            or not item["url"].strip()
            or not isinstance(item.get("transport"), str)
            or not item["transport"].strip()
            for item in additional
        ):
            raise ValueError("AgentCard 0.3 additionalInterfaces entries are invalid")
        return

    if any(
        key in payload
        for key in (
            "url",
            "preferredTransport",
            "preferred_transport",
            "protocolVersion",
            "protocol_version",
            "additionalInterfaces",
            "additional_interfaces",
        )
    ):
        raise ValueError("AgentCard 1.0 must not use legacy connection fields")
    interfaces = _aliased_value(payload, "supportedInterfaces", "supported_interfaces")
    if not isinstance(interfaces, list) or not interfaces:
        raise ValueError("AgentCard 1.0 requires non-empty supportedInterfaces")
    for item in interfaces:
        protocol_binding = (
            _aliased_value(item, "protocolBinding", "protocol_binding")
            if isinstance(item, Mapping)
            else _MISSING
        )
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("url"), str)
            or not item["url"].strip()
            or not isinstance(protocol_binding, str)
            or not protocol_binding.strip()
        ):
            raise ValueError("AgentCard 1.0 supportedInterfaces entries are invalid")


def prepare_agent_card(
    agent_card: AgentCard | Mapping[str, Any] | str,
    *,
    a2a_version: str = A2A_VERSION_10,
) -> PreparedAgentCard:
    """Validate one AgentCard and prepare its instance registration payload."""
    version = normalize_a2a_version(a2a_version)
    payload_mapping, is_native = _load_mapping(agent_card)
    _reject_duplicate_field_aliases(payload_mapping, AgentCard.DESCRIPTOR)
    _reject_duplicate_legacy_aliases(payload_mapping)
    _validate_schema_shape(payload_mapping, version, is_native=is_native)
    try:
        card = parse_agent_card(copy.deepcopy(payload_mapping))
    except (ParseError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid AgentCard payload: {error}") from error

    if not card.name.strip():
        raise ValueError("AgentCard name is required")
    if not card.version.strip():
        raise ValueError("AgentCard version is required")
    if not card.supported_interfaces:
        raise ValueError("AgentCard must contain at least one interface")

    hosts = []
    for interface in card.supported_interfaces:
        if not interface.protocol_binding.strip():
            raise ValueError("AgentCard interface protocolBinding is required")
        hosts.append(interface_host(interface.url))
    canonical_hosts = set(hosts)
    if len(canonical_hosts) != 1:
        raise ValueError("All AgentCard interfaces must use the same IP address")

    payload = (
        encode_card(card, a2a_version=version)
        if is_native
        else json.dumps(payload_mapping, ensure_ascii=False, separators=(",", ":"))
    )
    return PreparedAgentCard(
        card=card,
        payload=payload,
        a2a_version=version,
        host=hosts[0],
    )


def encode_card(card: AgentCard, *, a2a_version: str = A2A_VERSION_10) -> str:
    """Encode a native AgentCard without changing its endpoint fields."""
    version = normalize_a2a_version(a2a_version)
    if version != A2A_VERSION_10:
        raise ValueError("Native AgentCard encoding only supports a2a_version='1.0'")
    if not isinstance(card, AgentCard) or not card.name.strip():
        raise ValueError("A native a2a.types.AgentCard with a name is required")
    return json.dumps(
        MessageToDict(card),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_card(payload: str, *, a2a_version: str = A2A_VERSION_10) -> AgentCard:
    """Decode a declared AgentCard schema version to the native AgentCard."""
    return prepare_agent_card(payload, a2a_version=a2a_version).card
