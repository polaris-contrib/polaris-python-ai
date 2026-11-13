ARGS ?=

.PHONY: verify verify-e2e logs cleanup

verify:
	"$(CURDIR)/verify.sh" $(ARGS)

verify-e2e:
	"$(CURDIR)/verify_e2e.sh" $(ARGS)

logs:
	"$(CURDIR)/logs.sh" $(ARGS)

cleanup:
	"$(CURDIR)/cleanup.sh" $(ARGS)
