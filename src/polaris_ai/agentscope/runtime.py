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

"""Compose the Polaris AgentScope adapters from application options."""

from polaris.api.log import LogOptions

from polaris_ai._async import await_completion
from polaris_ai.a2a import PolarisA2ARegistrar, PolarisA2AResolver
from polaris_ai.agentscope.config import PolarisAgentConfig
from polaris_ai.agentscope.context import PolarisAgentContext
from polaris_ai.agentscope.skill import PolarisSkillLoader


class PolarisAgentRuntime:
    """Own configured adapters while preserving borrowed-context semantics."""

    def __init__(
        self,
        config: PolarisAgentConfig,
        *,
        sdk_context=None,
        log_options: LogOptions | None = None,
    ):
        if not isinstance(config, PolarisAgentConfig):
            raise TypeError("config must be a PolarisAgentConfig")
        if not config.enabled:
            raise ValueError("Polaris AgentScope integration is disabled")
        self.config = config
        self.context = PolarisAgentContext(
            config.namespace,
            address=config.addresses,
            connector_token=config.connector_token,
            skill_address=config.skill.addresses,
            log_options=log_options,
            sdk_context=sdk_context,
        )
        self.skill_loader: PolarisSkillLoader | None = None
        self.resolver: PolarisA2AResolver | None = None
        self.registrar: PolarisA2ARegistrar | None = None
        self.mcp_resolver = None
        self._closed = False
        try:
            if config.skill.enabled:
                self.skill_loader = PolarisSkillLoader(
                    self.context.context,
                    config.namespace,
                    service_name=(
                        config.skill.mounted_service_name if config.skill.mounted_enabled else ""
                    ),
                    names=config.skill.names,
                    version=config.skill.version,
                    list_limit=config.skill.list_limit,
                    max_skills=config.skill.max_skills,
                    refresh_interval=config.skill.refresh_interval,
                )
            if config.a2a.enabled and config.a2a.discovery.enabled:
                self.resolver = PolarisA2AResolver(self.context.context, config.namespace)
            if config.a2a.enabled and config.a2a.registry.enabled:
                if not config.service_token:
                    raise ValueError("service_token is required when A2A registry is enabled")
                self.registrar = PolarisA2ARegistrar(
                    self.context.context,
                    config.namespace,
                    service_token=config.service_token,
                    ttl=config.a2a.registry.ttl,
                )
            if config.mcp.enabled:
                from polaris_ai.agentscope.mcp import PolarisMCPResolver

                self.mcp_resolver = PolarisMCPResolver(
                    self.context.context,
                    config.namespace,
                    caller_service=config.mcp.caller_service,
                    labels=config.mcp.labels,
                    protocol_version=config.mcp.protocol_version,
                    scheme=config.mcp.scheme,
                    timeout=config.mcp.timeout,
                    filter_contract=config.mcp.filter_contract,
                    headers=dict(config.mcp.headers),
                )
        except BaseException:
            self.close()
            raise

    @property
    def provider(self):
        return self.context.provider

    @property
    def consumer(self):
        return self.context.consumer

    @property
    def skill(self):
        return self.context.skill

    def _check_open(self):
        if getattr(self, "_closed", True):
            raise RuntimeError("PolarisAgentRuntime is closed")

    async def _close_adapters(self):
        if self.registrar is not None:
            await self.registrar.async_close()
        if self.resolver is not None:
            await self.resolver.async_close()
        if self.skill_loader is not None:
            await self.skill_loader.async_close()

    def _close_adapters_sync(self):
        if self.registrar is not None:
            self.registrar.close()
        if self.resolver is not None:
            self.resolver.close()
        if self.skill_loader is not None:
            self.skill_loader.close()

    def close(self):
        """Close adapters, then the shared context only if this runtime owns it."""
        if getattr(self, "_closed", True):
            return
        self._closed = True
        self._close_adapters_sync()
        self.context.close()

    async def async_close(self):
        if getattr(self, "_closed", True):
            return
        self._closed = True
        await await_completion(self._close_adapters())
        await self.context.async_close()

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
