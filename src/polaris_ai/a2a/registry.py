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

"""Register A2A transports using the public Polaris Provider API."""

import asyncio
import concurrent.futures
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Event, RLock

from polaris.api.provider import ProviderAPI
from polaris.pkg.model.server import InstanceDeRegisterRequest, InstanceRegisterRequest

from polaris_ai._async import await_completion, drain_task

from ._card import (
    MAX_METADATA_VALUE_CHARS,
    META_AGENT_CARD,
    META_AGENT_NAME,
    META_PATH,
    META_TRANSPORT,
    AgentCard,
    encode_card,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class A2ATransport:
    """An already listening A2A endpoint; host is the explicit business instance address."""

    host: str
    port: int
    transport: str = "JSONRPC"
    path: str = "/"
    support_tls: bool = False


@dataclass(frozen=True)
class RegisteredInstance:
    service: str
    host: str
    port: int
    instance_id: str


class PolarisA2ARegistrar:
    """Track registrations and clean them up without closing the supplied SDKContext.

    The SDK requires ``service_token`` for register, heartbeat and deregister.
    It is distinct from the connector's authentication token. Heartbeat and
    instance-not-found re-registration are managed by ProviderAPI.register_instance.
    """

    def __init__(self, sdk_context, namespace: str = "default", *, service_token: str, ttl: int = 5):
        if sdk_context is None or sdk_context.is_destroy():
            raise ValueError("An active SDKContext is required")
        if not isinstance(service_token, str) or not service_token.strip():
            raise ValueError("service_token is required by the Polaris Provider API")
        if type(ttl) is not int or not 0 < ttl <= 0xFFFFFFFF:
            raise ValueError("ttl must be a positive uint32 number of seconds")
        self.namespace = namespace.strip() or "default"
        self.ttl = ttl
        self.service_token = service_token
        self._context = sdk_context
        self._provider = ProviderAPI(sdk_context)
        self._registered: list[RegisteredInstance] = []
        self._lock = RLock()
        self._closed = False

    @property
    def registered(self) -> tuple[RegisteredInstance, ...]:
        with self._lock:
            return tuple(self._registered)

    def _check_open(self):
        if self._closed or self._context.is_destroy():
            raise RuntimeError("A2A registrar or SDKContext is closed")

    def register(self, agent_card: AgentCard, transports: Sequence[A2ATransport]):
        """Register one instance per transport; roll back successes on partial failure."""
        return self._register(agent_card, tuple(transports))

    def _register(self, agent_card, transports, cancelled: Event | None = None):
        with self._lock:
            self._check_open()
            requests = self._requests(agent_card, transports)
            created = []
            try:
                for request in requests:
                    if cancelled is not None and cancelled.is_set():
                        raise concurrent.futures.CancelledError()
                    response = self._provider.register_instance(request)
                    instance = RegisteredInstance(
                        request.service, request.host, request.port, response.instance_id,
                    )
                    self._registered.append(instance)
                    created.append(instance)
                    if cancelled is not None and cancelled.is_set():
                        raise concurrent.futures.CancelledError()
                return tuple(created)
            except BaseException:
                self._deregister(created)
                raise

    def _requests(self, card, transports):
        payload = encode_card(card)
        if not transports:
            raise ValueError("transports must not be empty")
        requests = []
        for transport in transports:
            if not isinstance(transport, A2ATransport):
                raise ValueError("transports must contain A2ATransport objects")
            if (not isinstance(transport.host, str) or not transport.host.strip()
                    or type(transport.port) is not int or not 0 < transport.port < 65536
                    or type(transport.support_tls) is not bool
                    or not isinstance(transport.transport, str) or not transport.transport.strip()
                    or not isinstance(transport.path, str) or not transport.path.startswith("/")):
                raise ValueError("A2A transport requires a host, valid port, binding and absolute path")
            metadata = {
                META_AGENT_NAME: card.name,
                META_AGENT_CARD: payload,
                META_TRANSPORT: transport.transport,
                META_PATH: transport.path,
            }
            for name, value in metadata.items():
                # Java String.length counts UTF-16 code units, including supplementary characters.
                if len(value.encode("utf-16-le")) // 2 > MAX_METADATA_VALUE_CHARS:
                    raise ValueError(f"Metadata {name!r} exceeds the 65535 character limit")
            request = InstanceRegisterRequest(
                namespace=self.namespace, service=card.name, service_token=self.service_token,
                host=transport.host, port=transport.port, version=card.version,
                protocol="https" if transport.support_tls else "http",
                metadata=metadata, ttl=self.ttl, auto_heartbeat=True,
            )
            request.validate()
            requests.append(request)
        return requests

    def _deregister(self, instances):
        for instance in instances:
            request = InstanceDeRegisterRequest(
                namespace=self.namespace, service=instance.service, service_token=self.service_token,
                host=instance.host, port=instance.port, instance_id=instance.instance_id,
            )
            try:
                self._provider.deregister_instance(request)
            except Exception as error:
                logger.warning("Failed to deregister A2A agent %s at %s:%s: %s",
                               instance.service, instance.host, instance.port, error)
            else:
                self._registered = [item for item in self._registered if item is not instance]

    async def async_register(self, agent_card: AgentCard, transports: Sequence[A2ATransport]):
        """Run SDK sync calls off the caller loop; cancellation waits for rollback."""
        cancelled = Event()
        task = asyncio.create_task(asyncio.to_thread(
            self._register, agent_card, tuple(transports), cancelled,
        ))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            await drain_task(task)
            if not task.cancelled() and task.exception() is None:
                # Cancellation can arrive after the worker's last check, before delivery.
                cleanup = asyncio.create_task(asyncio.to_thread(self._rollback, task.result()))
                await drain_task(cleanup)
            raise

    def _rollback(self, instances):
        with self._lock:
            self._deregister(instances)

    def close(self):
        """Retry every tracked deregistration; failures remain in ``registered``."""
        with self._lock:
            self._closed = True
            self._deregister(tuple(self._registered))

    async def async_close(self):
        await await_completion(asyncio.to_thread(self.close))

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *_):
        self.close()

    async def __aenter__(self):
        self._check_open()
        return self

    async def __aexit__(self, *_):
        await self.async_close()
