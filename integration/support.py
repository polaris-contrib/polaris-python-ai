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

"""Shared state and artifact helpers for integration verification."""

import atexit
import json
import os
import sys
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psutil

DEFAULT_E2E_NAMESPACE = "python-agentscope-e2e"
_tracked = set()


def track_process(directory, entry):
    """Record process identity so cleanup cannot signal a reused PID."""
    directory = Path(directory).resolve()
    if directory in _tracked:
        return
    process = psutil.Process()
    records = directory / ".runtime" / "processes"
    records.mkdir(parents=True, exist_ok=True)
    record = records / f"{process.pid}.json"
    data = {
        "pid": process.pid,
        "created": process.create_time(),
        "command": process.cmdline(),
        "entry": str(Path(entry).resolve()),
    }
    record.write_text(json.dumps(data), encoding="utf-8")
    _tracked.add(directory)
    atexit.register(record.unlink, missing_ok=True)


def e2e_namespace(*, allow_default=False):
    """Return the namespace reserved for real AgentScope example verification."""
    namespace = os.getenv("POLARIS_E2E_NAMESPACE", DEFAULT_E2E_NAMESPACE).strip()
    namespace = namespace or DEFAULT_E2E_NAMESPACE
    if namespace == "default" and not allow_default:
        raise ValueError("POLARIS_E2E_NAMESPACE must name an isolated E2E namespace")
    return namespace


def new_run_directory(directory, action):
    """Give concurrent and repeated runs separate, inspectable output directories."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(directory) / ".logs" / f"{action}-{stamp}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True)
    return path


def record_external_process(directory, process, entry):
    """Record a child process so cleanup can verify identity before signaling it."""
    directory = Path(directory).resolve()
    records = directory / ".runtime" / "processes"
    records.mkdir(parents=True, exist_ok=True)
    record = records / f"{process.pid}.json"
    data = {
        "pid": process.pid,
        "created": process.create_time(),
        "command": process.cmdline(),
        "entry": str(Path(entry).resolve()),
    }
    record.write_text(json.dumps(data), encoding="utf-8")
    return record


class _Tee:
    def __init__(self, stream, logfile):
        self.stream, self.logfile = stream, logfile

    def write(self, value):
        self.logfile.write(value)
        self.logfile.flush()
        return self.stream.write(value)

    def flush(self):
        self.logfile.flush()
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


@contextmanager
def verification_directory(entry):
    """Retain console output, SDK logs and caches after either success or failure."""
    directory = Path(entry).resolve().parent
    configured = os.getenv("POLARIS_DEMO_RUN_DIR")
    run = Path(configured) if configured else new_run_directory(directory, "verify")
    work = run / "work"
    work.mkdir(parents=True, exist_ok=True)
    previous = {
        name: os.environ.get(name) for name in ("POLARIS_DEMO_RUN_DIR", "POLARIS_DEMO_DIRECTORY")
    }
    os.environ["POLARIS_DEMO_RUN_DIR"] = str(run)
    os.environ.setdefault("POLARIS_DEMO_DIRECTORY", str(directory))
    track_process(os.environ["POLARIS_DEMO_DIRECTORY"], entry)
    output, errors = sys.stdout, sys.stderr
    try:
        with (run / "verification.log").open("a", encoding="utf-8") as logfile:
            sys.stdout, sys.stderr = _Tee(output, logfile), _Tee(errors, logfile)
            try:
                yield work
            except BaseException:
                traceback.print_exc(file=logfile)
                raise
            finally:
                sys.stdout, sys.stderr = output, errors
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        print(f"Logs: {run / 'polaris' / 'log'}", file=sys.stderr)
        print(f"AI logs: {run / 'polaris' / 'log' / 'ai'}", file=sys.stderr)
        print(f"Backups: {run / 'polaris' / 'backup'}", file=sys.stderr)
