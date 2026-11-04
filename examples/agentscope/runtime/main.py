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

"""Compose Polaris AgentScope adapters through PolarisAgentRuntime."""

import asyncio
import json
import os

from examples.agentscope._common import ai_log_options, context, parser
from polaris_ai.agentscope import PolarisAgentConfig, PolarisAgentRuntime
from polaris_ai.agentscope.config import (
    PolarisA2AConfig,
    PolarisMCPConfig,
    PolarisSkillConfig,
)


async def main(argv=None):
    arguments = parser("Compose Skill, A2A and MCP adapters with PolarisAgentRuntime")
    arguments.add_argument("--service-token", default=os.environ.get("POLARIS_SERVICE_TOKEN", ""))
    arguments.add_argument("--skill-name", action="append", default=[])
    arguments.add_argument("--skill-version", default="")
    arguments.add_argument("--load-skills", action="store_true")
    arguments.add_argument("--no-skill", action="store_true")
    arguments.add_argument("--no-a2a", action="store_true")
    arguments.add_argument("--mcp", action="store_true")
    arguments.add_argument("--mcp-protocol-version", default="")
    arguments.add_argument("--mcp-scheme", default="")
    args = arguments.parse_args(argv)

    sdk = context(args, entry=__file__, component="runtime")
    runtime = None
    try:
        config = PolarisAgentConfig(
            namespace=args.namespace,
            addresses=(args.address or "127.0.0.1:8091",),
            connector_token=os.environ.get("POLARIS_TOKEN", ""),
            service_token=args.service_token,
            skill=PolarisSkillConfig(
                enabled=not args.no_skill,
                names=tuple(args.skill_name),
                version=args.skill_version,
            ),
            a2a=PolarisA2AConfig(enabled=not args.no_a2a),
            mcp=PolarisMCPConfig(
                enabled=args.mcp,
                protocol_version=args.mcp_protocol_version,
                scheme=args.mcp_scheme,
            ),
        )
        runtime = PolarisAgentRuntime(
            config,
            sdk_context=sdk,
            ai_log_options=ai_log_options(__file__),
        )

        skill_names = []
        if runtime.skill_loader is not None:
            if args.load_skills:
                skill_names = [
                    skill.name for skill in await runtime.skill_loader.list_skills()
                ]
            else:
                skill_names = await runtime.skill_loader.async_list_skill_names()

        result = {
            "namespace": config.namespace,
            "skill_names": skill_names,
            "a2a_resolver": runtime.resolver is not None,
            "a2a_registrar": runtime.registrar is not None,
            "mcp_resolver": runtime.mcp_resolver is not None,
            "borrowed_context": not runtime.context.owns_context,
        }
        print(json.dumps(result), flush=True)
        return result
    finally:
        try:
            if runtime is not None:
                await runtime.async_close()
        finally:
            await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
