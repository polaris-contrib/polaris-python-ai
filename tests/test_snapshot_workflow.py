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

"""Check the single-package version source and release workflows."""

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from polaris_ai import __version__ as runtime_version


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_WORKFLOW = ROOT / ".github/workflows/python-snapshot.yaml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"
TESTING_WORKFLOW = ROOT / ".github/workflows/testing.yml"
PYPROJECT = ROOT / "pyproject.toml"
VERSION_FILE = ROOT / "src/polaris_ai/_version.py"
PACKAGE_INIT = ROOT / "src/polaris_ai/__init__.py"


def load_workflow(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def read_version(path):
    assignments = [
        node
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    return ast.literal_eval(assignments[0].value)


def run_step_script(step, cwd, **extra_env):
    lines = step["run"].splitlines()
    assert lines[0].endswith("<<'PY'") and lines[-1] == "PY"
    return subprocess.run(
        [sys.executable, "-c", "\n".join(lines[1:-1])],
        cwd=cwd,
        env={**os.environ, **extra_env},
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_project_uses_one_distribution_and_one_version_source():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert project["project"]["name"] == "polaris-python-ai"
    assert project["project"]["dependencies"] == ["polaris-python>=0.0.1.dev0,<0.1"]
    assert project["project"]["dynamic"] == ["version"]
    assert "version" not in project["project"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "polaris_ai._version.__version__"
    }
    assert read_version(VERSION_FILE) == runtime_version
    assert "__version__ =" not in PACKAGE_INIT.read_text(encoding="utf-8")
    assert not (ROOT / "libs").exists()
    assert not (ROOT / "src/polaris_ai/a2a/_version.py").exists()
    assert not (ROOT / "src/polaris_ai/agentscope/_version.py").exists()
    assert not (ROOT / "src/polaris_ai/langgraph/_version.py").exists()


def test_optional_frameworks_are_installed_through_extras():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]
    assert extras == {
        "a2a": ["a2a-sdk>=1.2.3,<2"],
        "agentscope": [
            "a2a-sdk>=1.2.3,<2",
            "agentscope>=2.0.10,<3",
        ],
        "langgraph": ["langgraph>=1.0,<2"],
        "mcp": [
            "a2a-sdk>=1.2.3,<2",
            "agentscope>=2.0.10,<3",
            "mcp>=2,<3",
        ],
        "all": [
            "a2a-sdk>=1.2.3,<2",
            "agentscope>=2.0.10,<3",
            "langgraph>=1.0,<2",
            "mcp>=2,<3",
        ],
    }


def test_snapshot_triggers_on_main_relevant_changes_and_checks_dev_version():
    config = load_workflow(SNAPSHOT_WORKFLOW)
    assert config["on"]["push"]["branches"] == ["main", "release/*", "develop"]
    assert config["on"]["push"]["paths"] == [
        "src/**",
        "tests/**",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/python-snapshot.yaml",
        "!src/**.md",
        "!tests/**.md",
    ]
    assert "workflow_dispatch" in config["on"]
    jobs = config["jobs"]
    assert "refs/heads/main" in jobs["check-snapshot"]["if"]
    assert "refs/heads/develop" in jobs["check-snapshot"]["if"]
    assert "refs/heads/release/" in jobs["check-snapshot"]["if"]
    assert jobs["build"]["needs"] == "check-snapshot"
    assert jobs["build"]["if"] == "${{ needs.check-snapshot.outputs.IS_SNAPSHOT == 'true' }}"
    assert jobs["publish"]["needs"] == "build"
    assert jobs["publish"]["environment"] == "Release"
    assert jobs["publish"]["permissions"] == {"contents": "read", "id-token": "write"}


def test_snapshot_upload_and_publish_use_the_same_verified_artifact():
    config = load_workflow(SNAPSHOT_WORKFLOW)
    upload = config["jobs"]["build"]["steps"][-1]
    download, publish = config["jobs"]["publish"]["steps"]
    assert upload["with"]["name"] == download["with"]["name"]
    assert upload["with"]["path"] == "polaris-python-ai/dist/"
    assert "user" not in publish["with"]
    assert "password" not in publish["with"]
    assert publish["with"]["attestations"] == "true"
    assert publish["with"]["skip-existing"] == "true"


def test_release_requires_the_canonical_single_package_tag():
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "polaris-python-ai==" in text
    assert 'RELEASE_TAG"] != expected' in text
    config = load_workflow(RELEASE_WORKFLOW)
    assert "working-directory" not in config["on"]["workflow_dispatch"]["inputs"]
    publish = config["jobs"]["publish"]
    assert publish["environment"] == "Release"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    step = next(step for step in publish["steps"]
                if step.get("uses") == "pypa/gh-action-pypi-publish@release/v1")
    assert "user" not in step["with"]
    assert "password" not in step["with"]
    assert step["with"]["attestations"] == "true"


def test_testing_checks_one_lockfile_and_one_wheel():
    config = load_workflow(TESTING_WORKFLOW)
    install = next(
        step
        for step in config["jobs"]["test"]["steps"]
        if step["name"] == "Install dependencies"
    )
    assert install["run"] == "uv sync --all-extras --group dev --locked"
    package_steps = config["jobs"]["package"]["steps"]
    build = next(step for step in package_steps if step["name"] == "Build AI distributions")
    assert build["run"] == "uv build"
    install_wheel = next(
        step for step in package_steps if step["name"] == "Install verified wheel"
    )
    assert "${wheel}[all]" in install_wheel["run"]


def test_snapshot_version_step_changes_only_the_single_version_file(tmp_path):
    workflow = load_workflow(SNAPSHOT_WORKFLOW)
    step = next(
        item
        for item in workflow["jobs"]["build"]["steps"]
        if item.get("id") == "version"
    )
    about = tmp_path / "src/polaris_ai/_version.py"
    about.parent.mkdir(parents=True)
    about.write_text(
        '"""header"""\n\n__version__ = "0.2.0.dev0"\n',
        encoding="utf-8",
    )
    output = tmp_path / "github-output"
    completed = run_step_script(
        step,
        tmp_path,
        GITHUB_OUTPUT=str(output),
        GITHUB_RUN_NUMBER="42",
    )
    assert completed.returncode == 0, completed.stderr
    assert read_version(about) == "0.2.0.dev42"
    assert output.read_text(encoding="utf-8") == "VERSION=0.2.0.dev42\n"


@pytest.mark.parametrize("configured", ["0.2.0", "0.2.0.dev0+local", "invalid"])
def test_snapshot_version_step_rejects_nonpublic_development_version(tmp_path, configured):
    workflow = load_workflow(SNAPSHOT_WORKFLOW)
    step = next(
        item
        for item in workflow["jobs"]["build"]["steps"]
        if item.get("id") == "version"
    )
    about = tmp_path / "src/polaris_ai/_version.py"
    about.parent.mkdir(parents=True)
    original = f'__version__ = "{configured}"\n'
    about.write_text(original, encoding="utf-8")
    completed = run_step_script(
        step,
        tmp_path,
        GITHUB_OUTPUT=str(tmp_path / "output"),
        GITHUB_RUN_NUMBER="42",
    )
    assert completed.returncode != 0
    assert about.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("run_number", ["0", "-1", "invalid"])
def test_snapshot_version_step_rejects_invalid_run_number(tmp_path, run_number):
    workflow = load_workflow(SNAPSHOT_WORKFLOW)
    step = next(
        item
        for item in workflow["jobs"]["build"]["steps"]
        if item.get("id") == "version"
    )
    about = tmp_path / "src/polaris_ai/_version.py"
    about.parent.mkdir(parents=True)
    original = '__version__ = "0.2.0.dev0"\n'
    about.write_text(original, encoding="utf-8")
    completed = run_step_script(
        step,
        tmp_path,
        GITHUB_OUTPUT=str(tmp_path / "output"),
        GITHUB_RUN_NUMBER=run_number,
    )
    assert completed.returncode != 0
    assert about.read_text(encoding="utf-8") == original


def test_release_version_step_accepts_only_matching_tag(tmp_path):
    workflow = load_workflow(RELEASE_WORKFLOW)
    step = next(
        item
        for item in workflow["jobs"]["build"]["steps"]
        if item["name"] == "Verify release version"
    )
    about = tmp_path / "src/polaris_ai/_version.py"
    about.parent.mkdir(parents=True)
    about.write_text('__version__ = "0.2.0"\n', encoding="utf-8")
    completed = run_step_script(
        step,
        tmp_path,
        RELEASE_TAG="polaris-python-ai==0.2.0",
    )
    assert completed.returncode == 0, completed.stderr
    completed = run_step_script(
        step,
        tmp_path,
        RELEASE_TAG="polaris-python-ai==0.2.1",
    )
    assert completed.returncode != 0
