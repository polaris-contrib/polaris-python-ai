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

"""Read-only published and mounted Skill loaders for AgentScope."""

import asyncio
import io
import logging
import re
import shutil
import stat
import tempfile
import time
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from threading import RLock

try:
    import frontmatter
    from agentscope.skill import Skill, SkillLoaderBase
except ImportError as error:
    raise ImportError(
        "PolarisSkillLoader requires pip install 'polaris-python-ai[agentscope]'."
    ) from error

from polaris.api.consumer import ConsumerAPI
from polaris.api.skill import SkillAPI
from polaris.pkg.model.service import ExtendedMetadata, GetAllInstancesRequest
from polaris.pkg.model.skill import SkillDownloadRequest, SkillListRequest

from polaris_ai._async import await_completion

logger = logging.getLogger(__name__)
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_ARCHIVE_FILES = 2048


class PolarisSkillLoader(SkillLoaderBase):
    """Load published skills, or only skills mounted on ``service_name``.

    The supplied SDKContext is borrowed. Extracted assets live until ``close``;
    persistent offline backups remain the responsibility of the SDK SkillAPI.
    ``refresh_interval`` is in seconds and request ``timeout`` is in milliseconds.
    """

    def __init__(
        self,
        sdk_context,
        namespace: str = "default",
        *,
        service_name: str = "",
        version: str = "",
        names: Sequence[str] = (),
        list_limit: int = 50,
        max_skills: int = 100,
        refresh_interval: float = 30.0,
        timeout: int = 0,
    ):
        if sdk_context is None or sdk_context.is_destroy():
            raise ValueError("An active SDKContext is required")
        if (type(list_limit) is not int or list_limit <= 0
                or type(max_skills) is not int or max_skills <= 0):
            raise ValueError("list_limit and max_skills must be positive integers")
        if not isinstance(refresh_interval, (int, float)) or refresh_interval < 0:
            raise ValueError("refresh_interval must be nonnegative")
        if type(timeout) is not int or timeout < 0:
            raise ValueError("timeout must be a nonnegative integer")
        if isinstance(names, str) or any(not isinstance(n, str) or not n.strip() for n in names):
            raise ValueError("names must be a sequence of nonempty skill names")
        if service_name and names:
            raise ValueError("names cannot be combined with service_name")
        self.namespace = namespace.strip() or "default"
        self.service_name = service_name.strip()
        self.version = version.strip()
        self.names = tuple(n.strip() for n in names)
        self.list_limit = list_limit
        self.max_skills = max_skills
        self.refresh_interval = refresh_interval
        self.timeout = timeout
        self._context = sdk_context
        self._skill_api = SkillAPI(sdk_context)
        self._consumer = ConsumerAPI(sdk_context)
        self._refs: tuple[tuple[str, str], ...] = ()
        self._refreshed_at: float | None = None
        self._cache: dict[tuple[str, str], Skill] = {}
        self._lock = asyncio.Lock()
        self._files_lock = RLock()
        self._directory: tempfile.TemporaryDirectory | None = None
        self._closed = False

    def _check_open(self):
        if self._closed or self._context.is_destroy():
            raise RuntimeError("Skill loader or SDKContext is closed")

    async def list_skills(self) -> list[Skill]:
        """Return native AgentScope Skills; failed downloads are skipped and retried later."""
        async with self._lock:
            self._check_open()
            await self._refresh_refs()
            self._check_open()
            result = []
            for name, version in self._refs:
                try:
                    result.append(await self._load_skill(name, version))
                except Exception as error:
                    self._check_open()
                    logger.warning("Failed to load skill %s/%s: %s", self.namespace, name, error)
            return result

    async def async_get_skill(self, name: str, *, version: str | None = None) -> Skill:
        """Load one skill; mounted loaders only accept names in the current mount table."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Skill name is required")
        name = name.strip()
        async with self._lock:
            self._check_open()
            resolved = self.version if version is None else version.strip()
            if self.service_name:
                await self._refresh_refs()
                mounts = dict(self._refs)
                if name not in mounts:
                    raise LookupError(f"Skill {name!r} is not mounted on {self.service_name!r}")
                resolved = mounts[name]
            return await self._load_skill(name, resolved)

    async def _refresh_refs(self):
        if self.names:
            self._refs = tuple((name, self.version) for name in self.names)
            return
        if (self._refreshed_at is not None
                and time.monotonic() - self._refreshed_at < self.refresh_interval
                and (not self.service_name or self._refs)):
            return
        refs = await self._mounted_refs() if self.service_name else await self._published_refs()
        self._check_open()
        self._refs = tuple(refs)
        self._refreshed_at = time.monotonic()

    async def _published_refs(self):
        refs = []
        offset = 0
        while len(refs) < self.max_skills:
            response = await self._skill_api.async_list_skills(SkillListRequest(
                namespace=self.namespace, offset=offset, limit=self.list_limit, timeout=self.timeout,
            ))
            if response is None or response.code not in (0, 200000):
                raise RuntimeError("Failed to list skills from Polaris")
            resources = response.resources
            if not resources:
                break
            for resource in resources:
                if resource is None or not resource.name.strip():
                    continue
                active = resource.version_info.active_version if resource.version_info else ""
                refs.append((resource.name, self.version or active or ""))
                if len(refs) >= self.max_skills:
                    break
            offset += self.list_limit
            if len(resources) < self.list_limit or offset >= response.total:
                break
        return refs

    async def _mounted_refs(self):
        response = await self._consumer.async_get_all_instances(GetAllInstancesRequest(
            namespace=self.namespace, service=self.service_name, timeout=self.timeout,
        ))
        refs = {}
        if response is None:
            return []
        for meta in response.get_extended_metadata():
            if meta.type != ExtendedMetadata.SKILL or meta.agent_skill is None:
                continue
            skill = meta.agent_skill
            raw = skill.name if skill.name.strip() else skill.id
            namespace, separator, name = raw.partition(":")
            if not separator or not namespace.strip() or not name.strip():
                logger.warning("Invalid mounted skill identity: %r", raw)
                continue
            if namespace.strip() != self.namespace:
                logger.warning("Skipping mounted skill %s outside namespace %s", raw, self.namespace)
                continue
            refs.setdefault(name.strip(), skill.version.strip() or self.version)
        return list(refs.items())

    async def _load_skill(self, name, version):
        self._check_open()
        key = (name, version)
        if key in self._cache:
            return self._cache[key]
        response = await self._skill_api.async_download_skill(SkillDownloadRequest(
            namespace=self.namespace, name=name, version=version, timeout=self.timeout, format="zip",
        ))
        if response is None or response.code not in (0, 200000) or not response.data:
            raise RuntimeError(f"Failed to download skill {name!r}")
        # Extraction is isolated from the event loop and close cannot race filesystem writes.
        return await await_completion(asyncio.to_thread(self._materialize, key, response.data))

    def _materialize(self, key, data):
        with self._files_lock:
            self._check_open()
            if key in self._cache:
                return self._cache[key]
            if self._directory is None:
                self._directory = tempfile.TemporaryDirectory(prefix="polaris-ai-skills-")
            directory = Path(tempfile.mkdtemp(dir=self._directory.name))
            try:
                root = _extract_archive(data, directory)
                markdown_path = root / "SKILL.md"
                content = frontmatter.loads(markdown_path.read_text(encoding="utf-8-sig"))
                name = content.get("name")
                description = content.get("description")
                if not name or not description:
                    raise ValueError("SKILL.md requires name and description front matter")
                skill = Skill(
                    name=str(name), description=str(description), dir=str(root),
                    markdown=content.content, updated_at=markdown_path.stat().st_mtime,
                )
                self._cache[key] = skill
                return skill
            except BaseException:
                shutil.rmtree(directory)
                raise

    def close(self):
        """Remove this loader's temporary assets without destroying the borrowed SDKContext."""
        with self._files_lock:
            self._closed = True
            self._cache.clear()
            self._refs = ()
            if self._directory is not None:
                self._directory.cleanup()
                self._directory = None

    async def async_close(self):
        await await_completion(self._close_async())

    async def _close_async(self):
        async with self._lock:
            await asyncio.to_thread(self.close)

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


def _extract_archive(data: bytes, directory: Path) -> Path:
    if len(data) > _MAX_ARCHIVE_BYTES:
        raise ValueError("Skill ZIP exceeds the 64 MiB limit")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > _MAX_ARCHIVE_FILES:
            raise ValueError("Skill ZIP exceeds the 2048 entry limit")
        if sum(entry.file_size for entry in entries) > _MAX_ARCHIVE_BYTES:
            raise ValueError("Expanded Skill ZIP exceeds the 64 MiB limit")
        paths = []
        seen = set()
        for entry in entries:
            raw = entry.orig_filename
            path = PurePosixPath(raw)
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if ("\x00" in raw or "\\" in raw or path.is_absolute() or ".." in path.parts
                    or re.match(r"^[A-Za-z]:", raw) or not path.parts
                    or mode not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"Unsafe Skill ZIP entry: {raw!r}")
            canonical = path.as_posix().casefold()
            if canonical in seen:
                raise ValueError(f"Duplicate Skill ZIP entry: {raw!r}")
            seen.add(canonical)
            paths.append((entry, path))
        definitions = [path for entry, path in paths
                       if not entry.is_dir() and path.name == "SKILL.md"]
        if len(definitions) != 1 or len(definitions[0].parts) > 2:
            raise ValueError("Skill ZIP must contain one root or top-level directory SKILL.md")
        root = definitions[0].parent
        if root.parts and any(not path.is_relative_to(root) for _, path in paths):
            raise ValueError("All Skill ZIP assets must be under the same skill root")
        for entry, path in paths:
            target = directory.joinpath(*path.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        return directory.joinpath(*root.parts)
