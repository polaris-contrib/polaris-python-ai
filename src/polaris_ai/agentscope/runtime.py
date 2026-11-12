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
from polaris_ai.agentscope.middleware import (
    PolarisDynamicSkillMiddleware,
    get_shared_snapshot_loader,
)
from polaris_ai.agentscope.skill import PolarisSkillLoader
from polaris_ai.log import PolarisAILogOptions, configure_ai_logging


class PolarisAgentRuntime:
    """Own configured adapters while preserving borrowed-context semantics."""

    def __init__(
        self,
        config: PolarisAgentConfig,
        *,
        sdk_context=None,
        log_options: LogOptions | None = None,
        ai_log_options: PolarisAILogOptions | None = None,
    ):
        if not isinstance(config, PolarisAgentConfig):
            raise TypeError("config must be a PolarisAgentConfig")
        if not config.enabled:
            raise ValueError("Polaris AgentScope integration is disabled")
        self.config = config
        self.context = None
        self.ai_logger = None
        self.skill_loader: PolarisSkillLoader | None = None
        self.resolver: PolarisA2AResolver | None = None
        self.registrar: PolarisA2ARegistrar | None = None
        self.mcp_resolver = None
        self._skill_toolkit = None
        self._closed = False
        try:
            self.context = PolarisAgentContext(
                config.namespace,
                address=config.addresses,
                connector_token=config.connector_token,
                skill_address=config.skill.addresses,
                log_options=log_options,
                sdk_context=sdk_context,
            )
            if ai_log_options is not None:
                client_id_getter = getattr(self.context.context, "get_client_id", None)
                client_id = (
                    client_id_getter() if callable(client_id_getter)
                    else f"runtime-{id(self.context.context)}"
                )
                self.ai_logger = configure_ai_logging(client_id, ai_log_options)
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
                    logger=self._category_logger("skill"),
                )
            if config.a2a.enabled and config.a2a.discovery.enabled:
                self.resolver = PolarisA2AResolver(
                    self.context.context, config.namespace,
                    logger=self._category_logger("a2a"),
                )
            if config.a2a.enabled and config.a2a.registry.enabled:
                self.registrar = PolarisA2ARegistrar(
                    self.context.context,
                    config.namespace,
                    service_token=config.service_token,
                    ttl=config.a2a.registry.ttl,
                    registration_port=config.a2a.registry.registration_port,
                    logger=self._category_logger("a2a"),
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
                    logger=self._category_logger("mcp"),
                    metrics_logger=self._category_logger("metrics"),
                )
            if self.ai_logger is not None:
                self.ai_logger.get_logger("base").info(
                    "Initialized Polaris AI runtime: namespace=%s skill=%s "
                    "a2aRegistry=%s a2aDiscovery=%s mcp=%s",
                    config.namespace, config.skill.enabled,
                    config.a2a.enabled and config.a2a.registry.enabled,
                    config.a2a.enabled and config.a2a.discovery.enabled,
                    config.mcp.enabled,
                )
                self.ai_logger.get_logger("base").debug(
                    "Polaris AI runtime settings: addresses=%s skillMounted=%s "
                    "skillNames=%d mcpScheme=%s",
                    config.addresses, config.skill.mounted_enabled,
                    len(config.skill.names), config.mcp.scheme or "<instance>",
                )
        except BaseException:
            self.close()
            raise

    def _category_logger(self, category):
        return self.ai_logger.get_logger(category) if self.ai_logger is not None else None

    def _log_close_start(self):
        ai_logger = getattr(self, "ai_logger", None)
        if ai_logger is None:
            return
        ai_logger.get_logger("base").info(
            "Closing Polaris AI runtime: namespace=%s", self.config.namespace,
        )

    @property
    def provider(self):
        return self.context.provider

    @property
    def consumer(self):
        return self.context.consumer

    @property
    def skill(self):
        return self.context.skill

    @property
    def skill_toolkit(self):
        """Build the Toolkit selected by ``skill.attach_to_agent``."""
        self._check_open()
        if (not self.config.skill.enabled or not self.config.skill.attach_to_agent
                or self.skill_loader is None):
            return None
        if self._skill_toolkit is None:
            from agentscope.tool import Toolkit

            self._skill_toolkit = Toolkit(skills_or_loaders=[self.skill_loader])
        return self._skill_toolkit

    def _attach_skill_loader(self, toolkit):
        for group in toolkit.tool_groups:
            if group.name == "basic":
                snapshot = get_shared_snapshot_loader(self.skill_loader)
                if snapshot is not None:
                    normalized = []
                    snapshot_present = False
                    for item in group.skills_or_loaders:
                        if item is self.skill_loader:
                            continue
                        if item is snapshot:
                            if snapshot_present:
                                continue
                            snapshot_present = True
                        normalized.append(item)
                    if not snapshot_present:
                        normalized.append(snapshot)
                    group.skills_or_loaders[:] = normalized
                    return
                if self.skill_loader not in group.skills_or_loaders:
                    group.skills_or_loaders.append(self.skill_loader)
                return
        raise ValueError("Toolkit has no basic tool group")

    def create_agent(self, *, name: str, system_prompt: str, model, toolkit=None,
                     middlewares=(), **kwargs):
        """Create a native Agent with the configured Polaris Skill attachment."""
        self._check_open()
        from agentscope.agent import Agent

        selected_toolkit = toolkit
        selected_middlewares = list(middlewares)
        if (self.config.skill.enabled and self.config.skill.attach_to_agent
                and self.skill_loader is not None):
            if selected_toolkit is None:
                selected_toolkit = self.skill_toolkit
            else:
                self._attach_skill_loader(selected_toolkit)
            selected_middlewares.append(PolarisDynamicSkillMiddleware(
                self.skill_loader,
                logger=self._category_logger("agentscope"),
            ))
        return Agent(
            name=name,
            system_prompt=system_prompt,
            model=model,
            toolkit=selected_toolkit,
            middlewares=selected_middlewares,
            **kwargs,
        )

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

    async def _close_all_async(self):
        try:
            await self._close_adapters()
        finally:
            try:
                context = getattr(self, "context", None)
                if context is not None:
                    await context.async_close()
            finally:
                ai_logger = getattr(self, "ai_logger", None)
                if ai_logger is not None:
                    await ai_logger.async_close()

    def close(self):
        """Close adapters, then the shared context only if this runtime owns it."""
        if getattr(self, "_closed", True):
            return
        self._log_close_start()
        self._closed = True
        try:
            self._close_adapters_sync()
        finally:
            try:
                context = getattr(self, "context", None)
                if context is not None:
                    context.close()
            finally:
                ai_logger = getattr(self, "ai_logger", None)
                if ai_logger is not None:
                    ai_logger.close()

    async def async_close(self):
        if getattr(self, "_closed", True):
            return
        self._log_close_start()
        self._closed = True
        await await_completion(self._close_all_async())

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
