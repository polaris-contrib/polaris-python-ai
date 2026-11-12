# Forward example actions to demo subdirectories.

UV ?= uv
ARGS ?=
SUBDIRS ?=

REPO_ROOT := $(shell dir="$(CURDIR)"; while [ "$$dir" != "/" ] && [ ! -f "$$dir/pyproject.toml" ]; do dir=$$(dirname "$$dir"); done; printf '%s\n' "$$dir")

.PHONY: build build-x86 package run clean

build build-x86 package run clean:
	@set -eu; for dir in $(SUBDIRS); do $(MAKE) -C "$(CURDIR)/$$dir" $@; done
