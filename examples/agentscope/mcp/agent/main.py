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

"""Discover a Polaris MCP Server and invoke its Tool through a native Agent."""

import asyncio
import json
import os
import socket

import uvicorn
from agentscope.agent import Agent
from agentscope.message import UserMsg
from agentscope.tool import Toolkit
from polaris.api.provider import ProviderAPI
from polaris.pkg.model.error import SDKError
from polaris.pkg.model.server import InstanceDeRegisterRequest, InstanceRegisterRequest

from examples._internal._runtime import get_local_host
from examples.agentscope._common import ai_logging, context, parser
from examples.agentscope._mock import DemoChatModel
from examples.agentscope.mcp.agent.server import create_mcp_app
from polaris_ai.agentscope import PolarisMCPResolver


async def _wait_candidates(resolver, service, protocol_version, timeout=20):
    deadline = asyncio.get_running_loop().time() + timeout
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            candidates = await resolver.async_candidates(
                service,
                protocol_version=protocol_version,
            )
        except SDKError as error:
            last_error = error
            candidates = []
        if candidates:
            return candidates
        await asyncio.sleep(0.2)
    raise LookupError(f"MCP service did not appear: {resolver.namespace}/{service}: {last_error}")


async def main(argv=None):
    arguments = parser("Use a Polaris-discovered MCP Tool from an AgentScope Agent")
    arguments.add_argument("--service", default="polaris-example-mcp")
    arguments.add_argument("--host")
    arguments.add_argument("--port", type=int, default=0)
    arguments.add_argument("--ttl", type=int, default=5)
    arguments.add_argument("--protocol-version", default="2025-06-18")
    arguments.add_argument("--message", default="hello from the AgentScope Agent")
    arguments.add_argument("--serve-only", action="store_true")
    arguments.add_argument(
        "--service-token",
        default=os.environ.get("POLARIS_SERVICE_TOKEN", ""),
    )
    args = arguments.parse_args(argv)

    args.host = args.host or get_local_host(args.address or "127.0.0.1:8091")
    family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
    listener = socket.create_server((args.host, args.port), family=family)
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_mcp_app(args.service, host=args.host),
            log_level="info",
            access_log=False,
        )
    )
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    sdk = None
    provider = None
    registered = None
    client = None
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    await serving
                    raise RuntimeError("MCP HTTP server stopped before startup")
                await asyncio.sleep(0.01)

        sdk = context(args, entry=__file__, component="mcp-agent")
        async with ai_logging(sdk, entry=__file__):
            provider = ProviderAPI(sdk)
            request = InstanceRegisterRequest(
                namespace=args.namespace,
                service=args.service,
                service_token=args.service_token,
                host=args.host,
                port=port,
                version="1.0.0",
                protocol="mcp-streamable-http",
                metadata={
                    "mcp-server-name": args.service,
                    "mcp-protocol-version": args.protocol_version,
                    "mcp-endpoint-path": "/mcp",
                    "mcp-scheme": "http",
                },
                ttl=args.ttl,
            )
            registered = await asyncio.to_thread(provider.register_instance, request)
            print(
                f"Registered MCP {args.namespace}/{args.service} at {args.host}:{port}",
                flush=True,
            )

            resolver = PolarisMCPResolver(
                sdk,
                args.namespace,
                protocol_version=args.protocol_version,
                timeout=10,
            )
            await _wait_candidates(
                resolver,
                args.service,
                args.protocol_version,
            )
            client = await resolver.async_create_client(args.service)
            tools = [tool.name for tool in await client.list_raw_tools()]
            result = {
                "service": args.service,
                "host": args.host,
                "port": port,
                "instance_id": registered.instance_id,
                "protocol": "mcp-streamable-http",
                "tools": tools,
            }
            if args.serve_only:
                print(json.dumps(result), flush=True)
                await asyncio.shield(serving)
                return result

            agent = Agent(
                name="polaris-mcp-agent",
                system_prompt="Use the discovered MCP echo Tool to answer the user.",
                model=DemoChatModel(),
                toolkit=Toolkit(mcps=[client]),
            )
            reply = await agent.reply(UserMsg(name="user", content=args.message))
            result["reply"] = reply.get_text_content()
            print(json.dumps(result, ensure_ascii=False), flush=True)
            return result
    finally:
        try:
            if client is not None:
                await client.close()
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
                    server.should_exit = True
                    await serving
                finally:
                    listener.close()
                    if sdk is not None:
                        await asyncio.to_thread(sdk.destroy)


if __name__ == "__main__":
    asyncio.run(main())
