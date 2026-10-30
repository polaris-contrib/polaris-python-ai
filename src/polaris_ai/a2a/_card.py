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

"""Use the official A2A SDK's protobuf JSON and legacy card compatibility."""

import json

try:
    from a2a.client.card_resolver import parse_agent_card
    from a2a.types import AgentCard
except ImportError as error:
    raise ImportError(
        "A2A integration requires pip install 'polaris-python-ai[a2a]'."
    ) from error

from google.protobuf.json_format import MessageToDict

META_AGENT_NAME = "ai-agent-name"
META_AGENT_CARD = "a2a.agent.card"
META_TRANSPORT = "a2a.transport"
META_PATH = "a2a.path"
MAX_METADATA_VALUE_CHARS = 65535


def encode_card(card: AgentCard) -> str:
    if not isinstance(card, AgentCard) or not card.name.strip():
        raise ValueError("A native a2a.types.AgentCard with a name is required")
    return json.dumps(MessageToDict(card), ensure_ascii=False, separators=(",", ":"))


def decode_card(payload: str) -> AgentCard:
    return parse_agent_card(json.loads(payload))
