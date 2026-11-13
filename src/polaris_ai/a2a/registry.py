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

"""Register one Polaris instance for each instance-level A2A AgentCard."""

import asyncio
import concurrent.futures
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Event, RLock
from typing import Any

from polaris.api.provider import ProviderAPI
from polaris.pkg.model.server import InstanceDeRegisterRequest, InstanceRegisterRequest

from polaris_ai._async import await_completion, drain_task
from polaris_ai.log import get_ai_logger

from ._card import (
    A2A_VERSION_10,
    MAX_METADATA_VALUE_CHARS,
    META_A2A_VERSION,
    META_AGENT_CARD,
    META_AGENT_NAME,
    AgentCard,
    normalize_ip_address,
    prepare_agent_card,
)


@dataclass(frozen=True)
class A2ATransport:
    """Deprecated migration input; AgentCard interfaces are the source of truth."""

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


def validate_registration_port(port: int) -> int:
    """Validate the registration identity port accepted by the Core SDK."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("registration_port must be an integer in 1..65535")
    return port


class PolarisA2ARegistrar:
    """Track instance-level AgentCard registrations without owning the SDK context."""

    def __init__(
        self,
        sdk_context,
        namespace: str = "default",
        *,
        service_token: str = "",
        ttl: int = 5,
        registration_port: int = 1,
        logger=None,
    ):
        if sdk_context is None or sdk_context.is_destroy():
            raise ValueError("An active SDKContext is required")
        if not isinstance(service_token, str):
            raise ValueError("service_token must be a string")
        if type(ttl) is not int or not 0 < ttl <= 0xFFFFFFFF:
            raise ValueError("ttl must be a positive uint32 number of seconds")
        self.namespace = namespace.strip() or "default"
        self.ttl = ttl
        self.service_token = service_token.strip()
        self.registration_port = validate_registration_port(registration_port)
        self.logger = logger if logger is not None else get_ai_logger("a2a")
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

    def register(
        self,
        agent_card: AgentCard | dict[str, Any] | str,
        transports: Sequence[A2ATransport] | None = None,
        *,
        a2a_version: str = A2A_VERSION_10,
    ):
        """Register one AgentCard as one Polaris instance."""
        return self._register(agent_card, transports, a2a_version)

    def _register(
        self,
        agent_card,
        transports,
        a2a_version,
        cancelled: Event | None = None,
    ):
        with self._lock:
            self._check_open()
            prepared, request = self._request(
                agent_card,
                transports,
                a2a_version,
            )
            self.logger.debug(
                "Registering A2A AgentCard: namespace=%s service=%s host=%s "
                "registrationPort=%d schemaVersion=%s",
                self.namespace,
                prepared.card.name,
                prepared.host,
                self.registration_port,
                prepared.a2a_version,
            )
            created = []
            try:
                if cancelled is not None and cancelled.is_set():
                    raise concurrent.futures.CancelledError()
                response = self._provider.register_instance(request)
                instance = RegisteredInstance(
                    request.service,
                    request.host,
                    request.port,
                    response.instance_id,
                )
                identity = (instance.service, instance.host, instance.port)
                self._registered = [
                    item
                    for item in self._registered
                    if (item.service, item.host, item.port) != identity
                ]
                self._registered.append(instance)
                created.append(instance)
                if cancelled is not None and cancelled.is_set():
                    raise concurrent.futures.CancelledError()
                self.logger.info(
                    "Registered A2A agent %s/%s with AgentCard schema %s",
                    self.namespace,
                    prepared.card.name,
                    prepared.a2a_version,
                )
                return tuple(created)
            except BaseException:
                if created:
                    self.logger.warning_throttled(
                        ("register-rollback", prepared.card.name),
                        "Rolling back %d AgentCard registration(s) for %s/%s",
                        len(created),
                        self.namespace,
                        prepared.card.name,
                    )
                    self._deregister(created)
                raise

    def _request(
        self,
        agent_card,
        transports: Sequence[A2ATransport] | None,
        a2a_version: str,
    ):
        prepared = prepare_agent_card(agent_card, a2a_version=a2a_version)
        self._validate_legacy_transports(prepared.host, transports)
        registration_port = validate_registration_port(self.registration_port)
        metadata = {
            META_AGENT_NAME: prepared.card.name,
            META_AGENT_CARD: prepared.payload,
            META_A2A_VERSION: prepared.a2a_version,
        }
        for name, value in metadata.items():
            if len(value.encode("utf-16-le")) // 2 > MAX_METADATA_VALUE_CHARS:
                raise ValueError(f"Metadata {name!r} exceeds the 65535 character limit")
        request = InstanceRegisterRequest(
            namespace=self.namespace,
            service=prepared.card.name,
            service_token=self.service_token,
            host=prepared.host,
            port=registration_port,
            version=prepared.card.version,
            protocol="",
            metadata=metadata,
            ttl=self.ttl,
            auto_heartbeat=True,
        )
        request.validate()
        return prepared, request

    @staticmethod
    def _validate_legacy_transports(
        card_host: str,
        transports: Sequence[A2ATransport] | None,
    ):
        if transports is None:
            return
        warnings.warn(
            "transport registration is deprecated; AgentCard is the endpoint source of truth",
            DeprecationWarning,
            stacklevel=4,
        )
        transport_list = tuple(transports)
        if len(transport_list) != 1:
            raise ValueError("the compatibility API accepts exactly one transport")
        transport = transport_list[0]
        if not isinstance(transport, A2ATransport):
            raise ValueError("transports must contain A2ATransport objects")
        if normalize_ip_address(transport.host) != card_host:
            raise ValueError("compatibility transport host must match the AgentCard IP")

    def _deregister(self, instances):
        for instance in instances:
            request = InstanceDeRegisterRequest(
                namespace=self.namespace,
                service=instance.service,
                service_token=self.service_token,
                host=instance.host,
                port=instance.port,
                instance_id=instance.instance_id,
            )
            try:
                self._provider.deregister_instance(request)
            except Exception as error:
                self.logger.warning_throttled(
                    ("deregister", instance.service, instance.host, instance.port),
                    "Failed to deregister A2A agent %s at %s:%s: %s",
                    instance.service,
                    instance.host,
                    instance.port,
                    error,
                )
            else:
                self.logger.debug(
                    "Deregistered A2A instance: service=%s host=%s port=%s instanceId=%s",
                    instance.service,
                    instance.host,
                    instance.port,
                    instance.instance_id,
                )
                self._registered = [item for item in self._registered if item is not instance]

    async def async_register(
        self,
        agent_card: AgentCard | dict[str, Any] | str,
        transports: Sequence[A2ATransport] | None = None,
        *,
        a2a_version: str = A2A_VERSION_10,
    ):
        """Run the sync registration off-loop and roll back on delivery cancellation."""
        cancelled = Event()
        task = asyncio.create_task(
            asyncio.to_thread(
                self._register,
                agent_card,
                transports,
                a2a_version,
                cancelled,
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            await drain_task(task)
            if not task.cancelled() and task.exception() is None:
                cleanup = asyncio.create_task(asyncio.to_thread(self._rollback, task.result()))
                await drain_task(cleanup)
            raise

    def _rollback(self, instances):
        with self._lock:
            owned = [
                instance
                for instance in instances
                if any(item is instance for item in self._registered)
            ]
            self._deregister(owned)

    def close(self):
        """Retry every tracked deregistration while leaving the context open."""
        with self._lock:
            self._closed = True
            self.logger.debug(
                "Closing A2A registrar: namespace=%s remaining=%d",
                self.namespace,
                len(self._registered),
            )
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
