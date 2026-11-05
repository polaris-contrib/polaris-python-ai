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
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Resume a remote A2A conversation from a persisted AgentScope state."""

import asyncio
import json
from pathlib import Path

from agentscope.agent import A2AAgent
from agentscope.message import UserMsg
from agentscope.state import A2AAgentState

from examples.agentscope._common import ai_logging, context, parser
from polaris_ai.agentscope import PolarisA2AResolver


def _load_state(path: Path):
    if not path.is_file():
        return A2AAgentState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return A2AAgentState(
        context_id=data.get("context_id"),
        task_id=data.get("task_id"),
    )


def _save_state(path: Path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "context_id": state.context_id,
                "task_id": state.task_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


async def main(argv=None):
    arguments = parser("Resume a Polaris-discovered A2A conversation")
    arguments.add_argument("--service", default="streaming-agent")
    arguments.add_argument("--message", action="append", required=True)
    arguments.add_argument("--state-file", default="./.runtime/a2a-state.json")
    args = arguments.parse_args(argv)

    state_path = Path(args.state_file).expanduser()
    sdk = context(args, entry=__file__, component="state-resume")
    try:
        async with ai_logging(sdk, entry=__file__):
            resolver = PolarisA2AResolver(sdk, args.namespace)
            card = await resolver.async_resolve(args.service)
            state = _load_state(state_path)
            replies = []
            async with A2AAgent(card, state=state) as agent:
                for text in args.message:
                    reply = await agent.reply(UserMsg(name="user", content=text))
                    replies.append(reply.get_text_content())
                    print(reply.get_text_content())
                _save_state(state_path, agent.state)
                result = {
                    "context_id": agent.state.context_id,
                    "task_id": agent.state.task_id,
                    "replies": replies,
                    "state_file": str(state_path),
                }
            print(json.dumps(result), flush=True)
            return result
    finally:
        await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
