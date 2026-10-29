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
