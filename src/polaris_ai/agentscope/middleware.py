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

"""AgentScope middleware helpers for Polaris-backed agents."""

import logging
from weakref import WeakKeyDictionary

from agentscope.middleware import MiddlewareBase
from agentscope.skill import SkillLoaderBase

logger = logging.getLogger(__name__)

_SHARED_SNAPSHOT_LOADERS = WeakKeyDictionary()


class _SnapshotSkillLoader(SkillLoaderBase):
    """Expose the middleware's last successful Skill snapshot to a Toolkit."""

    def __init__(self):
        self.last_skills = ()

    async def list_skills(self):
        return list(self.last_skills)


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
        snapshot = _SHARED_SNAPSHOT_LOADERS.get(loader)
        if snapshot is None:
            snapshot = _SnapshotSkillLoader()
            _SHARED_SNAPSHOT_LOADERS[loader] = snapshot
        self._snapshot_loader = snapshot

    async def on_reply(self, agent, input_kwargs, next_handler):
        try:
            self.last_skills = tuple(await self.loader.list_skills())
        except Exception as error:
            logger.warning("Failed to refresh Polaris Skills before reply: %s", error)
        else:
            self._snapshot_loader.last_skills = self.last_skills
        self._sync_toolkit(agent)
        async for event in next_handler():
            yield event

    def _sync_toolkit(self, agent):
        toolkit = getattr(agent, "toolkit", None)
        if toolkit is None:
            return
        for group in getattr(toolkit, "tool_groups", ()):
            if group.name != "basic":
                continue
            for index, item in enumerate(group.skills_or_loaders):
                if item is self._snapshot_loader:
                    return
                if item is self.loader:
                    group.skills_or_loaders[index] = self._snapshot_loader
                    return
