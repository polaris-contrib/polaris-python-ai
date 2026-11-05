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

"""Self-contained MCP fixture used by the AgentScope integration example."""

from mcp.server import MCPServer
from mcp.types import ToolAnnotations


async def echo_text(text: str) -> str:
    """Echo text through a read-only MCP Tool."""
    return f"MCP echo: {text}"


def create_mcp_server(name: str) -> MCPServer:
    server = MCPServer(
        name,
        title="Polaris MCP Agent fixture",
        instructions="Use echo_text to verify Polaris MCP discovery.",
    )
    server.tool(
        description="Echo text through the example MCP Server.",
        annotations=ToolAnnotations(read_only_hint=True),
    )(echo_text)
    return server


def create_mcp_app(name: str, *, host: str):
    return create_mcp_server(name).streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        host=host,
    )
