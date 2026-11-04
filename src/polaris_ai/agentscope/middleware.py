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

from weakref import WeakKeyDictionary

from agentscope.middleware import MiddlewareBase
from agentscope.skill import SkillLoaderBase

from polaris_ai.log import get_ai_logger

_SHARED_SNAPSHOT_LOADERS = WeakKeyDictionary()


def get_shared_snapshot_loader(loader):
    """Return the snapshot associated with a loader, if middleware created it."""
    return _SHARED_SNAPSHOT_LOADERS.get(loader)


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

    def __init__(self, loader: SkillLoaderBase, *, logger=None):
        if not isinstance(loader, SkillLoaderBase):
            raise TypeError("loader must implement SkillLoaderBase")
        self.loader = loader
        self.logger = logger if logger is not None else get_ai_logger("agentscope")
        self.last_skills = ()
        snapshot = get_shared_snapshot_loader(loader)
        if snapshot is None:
            snapshot = _SnapshotSkillLoader()
            _SHARED_SNAPSHOT_LOADERS[loader] = snapshot
        self._snapshot_loader = snapshot

    async def on_reply(self, agent, input_kwargs, next_handler):
        self.logger.debug("Refreshing Polaris Skills before Agent reply")
        try:
            self.last_skills = tuple(await self.loader.list_skills())
        except Exception as error:
            self.logger.warning_throttled(
                ("refresh", id(self.loader)),
                "Failed to refresh Polaris Skills before reply: %s", error,
            )
        else:
            self._snapshot_loader.last_skills = self.last_skills
            self.logger.debug(
                "Refreshed Polaris Skill snapshot: count=%d names=%s",
                len(self.last_skills), [skill.name for skill in self.last_skills],
            )
        self._sync_toolkit(agent)
        async for event in next_handler():
            yield event

    def _sync_toolkit(self, agent):
        toolkit = getattr(agent, "toolkit", None)
        if toolkit is None:
            self.logger.debug("Agent has no Toolkit; skipping Polaris Skill snapshot binding")
            return
        for group in getattr(toolkit, "tool_groups", ()):
            if group.name != "basic":
                continue
            for index, item in enumerate(group.skills_or_loaders):
                if item is self._snapshot_loader:
                    self.logger.debug(
                        "Polaris Skill snapshot already bound to Toolkit: category=%s",
                        group.name,
                    )
                    return
                if item is self.loader:
                    group.skills_or_loaders[index] = self._snapshot_loader
                    self.logger.debug(
                        "Bound Polaris Skill snapshot to Toolkit: category=%s index=%d",
                        group.name, index,
                    )
                    return
