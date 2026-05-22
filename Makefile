PYTHON ?= python3
BIN_DIR ?= $(HOME)/.local/bin
BIN := $(BIN_DIR)/coco-llm-council

.PHONY: install-local test check

install-local:
	@mkdir -p "$(BIN_DIR)"
	@printf '%s\n' '#!/bin/sh' 'PYTHONPATH="$(CURDIR)/src$${PYTHONPATH:+:$$PYTHONPATH}" exec $(PYTHON) -m coco_llm_council.cli "$$@"' > "$(BIN)"
	@chmod +x "$(BIN)"
	@echo "installed $(BIN)"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

check: test
	PYTHONPATH=src $(PYTHON) -m coco_llm_council.cli --help >/dev/null
	PYTHONPATH=src $(PYTHON) -m coco_llm_council.cli doctor --json >/dev/null
