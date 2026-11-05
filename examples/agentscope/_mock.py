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

"""Deterministic models and tools shared by the AgentScope examples."""

import ast
import json
import operator
import uuid
from datetime import datetime
from types import SimpleNamespace

from agentscope.credential import CredentialBase
from agentscope.message import TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState
from agentscope.model import ChatModelBase, ChatResponse, FinishedReason
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import ToolBase, ToolChunk
from pydantic import BaseModel


def _text(value) -> str:
    if isinstance(value, list):
        return "".join(
            item if isinstance(item, str) else getattr(item, "text", "") for item in value
        )
    return str(value or "")


def _last_user_text(messages):
    for message in reversed(messages):
        if getattr(message, "role", "") != "user":
            continue
        text = message.get_text_content()
        if text:
            return text
    return ""


def _last_tool_result(messages):
    for message in reversed(messages):
        if getattr(message, "role", "") == "user":
            break
        for block in reversed(message.content):
            if isinstance(block, ToolResultBlock):
                return _text(block.output)
    return ""


def _tool_names(tools):
    names = set()
    for tool in tools or ():
        function = tool.get("function", {}) if isinstance(tool, dict) else {}
        name = function.get("name")
        if name:
            names.add(name)
    return names


class _AllowedTool(ToolBase):
    is_concurrency_safe = True
    is_read_only = True

    async def check_permissions(self, tool_input, context):
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Allowed deterministic example tool",
        )

    @staticmethod
    def response(text):
        return ToolChunk(
            content=[TextBlock(text=text)],
            state=ToolResultState.SUCCESS,
            is_last=True,
        )


class WeatherTool(_AllowedTool):
    name = "get_weather"
    description = "Get deterministic example weather for a city"
    input_schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }

    async def call(self, city: str):
        return self.response(
            f"Weather in {city}\n- Condition: Sunny\n- Temperature: 22 C\n- Humidity: 45%",
        )


class CalculateTool(_AllowedTool):
    name = "calculate"
    description = "Calculate a simple arithmetic expression"
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    }

    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    async def call(self, expression: str):
        try:
            node = ast.parse(expression, mode="eval").body
            value = self._evaluate(node)
        except Exception as error:
            return ToolChunk(
                content=[TextBlock(text=f"Failed to calculate: {error}")],
                state=ToolResultState.ERROR,
                is_last=True,
            )
        return self.response(f"Result: {value:g}")

    def _evaluate(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._operators:
            return self._operators[type(node.op)](
                self._evaluate(node.left),
                self._evaluate(node.right),
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._operators:
            return self._operators[type(node.op)](self._evaluate(node.operand))
        raise ValueError("only numbers and + - * / are supported")


class CurrentTimeTool(_AllowedTool):
    name = "get_current_time"
    description = "Get the current local date and time"
    input_schema = {"type": "object", "properties": {}}

    async def call(self):
        return self.response(
            "Current time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )


def default_tools():
    return [WeatherTool(), CalculateTool(), CurrentTimeTool()]


class DemoChatModel(ChatModelBase):
    """Small streaming model that exercises text, skills and Tool calls."""

    class Parameters(BaseModel):
        pass

    def __init__(self, *, skill_loader=None, stream: bool = True):
        super().__init__(
            credential=CredentialBase(),
            model="polaris-demo-model",
            parameters=self.Parameters(),
            stream=stream,
            max_retries=0,
            retry_delay=0,
        )
        self.skill_loader = skill_loader
        self.formatter = SimpleNamespace(supported_input_media_types=["text"])

    async def _call_api(self, model, messages, tools=None, tool_choice=None, **kwargs):
        tool_result = _last_tool_result(messages)
        if tool_result:
            reply = f"Tool result:\n{tool_result}"
        else:
            text = _last_user_text(messages)
            reply = await self._reply_for_text(text, _tool_names(tools))

        if isinstance(reply, ToolCallBlock):
            if not self.stream:
                return ChatResponse(content=[reply], is_last=True)

            async def tool_stream():
                yield ChatResponse(content=[reply], is_last=False)

            return tool_stream()

        text_id = f"text-{uuid.uuid4().hex}"
        if not self.stream:
            return ChatResponse(
                content=[TextBlock(text=reply, id=text_id)],
                is_last=True,
                finished_reason=FinishedReason.COMPLETED,
            )

        async def text_stream():
            parts = reply.split(" ")
            for index, part in enumerate(parts):
                suffix = " " if index < len(parts) - 1 else ""
                yield ChatResponse(
                    content=[TextBlock(text=part + suffix, id=text_id)],
                    is_last=False,
                )

        return text_stream()

    async def _reply_for_text(self, text, available_tools):
        lower = text.lower()
        if text == "/skill-list" and self.skill_loader is not None:
            skills = await self.skill_loader.list_skills()
            return "\n".join(skill.name for skill in skills) or "No skills"
        if text.startswith("/skill ") and self.skill_loader is not None:
            name = text.split(None, 1)[1].strip()
            try:
                skill = await self.skill_loader.async_get_skill(name)
            except (LookupError, ValueError):
                return f"Skill not found: {name}"
            markdown = skill.markdown.strip()
            if len(markdown) > 1200:
                markdown = markdown[:1200].rstrip() + "\n\n[skill preview truncated]"
            return f"{skill.name}\n\n{markdown}"

        if "weather" in lower and "get_weather" in available_tools:
            city = "Beijing"
            for candidate in ("Shanghai", "Shenzhen", "Hangzhou", "Beijing"):
                if candidate.lower() in lower:
                    city = candidate
                    break
            return ToolCallBlock(
                id=f"tool-{uuid.uuid4().hex}",
                name="get_weather",
                input=json.dumps({"city": city}),
            )

        if (
            any(symbol in text for symbol in ("+", "-", "*", "/"))
            and "calculate" in available_tools
        ):
            return ToolCallBlock(
                id=f"tool-{uuid.uuid4().hex}",
                name="calculate",
                input=json.dumps({"expression": text}),
            )

        if "time" in lower and "get_current_time" in available_tools:
            return ToolCallBlock(
                id=f"tool-{uuid.uuid4().hex}",
                name="get_current_time",
                input="{}",
            )

        mcp_echo = next(
            (
                name
                for name in available_tools
                if name.startswith("mcp__") and name.endswith("__echo_text")
            ),
            None,
        )
        if mcp_echo is not None:
            return ToolCallBlock(
                id=f"tool-{uuid.uuid4().hex}",
                name=mcp_echo,
                input=json.dumps({"text": text}),
            )

        return f"Echo: {text}"
