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

"""A2A application with one streaming AgentScope Agent per context."""

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentSkill, Part, Task, TaskState, TaskStatus
from agentscope.event import TextBlockDeltaEvent
from agentscope.message import UserMsg
from starlette.applications import Starlette

from polaris_ai.agentscope import build_agent_card


class StreamingAgentExecutor(AgentExecutor):
    """Build one Agent per A2A context and stream text deltas as artifacts."""

    def __init__(self, agent_factory):
        self.agent_factory = agent_factory
        self.agents = {}

    async def execute(self, context, event_queue):
        if context.task_id is None or context.context_id is None:
            raise RuntimeError("A2A server did not assign Task/context IDs")
        agent = self.agents.get(context.context_id)
        if agent is None:
            agent = self.agent_factory()
            self.agents[context.context_id] = agent

        await event_queue.enqueue_event(
            Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            )
        )
        updater = TaskUpdater(
            event_queue,
            task_id=context.task_id,
            context_id=context.context_id,
        )
        await updater.start_work()
        artifact_id = f"{context.task_id}-reply"
        pending = None
        started = False
        async for event in agent.reply_stream(
            UserMsg(name="user", content=context.get_user_input()),
        ):
            if not isinstance(event, TextBlockDeltaEvent):
                continue
            if pending is not None:
                await updater.add_artifact(
                    [Part(text=pending)],
                    artifact_id=artifact_id,
                    append=started,
                    last_chunk=False,
                )
                started = True
            pending = event.delta
        if pending is not None:
            await updater.add_artifact(
                [Part(text=pending)],
                artifact_id=artifact_id,
                append=started,
                last_chunk=True,
            )
        await updater.complete()

    async def cancel(self, context, event_queue):
        await TaskUpdater(
            event_queue,
            task_id=context.task_id,
            context_id=context.context_id,
        ).cancel()


def create_streaming_app(service, base_url, agent_factory):
    card = build_agent_card(
        name=service,
        url=base_url,
        description="Streaming AgentScope tool-calling agent registered in Polaris",
        version="1.0.0",
        skills=[
            AgentSkill(
                id="tools",
                name="Tools",
                description="Weather, arithmetic and current-time tools",
                tags=["tools", "streaming"],
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=StreamingAgentExecutor(agent_factory),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = Starlette(
        routes=[
            *create_agent_card_routes(card),
            *create_jsonrpc_routes(handler, rpc_url="/"),
        ]
    )
    return app, card
