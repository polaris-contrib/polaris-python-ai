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

import asyncio

import pytest
from agentscope.message import Msg, ToolResultBlock, UserMsg

from examples.agentscope._mock import DemoChatModel, _last_tool_result


def test_tool_result_does_not_leak_into_the_next_user_turn():
    messages = [
        UserMsg(name="user", content="first"),
        Msg(
            name="agent",
            role="assistant",
            content=[
                ToolResultBlock(
                    id="result-1",
                    name="get_weather",
                    output="Sunny",
                )
            ],
        ),
        UserMsg(name="user", content="second"),
    ]
    assert _last_tool_result(messages) == ""


def test_tool_result_is_used_inside_the_current_turn():
    messages = [
        UserMsg(name="user", content="weather"),
        Msg(
            name="agent",
            role="assistant",
            content=[
                ToolResultBlock(
                    id="result-1",
                    name="get_weather",
                    output="Sunny",
                )
            ],
        ),
    ]
    assert _last_tool_result(messages) == "Sunny"


def test_demo_model_selects_discovered_mcp_echo_tool():
    model = DemoChatModel(stream=False)
    call = asyncio.run(
        model._reply_for_text(
            "hello",
            {"mcp__polaris_example__echo_text"},
        )
    )
    assert call.name == "mcp__polaris_example__echo_text"
    assert call.input == '{"text": "hello"}'


def test_example_mcp_server_exposes_read_only_echo_tool():
    pytest.importorskip("mcp.server")
    from examples.agentscope.mcp.agent.server import create_mcp_server

    server = create_mcp_server("example")
    assert server.name == "example"
