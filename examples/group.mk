# Forward build, package, run, and clean to demo subdirectories.
# A verify.py in this directory runs before the subdirectories.
# Root entry points delegate directly to their matching scripts.

UV ?= uv
ARGS ?=
SUBDIRS ?=

REPO_ROOT := $(shell dir="$(CURDIR)"; while [ "$$dir" != "/" ] && [ ! -f "$$dir/pyproject.toml" ]; do dir=$$(dirname "$$dir"); done; printf '%s\n' "$$dir")

.PHONY: build build-x86 package run verify clean

build build-x86 package run clean:
	@set -eu; for dir in $(SUBDIRS); do $(MAKE) -C "$(CURDIR)/$$dir" $@; done

ifdef VERIFY_COMMAND
verify:
	$(VERIFY_COMMAND) $(ARGS)
else
verify:
	@set -eu; \
	if [ -f "$(CURDIR)/verify.py" ]; then \
		cd "$(REPO_ROOT)" && $(UV) run --locked python "$(CURDIR)/verify.py"; \
	fi; \
	for dir in $(SUBDIRS); do $(MAKE) -C "$(CURDIR)/$$dir" verify; done
endif

.PHONY: verify-e2e logs cleanup

ifeq ($(CURDIR),$(REPO_ROOT)/examples)
verify-e2e:
	"$(CURDIR)/verify_e2e.sh" $(ARGS)

logs:
	"$(CURDIR)/logs.sh" $(ARGS)

cleanup:
	"$(CURDIR)/cleanup.sh" $(ARGS)
else
verify-e2e:
	bash -c 'source "$(REPO_ROOT)/examples/_internal/_scripts.sh"; example_manage "$(CURDIR)" verify-e2e "$$@"' -- $(ARGS)

logs:
	bash -c 'source "$(REPO_ROOT)/examples/_internal/_scripts.sh"; example_manage "$(CURDIR)" logs "$$@"' -- $(ARGS)

cleanup:
	bash -c 'source "$(REPO_ROOT)/examples/_internal/_scripts.sh"; example_manage "$(CURDIR)" cleanup "$$@"' -- $(ARGS)
endif
