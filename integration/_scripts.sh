#!/usr/bin/env bash
# Shared integration entry point; paths never depend on the caller's current directory.
set -euo pipefail

integration_scripts_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
integration_repo_dir="$(cd -- "${integration_scripts_dir}/.." && pwd)"

integration_manage() {
    if [[ -n "${POLARIS_PYTHON:-}" ]]; then
        exec "$POLARIS_PYTHON" "${integration_scripts_dir}/runner.py" --directory "$@"
    elif [[ -x "${integration_repo_dir}/.venv/bin/python" ]]; then
        exec "${integration_repo_dir}/.venv/bin/python" "${integration_scripts_dir}/runner.py" --directory "$@"
    elif command -v uv >/dev/null 2>&1; then
        exec uv run --project "$integration_repo_dir" --all-extras python "${integration_scripts_dir}/runner.py" --directory "$@"
    else
        exec python3 "${integration_scripts_dir}/runner.py" --directory "$@"
    fi
}
