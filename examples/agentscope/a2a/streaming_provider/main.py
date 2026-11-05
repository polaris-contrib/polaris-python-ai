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

"""Run a streaming model-backed A2A provider with one Agent per context."""

import asyncio
import os
import socket

import uvicorn

from examples._internal._runtime import get_local_host
from examples.agentscope._common import ai_logging, context, parser
from examples.agentscope._mock import DemoChatModel, default_tools
from examples.agentscope.a2a.streaming_provider.server import create_streaming_app
from polaris_ai.agentscope import (
    A2ATransport,
    PolarisA2ARegistrar,
    PolarisA2AServerRegistration,
    PolarisDynamicSkillMiddleware,
    PolarisSkillLoader,
)


async def main(argv=None):
    arguments = parser("Register a streaming tool-calling A2A agent")
    arguments.add_argument("--service", default="streaming-agent")
    arguments.add_argument("--host")
    arguments.add_argument("--port", type=int, default=0)
    arguments.add_argument("--ttl", type=int, default=5)
    arguments.add_argument("--service-token", default=os.environ.get("POLARIS_SERVICE_TOKEN", ""))
    arguments.add_argument(
        "--skill-source", choices=("none", "published", "mounted"), default="none"
    )
    arguments.add_argument("--skill-name", action="append", default=[])
    arguments.add_argument("--skill-version", default="")
    arguments.add_argument("--skill-service")
    args = arguments.parse_args(argv)

    args.host = args.host or get_local_host(args.address or "127.0.0.1:8091")
    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    listener = socket.create_server((args.host, args.port), family=family)
    sdk = None
    loader = None
    server = None
    serving = None
    try:
        sdk = context(args, entry=__file__, component="streaming-provider")
        async with ai_logging(sdk, entry=__file__):
            if args.skill_source != "none":
                service_name = args.skill_service
                if args.skill_source == "mounted" and not service_name:
                    service_name = args.service
                loader = PolarisSkillLoader(
                    sdk,
                    args.namespace,
                    names=args.skill_name,
                    version=args.skill_version,
                    service_name=service_name or "",
                )

            def build_agent():
                from agentscope.agent import Agent
                from agentscope.tool import Toolkit

                toolkit = Toolkit(tools=default_tools())
                middlewares = []
                if loader is not None:
                    toolkit.tool_groups[0].skills_or_loaders.append(loader)
                    middlewares.append(PolarisDynamicSkillMiddleware(loader))
                return Agent(
                    name=args.service,
                    system_prompt=(
                        "Use the provided weather, calculate and current-time tools. "
                        "Answer with the tool result."
                    ),
                    model=DemoChatModel(skill_loader=loader),
                    toolkit=toolkit,
                    middlewares=middlewares,
                )

            port = listener.getsockname()[1]
            endpoint_host = f"[{args.host}]" if ":" in args.host else args.host
            app, card = create_streaming_app(
                args.service,
                f"http://{endpoint_host}:{port}/",
                build_agent,
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
                ),
                card,
                [A2ATransport(args.host, port)],
            ):
                print(
                    f"Registered streaming {args.namespace}/{args.service} at {args.host}:{port}",
                    flush=True,
                )
                await asyncio.shield(serving)
    finally:
        try:
            if serving is not None:
                server.should_exit = True
                await serving
        finally:
            try:
                if loader is not None:
                    await loader.async_close()
            finally:
                listener.close()
                if sdk is not None:
                    await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
