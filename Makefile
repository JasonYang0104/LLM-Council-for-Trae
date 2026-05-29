PYTHON ?= python3
BIN_DIR ?= $(HOME)/.local/bin
BIN := $(BIN_DIR)/llm-council-for-trae

.PHONY: install-local test check

install-local:
	@mkdir -p "$(BIN_DIR)"
	@printf '%s\n' '#!/bin/sh' 'PYTHONPATH="$(CURDIR)/src$${PYTHONPATH:+:$$PYTHONPATH}" exec $(PYTHON) -m llm_council_for_trae.cli "$$@"' > "$(BIN)"
	@chmod +x "$(BIN)"
	@echo "installed $(BIN)"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

check: test
	PYTHONPATH=src $(PYTHON) -m llm_council_for_trae.cli --help >/dev/null
	PYTHONPATH=src $(PYTHON) -m llm_council_for_trae.cli doctor --json >/dev/null
