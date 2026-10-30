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

"""Model-free A2A server used to validate AgentScope discovery and invocation."""

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentSkill,
    Part,
    Task,
    TaskState,
    TaskStatus,
)
from agentscope.message import UserMsg
from starlette.applications import Starlette

from polaris_ai.agentscope import build_agent_card


class ReplyExecutor(AgentExecutor):
    def __init__(self, reply):
        self.reply = reply

    async def execute(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await event_queue.enqueue_event(Task(
            id=context.task_id, context_id=context.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
        ))
        await updater.start_work()
        await updater.add_artifact(
            [Part(text=await self.reply(context.get_user_input()))], last_chunk=True,
        )
        await updater.complete()

    async def cancel(self, context, event_queue):
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def create_server(service: str, base_url: str, agent=None, skills=None):
    card = build_agent_card(
        name=service,
        url=base_url,
        description="Model-free AgentScope integration verification",
        version="1.0.0",
        skills=(
            [AgentSkill(id="echo", name="Echo", description="Echo input", tags=["example"])]
            if skills is None
            else skills
        ),
    )
    if agent is None:
        async def reply(text):
            return "Echo: " + text
    else:
        async def reply(text):
            response = await agent.reply(UserMsg(name="user", content=text))
            return response.get_text_content()
    handler = DefaultRequestHandler(
        agent_executor=ReplyExecutor(reply), task_store=InMemoryTaskStore(), agent_card=card,
    )
    app = Starlette(routes=[
        *create_agent_card_routes(card), *create_jsonrpc_routes(handler, rpc_url="/"),
    ])
    return app, card
