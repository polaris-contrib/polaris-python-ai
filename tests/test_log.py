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
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from unittest.mock import patch

import pytest

from polaris_ai.log import (
    LOG_CATEGORIES,
    PolarisAILogOptions,
    configure_ai_logging,
    get_ai_logger,
    use_ai_logger,
)


def test_standard_logger_is_used_without_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("POLARIS_AI_LOG_PATH", str(tmp_path))
    logger = get_ai_logger("base")
    logger.warning("application-managed")
    assert list(tmp_path.iterdir()) == []


def test_managed_logger_writes_every_category_with_client_id(tmp_path):
    manager = configure_ai_logging(
        "client-1",
        PolarisAILogOptions(log_dir=tmp_path, max_age_days=0),
    )
    for category in LOG_CATEGORIES:
        manager.get_logger(category).warning("category=%s", category)
    manager.close()

    for category in LOG_CATEGORIES:
        path = tmp_path / category / f"polaris-ai-{category}-client-1.log"
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        assert "[clientId=client-1]" in content
        assert f"category={category}" in content
        assert (path.parent / f".{path.name}.lock").exists()


def test_default_managed_root_is_polaris_log_ai(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POLARIS_AI_LOG_PATH", raising=False)
    manager = configure_ai_logging(
        "default-root",
        PolarisAILogOptions(max_age_days=0),
    )
    manager.get_logger("base").warning("default-root-record")
    manager.close()

    path = (
        tmp_path / "polaris" / "log" / "ai" / "base"
        / "polaris-ai-base-default-root.log"
    )
    assert path.is_file()


def test_environment_options_and_level_are_applied(monkeypatch, tmp_path):
    monkeypatch.setenv("POLARIS_AI_LOG_PATH", str(tmp_path))
    monkeypatch.setenv("POLARIS_AI_LOG_LEVEL", "error")
    manager = configure_ai_logging("client-env", PolarisAILogOptions(max_age_days=0))
    logger = manager.get_logger("a2a")
    logger.warning("hidden")
    logger.error("visible")
    manager.close()

    content = (
        tmp_path / "a2a" / "polaris-ai-a2a-client-env.log"
    ).read_text(encoding="utf-8")
    assert "hidden" not in content
    assert "visible" in content


def test_explicit_file_path_uses_category_family_without_client_id(tmp_path):
    base = tmp_path / "polaris-ai.log"
    manager = configure_ai_logging(
        "client-1",
        PolarisAILogOptions(file_path=base, max_age_days=0),
    )
    manager.get_logger("base").info("base")
    manager.get_logger("mcp").info("mcp")
    manager.close()

    assert base.is_file()
    assert (tmp_path / "mcp" / "polaris-ai-mcp.log").is_file()
    assert "client-1" not in base.name


def test_active_file_conflict_is_rejected_and_close_releases_path(tmp_path):
    options = PolarisAILogOptions(log_dir=tmp_path, max_age_days=0)
    first = configure_ai_logging("first", options)
    with pytest.raises(Exception, match="log file is already in use|Log file is already in use"):
        configure_ai_logging("first", options)
    first.close()

    replacement = configure_ai_logging("first", options)
    replacement.close()


def test_rotation_creates_numbered_backup(tmp_path):
    manager = configure_ai_logging(
        "rotate",
        PolarisAILogOptions(
            log_dir=tmp_path,
            max_bytes=180,
            backup_count=1,
            max_age_days=0,
        ),
    )
    logger = manager.get_logger("skill")
    logger.info("x" * 300)
    logger.info("y" * 300)
    manager.close()

    path = tmp_path / "skill" / "polaris-ai-skill-rotate.log"
    assert path.is_file()
    assert path.with_name(f"{path.name}.1").is_file()


def test_agentscope_bridge_adds_and_removes_only_owned_handler(tmp_path):
    agentscope_logger = logging.getLogger("as")
    original_handlers = tuple(agentscope_logger.handlers)
    manager = configure_ai_logging(
        "bridge",
        PolarisAILogOptions(
            log_dir=tmp_path,
            capture_agentscope=True,
            max_age_days=0,
        ),
    )
    assert len(agentscope_logger.handlers) == len(original_handlers) + 1
    agentscope_logger.warning("agent-scope-record")
    manager.close()

    assert tuple(agentscope_logger.handlers) == original_handlers
    content = (
        tmp_path / "agentscope" / "polaris-ai-agentscope-bridge.log"
    ).read_text(encoding="utf-8")
    assert "agent-scope-record" in content


def test_agentscope_bridge_is_exclusive_until_close(tmp_path):
    first = configure_ai_logging(
        "first-bridge",
        PolarisAILogOptions(
            log_dir=tmp_path,
            capture_agentscope=True,
            max_age_days=0,
        ),
    )
    with pytest.raises(ValueError, match="already captured"):
        configure_ai_logging(
            "second-bridge",
            PolarisAILogOptions(
                log_dir=tmp_path,
                capture_agentscope=True,
                max_age_days=0,
            ),
        )
    first.close()

    second = configure_ai_logging(
        "second-bridge",
        PolarisAILogOptions(
            log_dir=tmp_path,
            capture_agentscope=True,
            max_age_days=0,
        ),
    )
    second.close()


def test_multiple_managers_use_isolated_client_files(tmp_path):
    first = configure_ai_logging(
        "first",
        PolarisAILogOptions(log_dir=tmp_path, max_age_days=0),
    )
    second = configure_ai_logging(
        "second",
        PolarisAILogOptions(log_dir=tmp_path, max_age_days=0),
    )
    first.get_logger("a2a").warning("first-only")
    second.get_logger("a2a").warning("second-only")
    first.close()
    second.close()

    first_content = (
        tmp_path / "a2a" / "polaris-ai-a2a-first.log"
    ).read_text(encoding="utf-8")
    second_content = (
        tmp_path / "a2a" / "polaris-ai-a2a-second.log"
    ).read_text(encoding="utf-8")
    assert "first-only" in first_content
    assert "second-only" not in first_content
    assert "second-only" in second_content
    assert "first-only" not in second_content


def test_context_var_selects_the_managed_logger(tmp_path):
    manager = configure_ai_logging(
        "bound",
        PolarisAILogOptions(log_dir=tmp_path, max_age_days=0),
    )
    with use_ai_logger(manager):
        get_ai_logger("metrics").warning("bound-record")
    manager.close()

    content = (
        tmp_path / "metrics" / "polaris-ai-metrics-bound.log"
    ).read_text(encoding="utf-8")
    assert "bound-record" in content


def test_close_still_releases_paths_when_retention_close_fails(tmp_path):
    options = PolarisAILogOptions(log_dir=tmp_path, max_age_days=0)
    manager = configure_ai_logging("close-failure", options)
    manager.get_logger("base").warning("before-close")

    def fail():
        raise RuntimeError("retention failed")

    manager._retention.close = fail
    with pytest.raises(RuntimeError, match="retention failed"):
        manager.close()

    replacement = configure_ai_logging("close-failure", options)
    replacement.close()


def test_repeated_warnings_are_throttled_and_report_suppressed_count(tmp_path):
    manager = configure_ai_logging(
        "throttle",
        PolarisAILogOptions(
            log_dir=tmp_path,
            max_age_days=0,
            warning_throttle_seconds=30,
        ),
    )
    logger = manager.get_logger("mcp")
    with patch("polaris_ai.log.time.monotonic", side_effect=[10, 11, 12, 50]):
        logger.warning_throttled(("contract", "search"), "contract unavailable: %s", "timeout")
        logger.warning_throttled(("contract", "search"), "contract unavailable: %s", "timeout")
        logger.warning_throttled(("contract", "search"), "contract unavailable: %s", "timeout")
        logger.warning_throttled(("contract", "search"), "contract unavailable: %s", "timeout")
    manager.close()

    content = (
        tmp_path / "mcp" / "polaris-ai-mcp-throttle.log"
    ).read_text(encoding="utf-8")
    assert content.count("contract unavailable") == 2
    assert "[suppressed 2 similar warnings]" in content
