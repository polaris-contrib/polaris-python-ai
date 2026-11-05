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

"""Interactive local Agent with Polaris-managed Skills."""

import asyncio
import json

from agentscope.agent import Agent
from agentscope.console import launch_console
from agentscope.message import UserMsg
from agentscope.tool import Toolkit

from examples.agentscope._common import ai_logging, context, parser
from examples.agentscope._mock import DemoChatModel
from polaris_ai.agentscope import PolarisDynamicSkillMiddleware, PolarisSkillLoader


async def main(argv=None):
    arguments = parser("Run an interactive Agent with Polaris Skills")
    arguments.add_argument("--skill-source", choices=("published", "mounted"), default="published")
    arguments.add_argument("--skill-name", action="append", default=[])
    arguments.add_argument("--skill-version", default="")
    arguments.add_argument("--skill-service")
    arguments.add_argument("--message", action="append", default=[])
    arguments.add_argument("--verbosity", choices=("quiet", "default", "debug"), default="default")
    args = arguments.parse_args(argv)

    sdk = context(args, entry=__file__, component="skill-console-agent")
    loader = None
    try:
        async with ai_logging(sdk, entry=__file__):
            service_name = ""
            if args.skill_source == "mounted":
                service_name = args.skill_service
                if not service_name:
                    raise ValueError("--skill-service is required for mounted Skills")
            loader = PolarisSkillLoader(
                sdk,
                args.namespace,
                service_name=service_name,
                names=args.skill_name,
                version=args.skill_version,
            )
            toolkit = Toolkit(skills_or_loaders=[loader])
            agent = Agent(
                name="polaris-skill-agent",
                system_prompt="Use Polaris Skills when the user invokes /skill or /skill-list.",
                model=DemoChatModel(skill_loader=loader),
                toolkit=toolkit,
                middlewares=[PolarisDynamicSkillMiddleware(loader)],
            )
            if not args.message:
                await launch_console(agent, verbosity=args.verbosity)
                return []

            replies = []
            for text in args.message:
                reply = await agent.reply(UserMsg(name="user", content=text))
                content = reply.get_text_content()
                replies.append(content)
                print(content)
            print(json.dumps({"replies": replies}, ensure_ascii=False), flush=True)
            return replies
    finally:
        try:
            if loader is not None:
                await loader.async_close()
        finally:
            await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
