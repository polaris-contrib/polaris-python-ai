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

"""Sticky AgentCard resolution using public Polaris discovery APIs."""

import asyncio
import logging
from dataclasses import dataclass
from threading import RLock

from google.protobuf.json_format import ParseError
from polaris.api.consumer import ConsumerAPI
from polaris.pkg.model.error import SDKError
from polaris.pkg.model.service import GetHealthyInstancesRequest

from polaris_ai._async import await_completion

from ._card import META_AGENT_CARD, AgentCard, decode_card

logger = logging.getLogger(__name__)


class AgentCardNotFoundError(LookupError):
    """Discovery succeeded but no healthy instance supplied a usable matching AgentCard."""


@dataclass(frozen=True)
class _CachedCard:
    host: str
    port: int
    card: AgentCard


class PolarisA2AResolver:
    """Resolve native AgentCards, retaining the selected healthy host and port.

    Every lookup refreshes discovery and decodes the selected instance's metadata.
    A Polaris SDKError can reuse the last successful card; a successful empty
    discovery raises AgentCardNotFoundError. Card URLs are preserved as registered.
    """

    def __init__(self, sdk_context, namespace: str = "default", *, timeout: int = 0):
        if sdk_context is None or sdk_context.is_destroy():
            raise ValueError("An active SDKContext is required")
        if type(timeout) is not int or timeout < 0:
            raise ValueError("timeout must be a nonnegative integer")
        self.namespace = namespace.strip() or "default"
        self.timeout = timeout
        self._context = sdk_context
        self._consumer = ConsumerAPI(sdk_context)
        self._cache: dict[str, _CachedCard] = {}
        self._lock = RLock()
        self._closed = False

    def _check_open(self):
        if self._closed or self._context.is_destroy():
            raise RuntimeError("A2A resolver or SDKContext is closed")

    def resolve(self, agent_name: str) -> AgentCard:
        """Return the latest card for the selected instance or select the first usable peer."""
        if not isinstance(agent_name, str) or not agent_name.strip():
            raise ValueError("agent_name is required")
        agent_name = agent_name.strip()
        with self._lock:
            self._check_open()
            cached = self._cache.get(agent_name)
            try:
                response = self._consumer.get_healthy_instances(GetHealthyInstancesRequest(
                    namespace=self.namespace, service=agent_name, timeout=self.timeout,
                    exclude_offline_service=True,
                ))
            except SDKError:
                if cached is None:
                    raise
                logger.warning("Failed to refresh agent %s; reusing %s:%s",
                               agent_name, cached.host, cached.port)
                return cached.card
            instances = [] if response is None else response.get_instances()
            instances = [i for i in instances if i.is_healthy() and not i.is_isolated()]
            if cached is not None:
                sticky = [i for i in instances
                          if (i.get_host(), i.get_port()) == (cached.host, cached.port)]
                instances = sticky + [i for i in instances if i not in sticky]
            for instance in instances:
                payload = instance.get_metadata().get(META_AGENT_CARD, "")
                try:
                    card = decode_card(payload)
                except (ValueError, TypeError, ParseError) as error:
                    logger.warning("Skipping invalid AgentCard for %s at %s:%s: %s",
                                   agent_name, instance.get_host(), instance.get_port(), error)
                    continue
                if card.name != agent_name:
                    logger.warning("Skipping AgentCard %r while resolving %r", card.name, agent_name)
                    continue
                if not any(i.url.strip() and i.protocol_binding.strip()
                           for i in card.supported_interfaces):
                    logger.warning("Skipping endpoint-less AgentCard for %s", agent_name)
                    continue
                self._cache[agent_name] = _CachedCard(instance.get_host(), instance.get_port(), card)
                return card
            raise AgentCardNotFoundError(f"No usable AgentCard for {self.namespace}/{agent_name}")

    async def async_resolve(self, agent_name: str) -> AgentCard:
        return await await_completion(asyncio.to_thread(self.resolve, agent_name))

    def invalidate(self, agent_name: str):
        with self._lock:
            self._cache.pop(agent_name, None)

    def invalidate_all(self):
        with self._lock:
            self._cache.clear()

    @property
    def consumer(self):
        return self._consumer

    def selected_endpoint(self, agent_name: str):
        """Return the sticky instance host/port for an already-resolved Agent."""
        with self._lock:
            cached = self._cache.get(agent_name)
            return None if cached is None else (cached.host, cached.port)

    def close(self):
        """Clear local cards while leaving the borrowed context available."""
        with self._lock:
            self._closed = True
            self._cache.clear()

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
