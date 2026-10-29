"""AgentScope middleware helpers for Polaris-backed agents."""

import logging

from agentscope.middleware import MiddlewareBase
from agentscope.skill import SkillLoaderBase

logger = logging.getLogger(__name__)


class PolarisDynamicSkillMiddleware(MiddlewareBase):
    """Refresh Polaris Skills before each reply while reusing one Agent.

    The loader applies its refresh interval, so replies within that interval do
    not query Polaris again. Refresh failures are logged and the reply proceeds
    with the loader's last successful state.
    """

    def __init__(self, loader: SkillLoaderBase):
        if not isinstance(loader, SkillLoaderBase):
            raise TypeError("loader must implement SkillLoaderBase")
        self.loader = loader
        self.last_skills = ()

    async def on_reply(self, agent, input_kwargs, next_handler):
        try:
            self.last_skills = tuple(await self.loader.list_skills())
        except Exception as error:
            logger.warning("Failed to refresh Polaris Skills before reply: %s", error)
        async for event in next_handler():
            yield event
