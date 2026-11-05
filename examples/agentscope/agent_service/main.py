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

"""Host an AgentScope Agent behind a small FastAPI service."""

import asyncio
import json
import os
import socket
from pathlib import Path

import uvicorn
from agentscope.agent import Agent
from agentscope.message import UserMsg
from agentscope.tool import Toolkit
from fastapi import FastAPI
from polaris.api.provider import ProviderAPI
from polaris.pkg.model.server import InstanceDeRegisterRequest, InstanceRegisterRequest
from pydantic import BaseModel, Field

from examples._internal._runtime import get_local_host
from examples.agentscope._common import ai_logging, context, parser
from examples.agentscope._mock import DemoChatModel
from polaris_ai.agentscope import PolarisDynamicSkillMiddleware, PolarisSkillLoader


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = "default"


def create_agent_service(
    *,
    loader: PolarisSkillLoader | None = None,
    namespace: str = "default",
    service: str = "polaris-agent-service",
):
    """Create a small production-shaped HTTP surface around a native Agent."""
    app = FastAPI(
        title="Polaris AgentScope Agent Service",
        version="1.0.0",
    )
    agents = {}

    def build_agent():
        toolkit = Toolkit()
        middlewares = []
        if loader is not None:
            toolkit = Toolkit(skills_or_loaders=[loader])
            middlewares.append(PolarisDynamicSkillMiddleware(loader))
        return Agent(
            name=service,
            system_prompt="Use the configured Polaris Skills when requested.",
            model=DemoChatModel(skill_loader=loader),
            toolkit=toolkit,
            middlewares=middlewares,
        )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": service,
            "namespace": namespace,
            "sessions": len(agents),
            "skills": loader is not None,
        }

    @app.post("/chat")
    async def chat(request: ChatRequest):
        agent = agents.get(request.session_id)
        if agent is None:
            agent = build_agent()
            agents[request.session_id] = agent
        reply = await agent.reply(UserMsg(name="user", content=request.message))
        return {
            "session_id": request.session_id,
            "reply": reply.get_text_content(),
        }

    return app


async def main(argv=None):
    arguments = parser("Run an AgentScope Agent as an HTTP service")
    arguments.add_argument("--service", default="polaris-agent-service")
    arguments.add_argument("--host")
    arguments.add_argument("--port", type=int, default=0)
    arguments.add_argument("--ttl", type=int, default=5)
    arguments.add_argument("--ready-file")
    arguments.add_argument("--load-skills", action="store_true")
    arguments.add_argument("--skill-name", action="append", default=[])
    arguments.add_argument("--skill-version", default="")
    arguments.add_argument(
        "--service-token",
        default=os.environ.get("POLARIS_SERVICE_TOKEN", ""),
    )
    args = arguments.parse_args(argv)

    args.host = args.host or get_local_host(args.address or "127.0.0.1:8091")
    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    listener = socket.create_server((args.host, args.port), family=family)
    port = listener.getsockname()[1]
    endpoint_host = f"[{args.host}]" if ":" in args.host else args.host
    endpoint = f"http://{endpoint_host}:{port}"
    sdk = None
    loader = None
    provider = None
    registered = None
    serving = None
    server = None
    try:
        sdk = context(args, entry=__file__, component="agent-service")
        async with ai_logging(sdk, entry=__file__):
            if args.load_skills or args.skill_name:
                loader = PolarisSkillLoader(
                    sdk,
                    args.namespace,
                    names=args.skill_name,
                    version=args.skill_version,
                )
            app = create_agent_service(
                loader=loader,
                namespace=args.namespace,
                service=args.service,
            )
            server = uvicorn.Server(uvicorn.Config(app, log_level="info", access_log=False))
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            async with asyncio.timeout(10):
                while not server.started:
                    if serving.done():
                        await serving
                        raise RuntimeError("Agent service stopped before startup")
                    await asyncio.sleep(0.01)

            provider = ProviderAPI(sdk)
            request = InstanceRegisterRequest(
                namespace=args.namespace,
                service=args.service,
                service_token=args.service_token,
                host=args.host,
                port=port,
                version="1.0.0",
                protocol="http",
                metadata={
                    "framework": "agentscope",
                    "agent-service": "true",
                },
                ttl=args.ttl,
            )
            registered = await asyncio.to_thread(provider.register_instance, request)
            ready = {
                "service": args.service,
                "namespace": args.namespace,
                "host": args.host,
                "port": port,
                "endpoint": endpoint,
                "instance_id": registered.instance_id,
            }
            if args.ready_file:
                ready_path = Path(args.ready_file)
                ready_path.parent.mkdir(parents=True, exist_ok=True)
                ready_path.write_text(json.dumps(ready), encoding="utf-8")
            print(json.dumps(ready), flush=True)
            await asyncio.shield(serving)
            return ready
    finally:
        try:
            if provider is not None and registered is not None:
                await asyncio.to_thread(
                    provider.deregister_instance,
                    InstanceDeRegisterRequest(
                        service=args.service,
                        service_token=args.service_token,
                        namespace=args.namespace,
                        host=args.host,
                        port=port,
                        instance_id=registered.instance_id,
                    ),
                )
        finally:
            try:
                if loader is not None:
                    await loader.async_close()
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
