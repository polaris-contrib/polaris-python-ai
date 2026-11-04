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

"""Lifecycle glue between an already started A2A server and Polaris."""

from __future__ import annotations

import asyncio
import inspect

from polaris_ai._async import await_completion


class PolarisA2AServerRegistration:
    """Register an A2A endpoint after its server becomes ready.

    ``server_ready`` accepts an ``asyncio.Event``, an awaitable, or a callable
    returning an awaitable. Closing the registration closes the registrar, so
    normal exceptions and cancellation unwind through the context manager and
    trigger deregistration.
    """

    def __init__(self, registrar, agent_card, transports, *, server_ready=None):
        if registrar is None:
            raise ValueError("A PolarisA2ARegistrar is required")
        if agent_card is None:
            raise ValueError("An AgentCard is required")
        self._registrar = registrar
        self._agent_card = agent_card
        self._transports = tuple(transports)
        self._server_ready = server_ready
        self._lock = asyncio.Lock()
        self._registered = False
        self._closed = False

    @property
    def registered(self) -> bool:
        return self._registered

    async def _wait_for_server(self):
        ready = self._server_ready
        if ready is None:
            return
        if isinstance(ready, asyncio.Event):
            await ready.wait()
            return
        if inspect.isawaitable(ready):
            await ready
            return
        if callable(ready):
            result = ready()
            if inspect.isawaitable(result):
                await result
            return
        raise TypeError("server_ready must be an asyncio.Event, awaitable, or callable")

    async def async_start(self):
        async with self._lock:
            if self._closed:
                raise RuntimeError("Polaris A2A server registration is closed")
            if self._registered:
                return self
            await self._wait_for_server()
            await self._registrar.async_register(self._agent_card, self._transports)
            self._registered = True
            return self

    async def async_close(self):
        async with self._lock:
            self._closed = True
            await await_completion(self._registrar.async_close())
            if not self._registrar.registered:
                self._registered = False

    async def __aenter__(self):
        return await self.async_start()

    async def __aexit__(self, *_):
        await self.async_close()
