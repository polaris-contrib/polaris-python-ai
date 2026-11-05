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

"""Create multiple Agents from one PolarisAgentRuntime."""

import asyncio
import json
import os

from agentscope.message import UserMsg

from examples.agentscope._common import ai_log_options, context, parser
from examples.agentscope._mock import DemoChatModel
from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime
from polaris_ai.agentscope.config import PolarisA2AConfig, PolarisSkillConfig


async def main(argv=None):
    arguments = parser("Create multiple Agents from one PolarisAgentRuntime")
    arguments.add_argument("--skill-name", action="append", default=[])
    arguments.add_argument("--skill-version", default="")
    args = arguments.parse_args(argv)
    if not args.skill_name:
        args.skill_name = [os.getenv("POLARIS_SKILL_NAME", "weather")]

    sdk = context(args, entry=__file__, component="runtime-multi-agent")
    runtime = None
    try:
        runtime = PolarisAgentRuntime(
            PolarisAgentConfig(
                namespace=args.namespace,
                addresses=(args.address or "127.0.0.1:8091",),
                skill=PolarisSkillConfig(
                    names=tuple(args.skill_name),
                    version=args.skill_version,
                ),
                a2a=PolarisA2AConfig(enabled=False),
            ),
            sdk_context=sdk,
            ai_log_options=ai_log_options(__file__),
        )
        first = runtime.create_agent(
            name="skill-reader",
            system_prompt="Use Polaris Skills",
            model=DemoChatModel(skill_loader=runtime.skill_loader),
        )
        second = runtime.create_agent(
            name="skill-viewer",
            system_prompt="Use Polaris Skills",
            model=DemoChatModel(skill_loader=runtime.skill_loader),
        )
        first_reply = await first.reply(UserMsg(name="user", content="/skill-list"))
        second_reply = await second.reply(
            UserMsg(
                name="user",
                content=f"/skill {args.skill_name[0]}",
            )
        )
        result = {
            "agent_count": 2,
            "shared_toolkit": first.toolkit is second.toolkit,
            "first_reply": first_reply.get_text_content(),
            "second_reply": second_reply.get_text_content(),
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result
    finally:
        try:
            if runtime is not None:
                await runtime.async_close()
        finally:
            await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
