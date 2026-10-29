"""Start an A2A endpoint, then register it and keep automatic heartbeats active."""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager

import uvicorn
from a2a.types import AgentSkill

from examples._internal._runtime import get_local_host
from examples.agentscope._common import context, parser
from examples.agentscope.a2a.provider.server import create_server
from examples.agentscope.a2a.provider.skill_agent import create_skill_agent
from polaris_ai.agentscope import A2ATransport, PolarisA2ARegistrar, PolarisSkillLoader

logger = logging.getLogger(__name__)


async def main(argv=None):
    arguments = parser("Register a model-free A2A Agent")
    arguments.add_argument("--service", default="echo-agent")
    arguments.add_argument("--host")
    arguments.add_argument("--port", type=int, default=8080)
    arguments.add_argument("--ttl", type=int, default=5)
    arguments.add_argument(
        "--skill-source", choices=("none", "published", "mounted"), default="none"
    )
    arguments.add_argument("--skill-name", action="append", default=[])
    arguments.add_argument("--skill-version", default="")
    arguments.add_argument("--skill-service")
    arguments.add_argument("--service-token", default=os.environ.get("POLARIS_SERVICE_TOKEN", ""))
    args = arguments.parse_args(argv)
    if not args.service_token:
        arguments.error("--service-token or POLARIS_SERVICE_TOKEN is required")
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
        async with skill_agent() as (agent, skills):
            app, card = create_server(
                args.service, f"http://{endpoint_host}:{port}/", agent=agent, skills=skills
            )
            server = uvicorn.Server(uvicorn.Config(app, log_level="info"))
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            async with asyncio.timeout(10):
                while not server.started:
                    if serving.done():
                        await serving
                        raise RuntimeError("A2A server stopped before startup")
                    await asyncio.sleep(0.01)
            async with PolarisA2ARegistrar(
                sdk,
                args.namespace,
                service_token=args.service_token,
                ttl=args.ttl,
            ) as registrar:
                await registrar.async_register(card, [A2ATransport(args.host, port)])
                print(f"Registered {args.namespace}/{args.service} at {args.host}:{port}", flush=True)
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
