# Keep runnable examples self-contained.
ARGS ?=
DEMO_NAME ?= $(notdir $(CURDIR))
REPO_ROOT := $(shell dir="$(CURDIR)"; while [ "$$dir" != "/" ] && [ ! -f "$$dir/pyproject.toml" ]; do dir=$$(dirname "$$dir"); done; printf '%s\n' "$$dir")

.PHONY: build build-x86 package run clean

build:
	@printf '%s\n' \
		'#!/usr/bin/env bash' \
		'set -euo pipefail' \
		'HERE=$$(CDPATH= cd -- "$$(dirname -- "$$0")" && pwd)' \
		'ROOT=$$HERE' \
		'while [ "$$ROOT" != "/" ] && [ ! -f "$$ROOT/pyproject.toml" ]; do' \
		'  ROOT=$$(dirname "$$ROOT")' \
		'done' \
		'if [ ! -f "$$ROOT/pyproject.toml" ]; then' \
		'  echo "place this demo inside a polaris-python-ai checkout" >&2' \
		'  exit 1' \
		'fi' \
		'if [ -n "$${POLARIS_PYTHON:-}" ]; then' \
		'  PYTHON=("$$POLARIS_PYTHON")' \
		'elif [ -x "$$ROOT/.venv/bin/python" ]; then' \
		'  PYTHON=("$$ROOT/.venv/bin/python")' \
		'elif command -v uv >/dev/null 2>&1; then' \
		'  PYTHON=(uv run --project "$$ROOT" --all-extras python)' \
		'else' \
		'  PYTHON=(python3)' \
		'fi' \
		'export PYTHONPATH="$$ROOT/src:$$ROOT$${PYTHONPATH:+:$$PYTHONPATH}"' \
		'exec "$${PYTHON[@]}" "$$HERE/main.py" "$$@"' \
		> "$(CURDIR)/bin"
	@chmod +x "$(CURDIR)/bin"
	@echo "built $(CURDIR)/bin"

build-x86:
	@os=$$(uname -s); arch=$$(uname -m); \
	if [ "$$os" = "Linux" ] && [ "$$arch" = "x86_64" ]; then \
		$(MAKE) build; cp "$(CURDIR)/bin" "$(CURDIR)/x86-bin"; \
	else \
		echo "build-x86 requires linux/amd64; current platform is $$os/$$arch." >&2; exit 1; \
	fi

package: build
	@mkdir -p "$(CURDIR)/.build"
	@set -eu; \
	stage="$(CURDIR)/.build/stage"; \
	rm -rf "$$stage"; \
	mkdir -p "$$stage/examples/agentscope"; \
	cp "$(REPO_ROOT)/pyproject.toml" "$(REPO_ROOT)/README.md" "$(REPO_ROOT)/README-zh.md" "$$stage/"; \
	mkdir -p "$$stage/src"; \
	cp -R "$(REPO_ROOT)/src/polaris_ai" "$$stage/src/"; \
	[ ! -f "$(REPO_ROOT)/LICENSE" ] || cp "$(REPO_ROOT)/LICENSE" "$$stage/"; \
	tar -c --exclude=.logs --exclude=.runtime --exclude=.build --exclude=__pycache__ \
		-C "$(REPO_ROOT)/examples" . | tar -x -C "$$stage/examples"; \
	find "$$stage" -type d \( -name .logs -o -name .runtime -o -name .build -o -name __pycache__ \) \
		-prune -exec rm -rf {} +; \
	tar -czf "$(CURDIR)/.build/$(DEMO_NAME).tar.gz" -C "$$stage" .; \
	rm -rf "$$stage"; \
	echo "packaged $(CURDIR)/.build/$(DEMO_NAME).tar.gz"

run: build
	"$(CURDIR)/bin" $(ARGS)

clean:
	rm -f "$(CURDIR)/bin" "$(CURDIR)/x86-bin"
	rm -rf "$(CURDIR)/.build"
