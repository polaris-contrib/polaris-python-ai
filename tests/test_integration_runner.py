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

"""Regression checks for integration runners, example entry points and cleanup scope."""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psutil
import pytest

from integration import runner as manager
from integration import support

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def example_tree(tmp_path, monkeypatch):
    root = tmp_path / "integration" / "cases"
    examples = tmp_path / "examples"
    for name in (
        "agentscope/skill/published",
        "agentscope/skill/mounted",
        "agentscope/a2a",
        "agentscope/a2a/skill",
        "agentscope/mcp",
        "agentscope/runtime",
    ):
        (root / name).mkdir(parents=True)
        (examples / name).mkdir(parents=True)
    monkeypatch.setattr(manager, "EXAMPLES", examples)
    monkeypatch.setattr(manager, "CASES_ROOT", root)
    monkeypatch.setattr(manager, "INTEGRATION", tmp_path / "integration")
    monkeypatch.setattr(manager, "REPO", tmp_path)
    return root


@pytest.mark.parametrize(
    "script",
    [
        "integration/verify.sh",
        "integration/verify_e2e.sh",
        "integration/logs.sh",
        "integration/cleanup.sh",
    ],
)
def test_entry_points_work_outside_project(script, tmp_path):
    path = REPO / script
    if os.name != "nt":
        assert os.access(path, os.X_OK)
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is unavailable")
    env = dict(os.environ, POLARIS_PYTHON=sys.executable)
    result = subprocess.run(
        [bash, path.as_posix(), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_group_selection_accepts_nested_names_and_rejects_unknown():
    assert manager.verification_targets("", "agentscope/skill") == [
        "agentscope/skill/published",
        "agentscope/skill/mounted",
        "agentscope/skill/console_agent",
    ]
    assert manager.verification_targets("agentscope", "a2a") == [
        "agentscope/a2a",
        "agentscope/a2a/streaming_provider",
        "agentscope/a2a/console_consumer",
        "agentscope/a2a/state_resume",
        "agentscope/a2a/skill",
    ]
    assert manager.verification_targets("agentscope", "mcp") == [
        "agentscope/mcp",
        "agentscope/mcp/agent",
    ]
    assert manager.verification_targets("agentscope", "runtime") == [
        "agentscope/runtime",
        "agentscope/runtime/multi_agent",
    ]
    assert manager.verification_targets("agentscope/a2a", "skill") == ["agentscope/a2a/skill"]
    assert manager.verification_targets("", "agentscope/a2a/provider") == [
        "agentscope/a2a/provider"
    ]
    with pytest.raises(ValueError, match="Unknown demo"):
        manager.verification_targets("", "unknown")


@pytest.mark.parametrize("exit_code", [0, 7])
def test_runner_retains_exit_code_and_output(example_tree, exit_code):
    directory = example_tree / "agentscope/skill/published"
    entry = directory / "verify.py"
    entry.write_text(f"print('verified', flush=True)\nraise SystemExit({exit_code})\n")
    assert manager.run_process(directory, entry, [], "verify", 3) == exit_code
    (run,) = (directory / ".logs").iterdir()
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    assert result["exit_code"] == exit_code
    assert not result["timed_out"] and result["interrupted"] is None
    assert (run / "console.log").read_text(encoding="utf-8") == "verified\n"


def test_e2e_namespace_defaults_to_dedicated_namespace(monkeypatch):
    monkeypatch.delenv("POLARIS_E2E_NAMESPACE", raising=False)
    assert support.e2e_namespace() == "python-agentscope-e2e"
    assert manager.e2e_namespace() == "python-agentscope-e2e"

    monkeypatch.setenv("POLARIS_E2E_NAMESPACE", "custom-e2e")
    assert support.e2e_namespace() == "custom-e2e"
    monkeypatch.setenv("POLARIS_E2E_NAMESPACE", " ")
    assert support.e2e_namespace() == "python-agentscope-e2e"
    monkeypatch.setenv("POLARIS_E2E_NAMESPACE", "default")
    with pytest.raises(ValueError, match="isolated E2E namespace"):
        support.e2e_namespace()
    assert support.e2e_namespace(allow_default=True) == "default"


def test_quiet_child_timeout_records_failure_and_stops_process(example_tree):
    directory = example_tree / "agentscope/skill/published"
    entry = directory / "verify.py"
    entry.write_text("import os, time\nprint(os.getpid(), flush=True)\ntime.sleep(30)\n")
    assert manager.run_process(directory, entry, [], "verify", 0.2) == 124
    (run,) = (directory / ".logs").iterdir()
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    assert result["timed_out"] and result["exit_code"] != 0
    assert not psutil.pid_exists(int((run / "console.log").read_text(encoding="utf-8")))


def test_failure_does_not_prevent_remaining_scenarios(example_tree, monkeypatch):
    called = []

    def run(directory, *args):
        called.append(directory.relative_to(example_tree).as_posix())
        return 7 if len(called) == 1 else 0

    monkeypatch.setattr(manager, "run_process", run)
    monkeypatch.setattr(manager, "track_process", lambda *args: None)
    monkeypatch.setattr(sys, "argv", ["manage", "--directory", str(example_tree), "verify"])
    assert manager.main() == 1
    assert called == manager.GROUPS[""]


def test_cleanup_preview_and_removal_preserve_source_and_other_scenario(example_tree):
    selected = example_tree / "agentscope/skill/published"
    other = example_tree / "agentscope/skill/mounted"
    for directory in (selected, other):
        (directory / ".logs").mkdir()
        (directory / ".logs/console.log").write_text("retained", encoding="utf-8")
        (directory / "polaris.yaml").write_text("keep YAML", encoding="utf-8")
    manager.cleanup(selected, SimpleNamespace(force=True, dry_run=True))
    assert (selected / ".logs/console.log").exists()
    manager.cleanup(selected, SimpleNamespace(force=True, dry_run=False))
    assert not (selected / ".logs").exists()
    assert (selected / "polaris.yaml").read_text(encoding="utf-8") == "keep YAML"
    assert (other / ".logs/console.log").read_text(encoding="utf-8") == "retained"


def test_legacy_cleanup_stays_within_selected_scope(example_tree, monkeypatch):
    monkeypatch.setenv(manager.LEGACY_EXAMPLES_ENV, "1")
    selected = example_tree / "agentscope/skill/published"
    other = example_tree / "agentscope/mcp"
    for directory in (
        selected,
        manager.EXAMPLES / "agentscope/skill/published",
        other,
        manager.EXAMPLES / "agentscope/mcp",
    ):
        (directory / ".logs").mkdir(parents=True)
        (directory / ".logs/console.log").write_text("retained", encoding="utf-8")

    assert manager.legacy_example_directories(selected) == [
        manager.EXAMPLES / "agentscope/skill/published"
    ]
    manager.cleanup(selected, SimpleNamespace(force=True, dry_run=False))
    assert not (selected / ".logs").exists()
    assert not (manager.EXAMPLES / "agentscope/skill/published/.logs").exists()
    assert (other / ".logs/console.log").exists()
    assert (manager.EXAMPLES / "agentscope/mcp/.logs/console.log").exists()


def test_cleanup_cannot_signal_reused_pid(example_tree):
    directory = example_tree / "agentscope/skill/published"
    records = directory / ".runtime/processes"
    records.mkdir(parents=True)
    process = psutil.Process()
    (records / "reused.json").write_text(
        json.dumps(
            {
                "pid": process.pid,
                "created": process.create_time() - 100,
                "command": process.cmdline(),
                "entry": str(directory / "main.py"),
            }
        )
    )
    found, stale = manager.owned_processes(example_tree)
    assert not found and len(stale) == 1


def test_verification_tee_preserves_standard_stream_methods():
    output, log = io.StringIO(), io.StringIO()
    tee = support._Tee(output, log)
    assert tee.isatty() == output.isatty()
    tee.write("uvicorn ready")
    tee.flush()
    assert output.getvalue() == log.getvalue() == "uvicorn ready"


@pytest.mark.skipif(os.name == "nt", reason="the runnable example launcher is Bash-only")
def test_example_launcher_preserves_interpreter_paths_with_spaces(tmp_path):
    make = shutil.which("make")
    if make is None or shutil.which("bash") is None:
        pytest.skip("make or bash is unavailable")

    root = tmp_path / "project"
    case = root / "examples" / "demo"
    case.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (root / "examples" / "demo.mk").write_text(
        (REPO / "examples" / "demo.mk").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (case / "Makefile").write_text("include ../demo.mk\n", encoding="utf-8")
    (case / "main.py").write_text("import sys\nprint(sys.argv[1:])\n", encoding="utf-8")
    python = tmp_path / "Python Env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)

    env = dict(os.environ, POLARIS_PYTHON=str(python))
    built = subprocess.run(
        [make, "-C", str(case), "build"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert built.returncode == 0, built.stderr
    executed = subprocess.run(
        [str(case / "bin"), "value with spaces", "plain"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert executed.returncode == 0, executed.stderr
    assert executed.stdout == "['value with spaces', 'plain']\n"


@pytest.mark.parametrize(
    "demo,variable",
    [
        ("mounted", "POLARIS_AGENT_SERVICE"),
        ("mcp", "POLARIS_MCP_SERVICE"),
    ],
)
def test_real_checks_require_scenario_fixtures(demo, variable):
    pytest.importorskip("agentscope.tool")
    pytest.importorskip("a2a.server.routes")
    from integration.scenarios import required_environment

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="POLARIS_SERVER_ADDRESS"):
            required_environment(demo)
        os.environ["POLARIS_SERVER_ADDRESS"] = "registry:8091"
        with pytest.raises(ValueError, match=variable):
            required_environment(demo)
        os.environ[variable] = "fixture"
        assert required_environment(demo)[0] == "registry:8091"


def test_real_checks_accept_registry_without_service_token():
    pytest.importorskip("agentscope.tool")
    pytest.importorskip("a2a.server.routes")
    from integration.scenarios import required_environment

    with patch.dict(
        os.environ,
        {"POLARIS_SERVER_ADDRESS": "registry:8091"},
        clear=True,
    ):
        assert required_environment("a2a") == ("registry:8091", "")
        assert required_environment("skill-console") == ("registry:8091", "")


def test_real_event_endpoint_handles_ipv6_and_sdk_service_token_priority():
    pytest.importorskip("agentscope.tool")
    pytest.importorskip("a2a.server.routes")
    from integration.scenarios import required_environment, scenario_environment

    assert scenario_environment("[::1]:8091")["POLARIS_EVENT_REPORTER_ADDRESS"] == "[::1]:9091"
    with patch.dict(
        os.environ,
        {
            "POLARIS_SERVER_ADDRESS": "registry:8091",
            "POLARIS_SERVICE_TOKEN": "ordinary",
            "POLARIS_E2E_SERVICE_TOKEN": "e2e",
        },
        clear=True,
    ):
        assert required_environment("a2a") == ("registry:8091", "e2e")


def test_remote_cleanup_filters_ai_prefix_and_namespace(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(
                {
                    "code": 200000,
                    "services": [
                        {
                            "namespace": "python-agentscope-e2e",
                            "name": "polaris-python-ai-e2e-agent",
                        },
                        {"namespace": "python-agentscope-e2e", "name": "polaris-python-e2e-agent"},
                        {"namespace": "python-agentscope-e2e", "name": "mounted-agent"},
                        {"namespace": "other", "name": "polaris-python-ai-e2e-agent"},
                    ],
                }
            ).encode()

    monkeypatch.setenv("POLARIS_SERVER_ADDRESS", "registry:8091")
    monkeypatch.setenv("POLARIS_E2E_NAMESPACE", "python-agentscope-e2e")
    monkeypatch.setattr(manager.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    assert manager.test_services()[2] == ["polaris-python-ai-e2e-agent"]


def test_remote_service_deletion_deregisters_stale_instances_first(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({"code": 200000, "responses": []}).encode()

    def deregister(address, namespace, names, token):
        calls.append((address, namespace, tuple(names), token))
        return 2

    monkeypatch.setenv("POLARIS_E2E_SERVICE_TOKEN", "service-token")
    monkeypatch.setattr(manager, "deregister_test_instances", deregister)
    monkeypatch.setattr(manager.urllib.request, "urlopen", lambda *args, **kwargs: Response())

    assert manager.delete_test_services(
        "http://registry:8090",
        "python-agentscope-e2e",
        ["polaris-python-ai-e2e-service"],
    ) == ["polaris-python-ai-e2e-service"]
    assert calls == [
        (
            "http://registry:8090",
            "python-agentscope-e2e",
            ("polaris-python-ai-e2e-service",),
            "service-token",
        )
    ]


@pytest.mark.parametrize("name", sorted(set(manager.VERIFIERS) | set(manager.GROUPS)))
def test_every_scenario_has_run_and_verification_documentation(name):
    example_dir = REPO / "examples" / name
    integration_dir = REPO / "integration" / "cases" / name
    assert (example_dir / "README.md").is_file()
    assert (example_dir / "README-zh.md").is_file()
    test_doc = REPO / "integration" / "test.md" if not name else integration_dir / "test.md"
    text = test_doc.read_text(encoding="utf-8")
    for expected in ("verify_e2e.sh", "console.log", "result.json", "verification.log"):
        assert expected in text
    assert (example_dir / "Makefile").is_file()
    assert not (example_dir / "test.md").exists()


def test_examples_do_not_own_integration_harness():
    assert not (REPO / "examples" / "_internal" / "_manage.py").exists()
    assert not (REPO / "examples" / "_internal" / "_verify.py").exists()
    assert not (REPO / "examples" / "_internal" / "_stub.py").exists()
    for script in ("verify.sh", "verify_e2e.sh", "logs.sh", "cleanup.sh"):
        assert not (REPO / "examples" / script).exists()
    assert (REPO / "integration" / "runner.py").is_file()
    assert (REPO / "integration" / "scenarios.py").is_file()
    assert (REPO / "integration" / "stub.py").is_file()
