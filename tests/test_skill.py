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

import asyncio
import io
import stat
import zipfile
from pathlib import Path
from threading import Event
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import pytest

pytest.importorskip("agentscope.skill")

from agentscope.skill import SkillLoaderBase
from agentscope.tool import Toolkit
from polaris.pkg.model.skill import (
    SkillDownloadResponse,
    SkillListResponse,
    SkillResource,
    SkillVersionInfo,
)

from polaris_ai.agentscope import PolarisSkillLoader
from tests._support import FakeContext, FakeEngine, skill_zip, snapshot


class SkillTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.context = FakeContext(self.engine)
        self.loaders = []

    def tearDown(self):
        for loader in self.loaders:
            loader.close()

    def loader(self, **kwargs):
        loader = PolarisSkillLoader(self.context, **kwargs)
        self.loaders.append(loader)
        return loader

    def download(self, name="weather", version="v1", data=None):
        self.engine.downloads[(name, version)] = SkillDownloadResponse(
            version=version, content_type="application/zip", data=data or skill_zip(name=name),
        )

    def resources(self, *names):
        return [SkillResource(name=n, version_info=SkillVersionInfo(active_version="v1"))
                for n in names]

    async def test_native_toolkit_loads_assets_and_version_cache(self):
        self.engine.pages = [SkillListResponse(total=1, resources=self.resources("weather"))]
        self.download()
        loader = self.loader()
        self.assertIsInstance(loader, SkillLoaderBase)
        toolkit = Toolkit(skills_or_loaders=[loader])
        instructions = await toolkit.get_skill_instructions()
        self.assertIn("weather", instructions)
        first = (await loader.list_skills())[0]
        second = (await loader.list_skills())[0]
        self.assertIs(first, second)
        self.assertEqual("Use weather.txt.", first.markdown.strip())
        self.assertEqual("weather reference", (Path(first.dir) / "weather.txt").read_text())
        self.assertEqual(["list_skills", "download_skill"], [m for m, _ in self.engine.skill_calls])
        self.assertEqual("zip", self.engine.skill_calls[1][1].format)

    async def test_pagination_caps_and_fixed_version_wins(self):
        self.engine.pages = [
            SkillListResponse(total=5, resources=self.resources("a", "b")),
            SkillListResponse(total=5, resources=self.resources("c", "d")),
        ]
        for name in "abc":
            self.download(name, "fixed")
        result = await self.loader(version="fixed", list_limit=2, max_skills=3).list_skills()
        self.assertEqual(["a", "b", "c"], [s.name for s in result])
        calls = [r for m, r in self.engine.skill_calls if m == "list_skills"]
        self.assertEqual([0, 2], [r.offset for r in calls])
        self.assertEqual([2, 2], [r.limit for r in calls])

    async def test_list_ttl_refreshes_and_loads_new_active_version(self):
        resource1 = self.resources("weather")
        resource2 = [SkillResource(name="weather", version_info=SkillVersionInfo(active_version="v2"))]
        self.engine.pages = [SkillListResponse(1, resource1), SkillListResponse(1, resource2)]
        self.download()
        self.download(version="v2")
        loader = self.loader()
        with patch("polaris_ai.agentscope.skill.time.monotonic", return_value=10):
            first = (await loader.list_skills())[0]
        with patch("polaris_ai.agentscope.skill.time.monotonic", return_value=39):
            self.assertIs(first, (await loader.list_skills())[0])
        with patch("polaris_ai.agentscope.skill.time.monotonic", return_value=40):
            self.assertIsNot(first, (await loader.list_skills())[0])

    async def test_configured_names_skip_list_and_active_key_is_distinct(self):
        self.download(version="")
        self.download(version="v1")
        loader = self.loader(names=["weather"])
        active = (await loader.list_skills())[0]
        fixed = await loader.async_get_skill("weather", version="v1")
        self.assertIsNot(active, fixed)
        self.assertEqual(["download_skill", "download_skill"], [m for m, _ in self.engine.skill_calls])

    async def test_mounted_names_parse_first_colon_and_keep_first_version(self):
        self.engine.snapshot = snapshot(mounts=[
            ("default:weather:city", "mounted", ""),
            ("default:weather:city", "duplicate", ""),
            ("other:weather", "v1", ""),
            ("invalid", "v1", ""),
            ("", "", "default:fallback"),
        ])
        self.download("weather:city", "mounted")
        self.download("fallback", "fixed")
        loader = self.loader(service_name="weather-agent", version="fixed")
        self.assertEqual(["weather:city", "fallback"], [s.name for s in await loader.list_skills()])
        await loader.list_skills()
        self.assertEqual(1, len(self.engine.discovery_calls))
        self.assertFalse(any(m == "list_skills" for m, _ in self.engine.skill_calls))
        with self.assertRaises(LookupError):
            await loader.async_get_skill("unmounted")

    async def test_empty_mounts_are_requeried_and_empty_published_list_is_cached(self):
        loader = self.loader(service_name="weather-agent")
        self.assertEqual([], await loader.list_skills())
        self.assertEqual([], await loader.list_skills())
        self.assertEqual(2, len(self.engine.discovery_calls))
        self.engine.pages = [SkillListResponse(0, [])]
        published = self.loader()
        self.assertEqual([], await published.list_skills())
        self.assertEqual([], await published.list_skills())
        self.assertEqual(1, len(self.engine.skill_calls))

    async def test_failed_list_does_not_cache_or_fallback_to_old_refs(self):
        self.engine.pages = [RuntimeError("offline"), SkillListResponse(0, [])]
        loader = self.loader()
        with self.assertRaisesRegex(RuntimeError, "offline"):
            await loader.list_skills()
        self.assertEqual([], await loader.list_skills())
        self.assertEqual(2, len(self.engine.skill_calls))

    async def test_failed_download_is_skipped_and_retried(self):
        self.engine.downloads[("weather", "v1")] = RuntimeError("download offline")
        loader = self.loader(names=["weather"], version="v1")
        self.assertEqual([], await loader.list_skills())
        self.download()
        self.assertEqual("weather", (await loader.list_skills())[0].name)
        self.assertEqual(2, len(self.engine.skill_calls))

    async def test_nested_archive_and_bom_frontmatter(self):
        self.download(data=skill_zip("weather/", markdown=(
            "\ufeff---\nname: weather\ndescription: Weather lookup\n---\nRead references\n"
        )))
        skill = (await self.loader(names=["weather"], version="v1").list_skills())[0]
        self.assertTrue(Path(skill.dir).name == "weather")
        self.assertTrue((Path(skill.dir) / "weather.txt").is_file())

    async def test_unsafe_archives_are_rejected_and_not_cached(self):
        loader = self.loader(names=["weather"], version="v1")
        for path in ("../escape", "/escape", "C:/escape", "a\\escape"):
            with self.subTest(path=path):
                entry = zipfile.ZipInfo("entry")
                entry.filename = path
                self.download(data=skill_zip(extra=(entry, "unsafe")))
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    await loader.async_get_skill("weather")
        self.download()
        self.assertEqual("weather", (await loader.list_skills())[0].name)

    async def test_symlink_duplicate_and_archive_bomb_are_rejected(self):
        loader = self.loader(names=["weather"], version="v1")
        stream = io.BytesIO(skill_zip())
        with zipfile.ZipFile(stream, "a") as archive:
            info = zipfile.ZipInfo("link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../outside")
        self.download(data=stream.getvalue())
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            await loader.async_get_skill("weather")
        self.download(data=skill_zip(extra=("Weather.txt", "duplicate")))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            await loader.async_get_skill("weather")
        self.download()
        with patch("polaris_ai.agentscope.skill._MAX_ARCHIVE_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "limit"):
                await loader.async_get_skill("weather")

    async def test_concurrent_loads_download_once(self):
        self.download()
        loader = self.loader(names=["weather"], version="v1")
        results = await asyncio.gather(loader.list_skills(), loader.list_skills())
        self.assertIs(results[0][0], results[1][0])
        self.assertEqual(1, len(self.engine.skill_calls))

    async def test_async_exit_removes_assets_and_preserves_context(self):
        self.download()
        async with self.loader(names=["weather"], version="v1") as loader:
            directory = Path((await loader.list_skills())[0].dir)
        self.assertFalse(directory.exists())
        self.assertFalse(self.context.is_destroy())
        with self.assertRaises(RuntimeError):
            await loader.list_skills()

    async def test_destroyed_context_rejects_cached_content(self):
        self.download()
        loader = self.loader(names=["weather"], version="v1")
        await loader.list_skills()
        self.context.destroy()
        with self.assertRaises(RuntimeError):
            await loader.list_skills()

    async def test_multiple_skill_roots_and_nested_definitions_are_rejected(self):
        loader = self.loader(names=["weather"], version="v1")
        for extra in (("other/asset.txt", "outside"), ("weather/sub/SKILL.md", "nested")):
            with self.subTest(extra=extra):
                self.download(data=skill_zip("weather/", extra=extra))
                with self.assertRaises(ValueError):
                    await loader.async_get_skill("weather")

    async def test_cancelled_extraction_finishes_before_a_retry_reuses_the_skill(self):
        self.download()
        loader = self.loader(names=["weather"], version="v1")
        entered = Event()
        release = Event()
        materialize = loader._materialize

        def blocked_materialize(*args):
            entered.set()
            release.wait(timeout=5)
            return materialize(*args)

        with patch.object(loader, "_materialize", side_effect=blocked_materialize):
            first = asyncio.create_task(loader.list_skills())
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            first.cancel()
            await asyncio.sleep(0)
            retry = asyncio.create_task(loader.list_skills())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await first
            skills = await retry
        self.assertIs(skills[0], (await loader.list_skills())[0])
        self.assertEqual(1, len(self.engine.skill_calls))

    async def test_close_cancellation_while_waiting_for_load_still_cleans_assets(self):
        self.download()
        loader = self.loader(names=["weather"], version="v1")
        directory = Path((await loader.list_skills())[0].dir)
        await loader._lock.acquire()
        closing = asyncio.create_task(loader.async_close())
        await asyncio.sleep(0)
        closing.cancel()
        await asyncio.sleep(0)
        closing.cancel()
        loader._lock.release()
        with self.assertRaises(asyncio.CancelledError):
            await closing
        self.assertFalse(directory.exists())
        self.assertFalse(self.context.is_destroy())
