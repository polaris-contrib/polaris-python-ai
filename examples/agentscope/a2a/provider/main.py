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

"""Start an A2A endpoint, then register it and keep automatic heartbeats active."""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager

import uvicorn
from a2a.types import AgentSkill

from examples._support import get_local_host
from examples.agentscope._common import ai_logging, context, parser
from examples.agentscope.a2a.provider.server import create_server
from examples.agentscope.a2a.provider.skill_agent import create_skill_agent
from polaris_ai.agentscope import (
    PolarisA2ARegistrar,
    PolarisA2AServerRegistration,
    PolarisSkillLoader,
)

logger = logging.getLogger(__name__)


async def main(argv=None):
    arguments = parser("Register a model-free A2A Agent")
    arguments.add_argument("--service", default="echo-agent")
    arguments.add_argument("--host")
    arguments.add_argument("--port", type=int, default=8080)
    arguments.add_argument("--ttl", type=int, default=5)
    arguments.add_argument("--registration-port", type=int, default=1)
    interfaces = arguments.add_mutually_exclusive_group()
    interfaces.add_argument("--multi-interface", action="store_true")
    interfaces.add_argument(
        "--multi-protocol",
        action="store_true",
        help="serve JSONRPC 1.0, JSONRPC 0.3 and HTTP+JSON 1.0 interfaces",
    )
    arguments.add_argument("--agent-version", default="1.0.0")
    arguments.add_argument(
        "--skill-source", choices=("none", "published", "mounted"), default="none"
    )
    arguments.add_argument("--skill-name", action="append", default=[])
    arguments.add_argument("--skill-version", default="")
    arguments.add_argument("--skill-service")
    arguments.add_argument("--service-token", default=os.environ.get("POLARIS_SERVICE_TOKEN", ""))
    args = arguments.parse_args(argv)
    args.host = args.host or get_local_host(args.address or "127.0.0.1:8091")
    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    listener = socket.create_server((args.host, args.port), family=family)
    sdk = None
    serving = None

    @asynccontextmanager
    async def skill_agent():
        if args.skill_source == "none":
            yield None, None
            return
        service_name = args.skill_service if args.skill_source == "mounted" else ""
        if args.skill_source == "mounted" and not service_name:
            service_name = args.service
        loader = PolarisSkillLoader(
            sdk,
            args.namespace,
            names=args.skill_name,
            version=args.skill_version,
            service_name=service_name,
        )
        async with loader:
            try:
                loaded = await loader.list_skills()
            except Exception as error:
                logger.warning("Failed to read Polaris Skills; starting without skills: %s", error)
                loaded = []
            skills = [
                AgentSkill(
                    id=skill.name,
                    name=skill.name,
                    description=skill.description,
                    tags=["polaris"],
                )
                for skill in loaded
            ]
            yield create_skill_agent(args.service, loader), skills

    try:
        port = listener.getsockname()[1]
        endpoint_host = f"[{args.host}]" if ":" in args.host else args.host
        sdk = context(args, entry=__file__)
        async with ai_logging(sdk, entry=__file__):
            async with skill_agent() as (agent, skills):
                app, card = create_server(
                    args.service,
                    f"http://{endpoint_host}:{port}/",
                    agent=agent,
                    skills=skills,
                    multi_interface=args.multi_interface,
                    multi_protocol=args.multi_protocol,
                    version=args.agent_version,
                )
                server = uvicorn.Server(uvicorn.Config(app, log_level="info"))
                serving = asyncio.create_task(server.serve(sockets=[listener]))
                async with asyncio.timeout(10):
                    while not server.started:
                        if serving.done():
                            await serving
                            raise RuntimeError("A2A server stopped before startup")
                        await asyncio.sleep(0.01)
                async with PolarisA2AServerRegistration(
                    PolarisA2ARegistrar(
                        sdk,
                        args.namespace,
                        service_token=args.service_token,
                        ttl=args.ttl,
                        registration_port=args.registration_port,
                    ),
                    card,
                ):
                    print(
                        f"Registered {args.namespace}/{args.service} "
                        f"at {args.host}:{port} with registrationPort={args.registration_port}",
                        flush=True,
                    )
                    await asyncio.shield(serving)
    finally:
        try:
            if serving is not None:
                server.should_exit = True
                await serving
        finally:
            listener.close()
            if sdk is not None:
                await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
