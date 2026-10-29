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

"""Execute the snapshot workflow's version scripts without publishing packages."""

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/python-snapshot.yaml"
TESTING_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/testing.yml"


def workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _load_testing_workflow():
    return yaml.load(TESTING_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _project_text(version: str) -> str:
    return f'[project]\nname = "polaris-python-ai"\nversion = "{version}"\n'


def run_version_step(tmp_path, configured, job, step_id, run_number="42", module_version=None):
    init = tmp_path / "src/polaris_ai/__init__.py"
    init.parent.mkdir(parents=True, exist_ok=True)
    module_version = configured if module_version is None else module_version
    original_init = f'"""Preserve the module docstring."""\n\n__version__ = "{module_version}"\n'
    init.write_text(original_init, encoding="utf-8")
    pyproject = tmp_path / "pyproject.toml"
    original_project = _project_text(configured)
    pyproject.write_text(original_project, encoding="utf-8")
    output = tmp_path / "github-output"
    step = next(step for step in workflow()["jobs"][job]["steps"] if step.get("id") == step_id)
    lines = step["run"].splitlines()
    assert lines[0].endswith("<<'PY'") and lines[-1] == "PY"
    completed = subprocess.run(
        [sys.executable, "-c", "\n".join(lines[1:-1])],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(output), "GITHUB_RUN_NUMBER": run_number},
        capture_output=True,
        text=True,
        timeout=10,
    )
    emitted = output.read_text(encoding="utf-8") if output.exists() else ""
    return completed, pyproject, init, original_project, original_init, emitted


def test_snapshot_publish_only_uses_verified_artifacts():
    config = workflow()
    assert config["on"]["push"]["branches"] == ["main", "release/*", "develop"]
    assert "workflow_dispatch" in config["on"]
    assert "pull_request" not in config["on"]
    jobs = config["jobs"]
    assert "refs/heads/develop" in jobs["check-snapshot"]["if"]
    assert "refs/heads/main" in jobs["check-snapshot"]["if"]
    assert "refs/heads/release/" in jobs["check-snapshot"]["if"]
    assert jobs["build"]["needs"] == "check-snapshot"
    assert jobs["build"]["if"] == "${{ needs.check-snapshot.outputs.IS_SNAPSHOT == 'true' }}"
    assert jobs["publish"]["needs"] == "build"
    assert jobs["publish"]["environment"] == "Release"
    upload = jobs["build"]["steps"][-1]
    download, publish = jobs["publish"]["steps"]
    assert upload["with"]["name"] == download["with"]["name"]
    assert upload["with"]["name"] == "polaris-python-ai-snapshot-dist"
    assert upload["with"]["path"] == "polaris-python-ai/dist/"
    assert publish["with"]["password"] == "${{ secrets.PYPI_API_TOKEN }}"
    assert publish["with"]["skip-existing"] == "true"


def test_snapshot_build_checks_publishable_metadata_and_core_checkout():
    steps = workflow()["jobs"]["build"]["steps"]
    core_checkout = next(
        step for step in steps
        if step.get("with", {}).get("repository") == "polaris-contrib/polaris-python"
    )
    assert core_checkout["with"]["ref"] == "${{ github.head_ref || github.ref_name }}"
    assert any("polaris-python/dist/*.whl" in step.get("run", "") for step in steps)
    assert any("${wheel}[agentscope,a2a,mcp]" in step.get("run", "") for step in steps)
    assert any("../polaris-python" in step.get("run", "") for step in steps)


@pytest.mark.parametrize("job", ["test", "package"])
def test_testing_checks_out_matching_core_ref(job):
    steps = _load_testing_workflow()["jobs"][job]["steps"]
    core_checkout = next(
        step for step in steps
        if step.get("with", {}).get("repository") == "polaris-contrib/polaris-python"
    )
    assert core_checkout["with"]["ref"] == "${{ github.head_ref || github.ref_name }}"


@pytest.mark.parametrize("configured, expected", [
    ("0.1.0", False),
    ("0.1.1a1", False),
    ("0.1.1rc1", False),
    ("0.1.0.post1", False),
    ("0.1.1.dev0", True),
    ("0.1.1a2.dev7", True),
])
def test_snapshot_gate(tmp_path, configured, expected):
    completed, pyproject, init, original_project, original_init, emitted = run_version_step(
        tmp_path, configured, "check-snapshot", "check_version"
    )
    assert completed.returncode == 0, completed.stderr
    assert emitted == f"IS_SNAPSHOT={str(expected).lower()}\n"
    assert pyproject.read_text(encoding="utf-8") == original_project
    assert init.read_text(encoding="utf-8") == original_init


@pytest.mark.parametrize("configured, expected", [
    ("0.1.1.dev0", "0.1.1.dev42"),
    ("0.1.1.dev999", "0.1.1.dev42"),
    ("0.1.1a2.dev7", "0.1.1a2.dev42"),
    ("1!0.1.1.dev0", "1!0.1.1.dev42"),
])
def test_snapshot_version_preserves_target_and_header(tmp_path, configured, expected):
    completed, pyproject, init, original_project, original_init, emitted = run_version_step(
        tmp_path, configured, "build", "version"
    )
    assert completed.returncode == 0, completed.stderr
    assert emitted == f"VERSION={expected}\n"
    assert runpy.run_path(str(init))["__version__"] == expected
    assert pyproject.read_text(encoding="utf-8") == original_project.replace(configured, expected)
    assert init.read_text(encoding="utf-8") == original_init.replace(configured, expected)


@pytest.mark.parametrize("configured", ["0.1.0", "0.1.1a1", "0.1.1.dev0+local", "invalid"])
def test_snapshot_set_version_rejects_nonpublic_development_version(tmp_path, configured):
    completed, pyproject, init, original_project, original_init, emitted = run_version_step(
        tmp_path, configured, "build", "version"
    )
    assert completed.returncode != 0
    assert emitted == ""
    assert pyproject.read_text(encoding="utf-8") == original_project
    assert init.read_text(encoding="utf-8") == original_init


@pytest.mark.parametrize("job, step_id", [("check-snapshot", "check_version"), ("build", "version")])
def test_snapshot_scripts_reject_version_mismatch(tmp_path, job, step_id):
    completed, pyproject, init, original_project, original_init, emitted = run_version_step(
        tmp_path, "0.1.1.dev0", job, step_id, module_version="0.1.2.dev0"
    )
    assert completed.returncode != 0
    assert emitted == ""
    assert pyproject.read_text(encoding="utf-8") == original_project
    assert init.read_text(encoding="utf-8") == original_init


@pytest.mark.parametrize("run_number", ["0", "-1", "invalid"])
def test_snapshot_set_version_rejects_invalid_run_number(tmp_path, run_number):
    completed, pyproject, init, original_project, original_init, emitted = run_version_step(
        tmp_path, "0.1.1.dev0", "build", "version", run_number
    )
    assert completed.returncode != 0
    assert emitted == ""
    assert pyproject.read_text(encoding="utf-8") == original_project
    assert init.read_text(encoding="utf-8") == original_init


def test_snapshot_gate_rejects_local_version(tmp_path):
    completed, pyproject, init, original_project, original_init, emitted = run_version_step(
        tmp_path, "0.1.1.dev0+local", "check-snapshot", "check_version"
    )
    assert completed.returncode != 0
    assert emitted == ""
    assert pyproject.read_text(encoding="utf-8") == original_project
    assert init.read_text(encoding="utf-8") == original_init


def test_snapshot_rerun_keeps_version(tmp_path):
    first = run_version_step(tmp_path / "first", "0.1.1.dev0", "build", "version")
    rerun = run_version_step(tmp_path / "rerun", "0.1.1.dev0", "build", "version")
    next_run = run_version_step(tmp_path / "next", "0.1.1.dev0", "build", "version", "43")
    assert first[0].returncode == rerun[0].returncode == next_run[0].returncode == 0
    assert first[5] == rerun[5] == "VERSION=0.1.1.dev42\n"
    assert next_run[5] == "VERSION=0.1.1.dev43\n"
