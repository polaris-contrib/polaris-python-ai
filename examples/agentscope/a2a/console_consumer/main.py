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

"""Streaming A2A client using Polaris AgentCard discovery."""

import asyncio

from agentscope.console import launch_console
from agentscope.event import TextBlockDeltaEvent
from agentscope.message import UserMsg

from examples.agentscope._common import ai_logging, context, parser
from polaris_ai.agentscope import PolarisA2AAgent, PolarisA2AResolver


async def main(argv=None):
    arguments = parser("Discover and stream a remote A2A agent")
    arguments.add_argument("--service", default="streaming-agent")
    arguments.add_argument("--message", action="append", default=[])
    arguments.add_argument("--verbosity", choices=("quiet", "default", "debug"), default="default")
    args = arguments.parse_args(argv)

    sdk = context(args, entry=__file__, component="console-consumer")
    try:
        async with ai_logging(sdk, entry=__file__):
            resolver = PolarisA2AResolver(sdk, args.namespace)
            async with PolarisA2AAgent(resolver, args.service) as agent:
                if not args.message:
                    await launch_console(agent, verbosity=args.verbosity)
                    return []

                replies = []
                for text in args.message:
                    chunks = []
                    async for event in agent.reply_stream(
                        UserMsg(name="user", content=text),
                    ):
                        if isinstance(event, TextBlockDeltaEvent):
                            chunks.append(event.delta)
                            print(event.delta, end="", flush=True)
                    print(flush=True)
                    replies.append("".join(chunks))
                return replies
    finally:
        await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
