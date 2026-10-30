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

"""Resolve a Polaris AgentCard and invoke the native AgentScope A2AAgent."""

import asyncio

from agentscope.message import UserMsg

from examples.agentscope._common import context, parser
from polaris_ai.agentscope import PolarisA2AAgent, PolarisA2AResolver


async def main(argv=None):
    arguments = parser("Discover and call an A2A Agent")
    arguments.add_argument("--service", default="echo-agent")
    arguments.add_argument("--message", action="append", default=None)
    args = arguments.parse_args(argv)
    sdk = context(args, entry=__file__)
    messages = args.message or ["Hello Polaris"]
    try:
        resolver = PolarisA2AResolver(sdk, args.namespace)
        async with PolarisA2AAgent(resolver, args.service) as agent:
            replies = []
            for message in messages:
                reply = await agent.reply(UserMsg(name="user", content=message))
                text = reply.get_text_content()
                print(text)
                replies.append(text)
            return replies[0] if len(replies) == 1 else replies
    finally:
        await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
