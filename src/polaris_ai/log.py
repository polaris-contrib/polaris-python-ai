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

"""Optional Polaris-managed logging for AI adapters."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from polaris.api._log_file import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_BYTES,
    ExclusiveRotatingFileHandler,
    LogRetention,
    reserve_log_files,
)

from polaris_ai._async import await_completion

LOG_CATEGORIES = ("base", "agentscope", "skill", "a2a", "mcp", "metrics")
DEFAULT_AI_LOG_DIR = "./polaris/log/ai"
DEFAULT_WARNING_THROTTLE_SECONDS = 30.0

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARN,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
_bound_logger: ContextVar["PolarisAILogger | None"] = ContextVar(
    "polaris_ai_logger", default=None,
)
_agentscope_owner_lock = RLock()
_agentscope_owner: "PolarisAILogger | None" = None
@dataclass(frozen=True)
class PolarisAILogOptions:
    """Code-first options for Polaris AI extension logs.

    Passing options enables Polaris-managed files. ``None`` leaves logging to
    the host application's Python logging configuration.
    """

    level: str | None = None
    file_path: str | Path | None = None
    log_dir: str | Path | None = None
    max_bytes: int = DEFAULT_MAX_BYTES
    backup_count: int = DEFAULT_BACKUP_COUNT
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
    capture_agentscope: bool | None = None
    warning_throttle_seconds: float = DEFAULT_WARNING_THROTTLE_SECONDS


def _boolean(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _validate_category(category: str):
    if category not in LOG_CATEGORIES:
        raise ValueError(f"Unknown AI log category: {category}")


def _resolved_level(options: PolarisAILogOptions) -> tuple[str, int]:
    level = options.level
    if level is None:
        level = os.getenv("POLARIS_AI_LOG_LEVEL", "info")
    if not isinstance(level, str) or level.lower() not in _LEVELS:
        raise ValueError(f"Invalid AI log level: {level!r}")
    level = level.lower()
    return level, _LEVELS[level]


def _resolve_paths(
    options: PolarisAILogOptions,
    client_id: str,
) -> tuple[dict[str, Path], tuple[Path, ...]]:
    file_path = options.file_path
    log_dir = options.log_dir
    if file_path is not None and log_dir is not None:
        raise ValueError("Specify either log_dir or file_path")

    if file_path is None and log_dir is None:
        configured = os.getenv("POLARIS_AI_LOG_PATH")
        if configured:
            candidate = Path(configured).expanduser()
            if (
                candidate.is_dir()
                or not candidate.suffix
                or configured.endswith(("/", "\\"))
            ):
                log_dir = candidate
            else:
                file_path = candidate
        else:
            log_dir = DEFAULT_AI_LOG_DIR

    if log_dir is not None:
        root = Path(log_dir).expanduser().resolve()
        paths = {
            category: (
                root / category / f"polaris-ai-{category}-{client_id}.log"
            ).resolve()
            for category in LOG_CATEGORIES
        }
        families = tuple(
            (root / category / f"polaris-ai-{category}.log").resolve()
            for category in LOG_CATEGORIES
        )
        return paths, families

    base = Path(file_path).expanduser().resolve()
    root = base.parent
    stem = base.stem
    suffix = base.suffix or ".log"
    paths = {
        category: (root / category / f"{stem}-{category}{suffix}").resolve()
        for category in LOG_CATEGORIES
    }
    paths["base"] = base
    return paths, ()


class PolarisAILogger:
    """Own the managed files and handlers for one AI runtime context."""

    def __init__(
        self,
        client_id: str,
        options: PolarisAILogOptions | None = None,
    ):
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("A non-empty client_id is required")
        if options is None:
            options = PolarisAILogOptions()
        if not isinstance(options, PolarisAILogOptions):
            raise TypeError("options must be PolarisAILogOptions")
        self.client_id = client_id
        self.options = options
        self.level, self._level = _resolved_level(options)
        if (
            type(options.max_bytes) is not int
            or options.max_bytes <= 0
            or type(options.backup_count) is not int
            or options.backup_count < 0
            or type(options.max_age_days) is not int
            or options.max_age_days < 0
            or isinstance(options.warning_throttle_seconds, bool)
            or not isinstance(options.warning_throttle_seconds, (int, float))
            or options.warning_throttle_seconds < 0
        ):
            raise ValueError("Invalid AI log rotation options")
        self._paths, self._family_paths = _resolve_paths(options, self.client_id)
        self._loggers: dict[str, logging.Logger] = {}
        self._handlers: dict[str, logging.Handler] = {}
        self._agentscope_handler: logging.Handler | None = None
        self._lock = RLock()
        self._closed = False
        try:
            self._locks = reserve_log_files(self._paths.values())
            self._retention = LogRetention(
                self._locks,
                options.max_age_days,
                options.backup_count,
                self._family_paths,
            )
            capture = (
                options.capture_agentscope
                if options.capture_agentscope is not None
                else _boolean(os.getenv("POLARIS_AI_LOG_CAPTURE_AGENTSCOPE"), False)
            )
            if capture:
                self._attach_agentscope()
            self._retention.start()
        except BaseException:
            self.close()
            raise

    def _create_category(self, category: str):
        path = self._paths[category]
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = ExclusiveRotatingFileHandler(
            path,
            "a",
            self.options.max_bytes,
            self.options.backup_count,
            encoding="utf-8",
            max_age_days=self.options.max_age_days,
        )
        handler.setLevel(self._level)
        handler.setFormatter(logging.Formatter(
            f"[%(asctime)s][%(levelname)s][%(process)d]"
            f"[clientId={self.client_id}][%(name)s]: %(message)s",
        ))
        logger = logging.Logger(
            f"polaris_ai.{self.client_id}.{category}",
            level=self._level,
        )
        logger.addHandler(handler)
        logger.propagate = False
        with self._retention.lock:
            self._retention.add_handler(handler)
        self._handlers[category] = handler
        self._loggers[category] = logger
        return logger

    def _logger_for(self, category):
        _validate_category(category)
        if self._closed:
            raise RuntimeError("PolarisAI logger is closed")
        with self._lock:
            if category not in self._loggers:
                return self._create_category(category)
            return self._loggers[category]

    def _attach_agentscope(self):
        global _agentscope_owner
        with _agentscope_owner_lock:
            if _agentscope_owner is not None and _agentscope_owner is not self:
                raise ValueError("AgentScope logging is already captured by another AI runtime")
            handler = self._create_category("agentscope").handlers[0]
            agentscope_logger = logging.getLogger("as")
            if handler not in agentscope_logger.handlers:
                agentscope_logger.addHandler(handler)
            self._agentscope_handler = handler
            _agentscope_owner = self

    def get_logger(self, category="base"):
        """Return a lazy category logger for this runtime."""
        _validate_category(category)
        return _CategoryLogger(
            self,
            category,
            self.options.warning_throttle_seconds,
        )

    def close(self):
        """Close owned handlers and release every reserved path."""
        global _agentscope_owner
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                with _agentscope_owner_lock:
                    if self._agentscope_handler is not None:
                        logging.getLogger("as").removeHandler(self._agentscope_handler)
                        self._agentscope_handler = None
                    if _agentscope_owner is self:
                        _agentscope_owner = None
            finally:
                try:
                    if hasattr(self, "_retention"):
                        self._retention.close()
                finally:
                    for category, logger in self._loggers.items():
                        handler = self._handlers.get(category)
                        if handler is not None:
                            logger.removeHandler(handler)
                            handler.close()
                    self._handlers.clear()
                    self._loggers.clear()
                    for lock in getattr(self, "_locks", {}).values():
                        lock.close()

    async def async_close(self):
        await await_completion(asyncio.to_thread(self.close))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class _CategoryLogger:
    """Resolve a category logger at emission time without changing std logging."""

    def __init__(
        self,
        manager: PolarisAILogger | None,
        category: str,
        warning_throttle_seconds: float = DEFAULT_WARNING_THROTTLE_SECONDS,
    ):
        _validate_category(category)
        self._manager = manager
        self.category = category
        self._warning_interval = warning_throttle_seconds
        self._warning_lock = RLock()
        self._warning_state: dict[object, tuple[float, int]] = {}

    def _target(self):
        manager = self._manager
        if manager is not None:
            return manager._logger_for(self.category)
        bound = _bound_logger.get()
        if bound is not None:
            return bound._logger_for(self.category)
        return logging.getLogger(f"polaris_ai.{self.category}")

    def debug(self, msg, *args, **kwargs):
        self._target().debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._target().info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._target().warning(msg, *args, **kwargs)

    def warning_throttled(self, key, msg, *args, **kwargs):
        """Emit a warning at most once per interval and report suppressed count."""
        now = time.monotonic()
        with self._warning_lock:
            last, suppressed = self._warning_state.get(key, (0.0, 0))
            if last and now - last < self._warning_interval:
                self._warning_state[key] = (last, suppressed + 1)
                return
            self._warning_state[key] = (now, 0)
        if suppressed:
            msg = f"{msg} [suppressed {suppressed} similar warnings]"
        self._target().warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._target().error(msg, *args, **kwargs)


def get_ai_logger(category="base"):
    """Return a category logger that uses managed AI logging when configured."""
    return _CategoryLogger(None, category)


def configure_ai_logging(
    client_id: str,
    options: PolarisAILogOptions | None = None,
) -> PolarisAILogger:
    """Create an owned AI log manager for a runtime or application."""
    return PolarisAILogger(client_id, options)


@contextmanager
def use_ai_logger(instance: PolarisAILogger | None):
    """Bind a managed logger to the current async task or thread."""
    token = _bound_logger.set(instance)
    try:
        yield
    finally:
        _bound_logger.reset(token)
