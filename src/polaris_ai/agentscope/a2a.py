"""A resilient wrapper around AgentScope's native A2A client."""

import asyncio
import time

from polaris.pkg.model.service import InstanceType

from polaris_ai.metrics import PolarisCallReporter


class PolarisA2AAgent:
    """Resolve once, then rebuild the native A2A client only when needed.

    A card is resolved before the first call. Later calls reuse the native
    AgentScope ``A2AAgent`` unless the caller invalidates it or a network
    failure occurs before any response event has been delivered. Business
    errors are propagated without switching instances. The wrapper owns the
    supplied resolver and closes it together with the current client.
    """

    def __init__(self, resolver, agent_name: str, *, agent_factory=None, reporter=None,
                 caller_service: str = "", labels: str = ""):
        if resolver is None:
            raise ValueError("A PolarisA2AResolver is required")
        if not isinstance(agent_name, str) or not agent_name.strip():
            raise ValueError("agent_name is required")
        if agent_factory is None:
            from agentscope.agent import A2AAgent

            agent_factory = A2AAgent
        self._resolver = resolver
        self._agent_name = agent_name.strip()
        self._agent_factory = agent_factory
        self._reporter = reporter
        if self._reporter is None and getattr(resolver, "consumer", None) is not None:
            self._reporter = PolarisCallReporter(
                resolver.consumer,
                getattr(resolver, "namespace", "default"),
                caller_service=caller_service,
                labels=labels,
            )
        self._agent = None
        self._card = None
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def card(self):
        return self._card

    @property
    def agent(self):
        return self._agent

    def _check_open(self):
        if self._closed:
            raise RuntimeError("Polaris A2A agent is closed")

    @staticmethod
    def _is_retryable(error: BaseException) -> bool:
        if isinstance(error, (asyncio.TimeoutError, TimeoutError, OSError)):
            return True
        try:
            from a2a.client.errors import A2AClientTimeoutError
        except ImportError:
            return False
        if isinstance(error, A2AClientTimeoutError):
            return True
        try:
            from a2a.client.errors import A2AClientError
        except ImportError:
            return False
        return isinstance(error, A2AClientError) and str(error).startswith("Network communication error")

    async def _ensure_agent(self):
        self._check_open()
        if self._agent is None:
            self._card = await self._resolver.async_resolve(self._agent_name)
            self._agent = self._agent_factory(self._card)
            await self._agent.__aenter__()
        return self._agent

    async def _close_agent(self):
        if self._agent is not None:
            agent, self._agent, self._card = self._agent, None, None
            await agent.aclose()

    async def _replace_agent(self):
        await self._close_agent()
        await self._ensure_agent()

    async def reply(self, inputs):
        async with self._lock:
            agent = await self._ensure_agent()
            started_at = time.monotonic()
            final_message = None
            saw_event = False
            try:
                async for event in agent.reply_stream(inputs, yield_final_msg=True):
                    saw_event = True
                    if isinstance(event, _message_type()):
                        final_message = event
                if final_message is None:
                    raise RuntimeError("A2A agent did not produce a final message")
                await self._report_call(started_at, success=True)
                return final_message
            except BaseException as error:
                await self._report_call(
                    started_at, success=False,
                    timeout=isinstance(error, (asyncio.TimeoutError, TimeoutError)),
                )
                if saw_event or not self._is_retryable(error):
                    raise
                await self._replace_agent()
                retry_started = time.monotonic()
                try:
                    reply = await self._agent.reply(inputs)
                except BaseException as retry_error:
                    await self._report_call(
                        retry_started, success=False,
                        timeout=isinstance(retry_error, (asyncio.TimeoutError, TimeoutError)),
                    )
                    raise
                await self._report_call(retry_started, success=True)
                return reply

    async def reply_stream(self, inputs, *, yield_final_msg: bool = False):
        async with self._lock:
            agent = await self._ensure_agent()
            started_at = time.monotonic()
            yielded = False
            succeeded = False
            try:
                async for event in agent.reply_stream(inputs, yield_final_msg=yield_final_msg):
                    yielded = True
                    yield event
                succeeded = True
            except BaseException as error:
                await self._report_call(
                    started_at, success=False,
                    timeout=isinstance(error, (asyncio.TimeoutError, TimeoutError)),
                )
                if yielded or not self._is_retryable(error):
                    raise
                await self._replace_agent()
                async for event in self._agent.reply_stream(inputs, yield_final_msg=yield_final_msg):
                    yield event
                succeeded = True
            finally:
                if succeeded:
                    await self._report_call(started_at, success=True)

    async def _report_call(self, started_at, *, success, timeout=False):
        if self._reporter is None:
            return
        endpoint = self._resolver.selected_endpoint(self._agent_name)
        if endpoint is None:
            return
        host, port = endpoint
        await self._reporter.report(
            service=self._agent_name,
            host=host,
            port=port,
            method="message/send",
            instance_type=InstanceType.A2A,
            started_at=started_at,
            success=success,
            timeout=timeout,
        )

    async def observe(self, msgs):
        async with self._lock:
            agent = await self._ensure_agent()
            await agent.observe(msgs)

    async def invalidate(self):
        """Close the current client and make the next call resolve again."""
        async with self._lock:
            self._check_open()
            await self._close_agent()
            self._resolver.invalidate(self._agent_name)

    async def aclose(self):
        if self._closed:
            return
        self._closed = True
        async with self._lock:
            await self._close_agent()
            await self._resolver.async_close()

    async def __aenter__(self):
        self._check_open()
        return self

    async def __aexit__(self, *_):
        await self.aclose()


def _message_type():
    from agentscope.message import Msg

    return Msg
