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

"""Register LangGraph deployments through the public Polaris Provider API."""

import asyncio
import concurrent.futures
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Event, RLock

from polaris.api.provider import ProviderAPI
from polaris.pkg.model.server import InstanceDeRegisterRequest, InstanceRegisterRequest

from polaris_ai._async import await_completion, drain_task
from polaris_ai.log import get_ai_logger

META_GRAPH_ID = "langgraph.graph-id"
META_PATH = "langgraph.path"
META_PROTOCOL = "langgraph.protocol"


@dataclass(frozen=True)
class LangGraphTransport:
    """An already listening LangGraph Server endpoint."""

    host: str
    port: int
    path: str = "/"
    graph_id: str = ""
    support_tls: bool = False


@dataclass(frozen=True)
class RegisteredInstance:
    service: str
    host: str
    port: int
    instance_id: str


class PolarisLangGraphRegistrar:
    """Track LangGraph registrations and deregister only instances it created."""

    def __init__(
        self,
        sdk_context,
        namespace: str = "default",
        *,
        service_token: str = "",
        ttl: int = 5,
        logger=None,
    ):
        if sdk_context is None or sdk_context.is_destroy():
            raise ValueError("An active SDKContext is required")
        if not isinstance(service_token, str):
            raise ValueError("service_token must be a string")
        if type(ttl) is not int or not 0 < ttl <= 0xFFFFFFFF:
            raise ValueError("ttl must be a positive uint32 number of seconds")
        self.namespace = namespace.strip() or "default"
        self.service_token = service_token.strip()
        self.ttl = ttl
        self.logger = logger if logger is not None else get_ai_logger("langgraph")
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
            raise RuntimeError("LangGraph registrar or SDKContext is closed")

    def register(
        self,
        service: str,
        transports: Sequence[LangGraphTransport],
        *,
        version: str = "",
    ):
        """Register one instance per LangGraph endpoint."""
        return self._register(service, tuple(transports), version)

    def _register(self, service, transports, version="", cancelled: Event | None = None):
        if not isinstance(service, str) or not service.strip():
            raise ValueError("service is required")
        service = service.strip()
        with self._lock:
            self._check_open()
            requests = self._requests(service, transports, version.strip())
            created = []
            self.logger.debug(
                "Registering LangGraph service: namespace=%s service=%s endpoints=%d",
                self.namespace,
                service,
                len(requests),
            )
            try:
                for request in requests:
                    if cancelled is not None and cancelled.is_set():
                        raise concurrent.futures.CancelledError()
                    response = self._provider.register_instance(request)
                    instance = RegisteredInstance(
                        request.service,
                        request.host,
                        request.port,
                        response.instance_id,
                    )
                    self._registered.append(instance)
                    created.append(instance)
                    if cancelled is not None and cancelled.is_set():
                        raise concurrent.futures.CancelledError()
                self.logger.info(
                    "Registered LangGraph service %s/%s with %d endpoint(s)",
                    self.namespace,
                    service,
                    len(created),
                )
                return tuple(created)
            except BaseException:
                self.logger.warning_throttled(
                    ("register-rollback", service),
                    "Rolling back %d LangGraph registration(s) for %s/%s",
                    len(created),
                    self.namespace,
                    service,
                )
                self._deregister(created)
                raise

    def _requests(self, service, transports, version):
        if not transports:
            raise ValueError("transports must not be empty")
        requests = []
        for transport in transports:
            if not isinstance(transport, LangGraphTransport):
                raise ValueError("transports must contain LangGraphTransport objects")
            if (
                not isinstance(transport.host, str)
                or not transport.host.strip()
                or type(transport.port) is not int
                or not 0 < transport.port < 65536
                or type(transport.support_tls) is not bool
                or not isinstance(transport.path, str)
                or not transport.path.startswith("/")
                or not isinstance(transport.graph_id, str)
            ):
                raise ValueError("LangGraphTransport requires host, valid port and absolute path")
            protocol = "https" if transport.support_tls else "http"
            metadata = {
                META_GRAPH_ID: transport.graph_id.strip() or service,
                META_PATH: transport.path,
                META_PROTOCOL: protocol,
            }
            request = InstanceRegisterRequest(
                namespace=self.namespace,
                service=service,
                service_token=self.service_token,
                host=transport.host.strip(),
                port=transport.port,
                version=version,
                protocol=protocol,
                metadata=metadata,
                ttl=self.ttl,
                auto_heartbeat=True,
            )
            request.validate()
            requests.append(request)
        return requests

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
                    "Failed to deregister LangGraph service %s at %s:%s: %s",
                    instance.service,
                    instance.host,
                    instance.port,
                    error,
                )
            else:
                self._registered = [item for item in self._registered if item is not instance]

    async def async_register(
        self,
        service: str,
        transports: Sequence[LangGraphTransport],
        *,
        version: str = "",
    ):
        cancelled = Event()
        task = asyncio.create_task(
            asyncio.to_thread(self._register, service, tuple(transports), version, cancelled)
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
            self._deregister(instances)

    def close(self):
        """Retry deregistration for every instance still tracked by this registrar."""
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
