PYTHON ?= python3
BIN_DIR ?= $(HOME)/.local/bin
BIN := $(BIN_DIR)/llm-council-for-trae
LCT_DIR ?= $(HOME)/.LCT
SKILLS_DIR ?= $(HOME)/.agents/skills
SKILL_NAME := llm-council-for-trae
LCT_SKILL_SRC := $(LCT_DIR)/skills/$(SKILL_NAME)
LCT_SKILL_DEST := $(SKILLS_DIR)/$(SKILL_NAME)

.PHONY: install-local install-global install-skill test check

install-local:
	@mkdir -p "$(BIN_DIR)"
	@printf '%s\n' '#!/bin/sh' 'PYTHONPATH="$(CURDIR)/src$${PYTHONPATH:+:$$PYTHONPATH}" exec $(PYTHON) -m llm_council_for_trae.cli "$$@"' > "$(BIN)"
	@chmod +x "$(BIN)"
	@echo "installed $(BIN)"

install-global:
	@test -d "$(LCT_DIR)/src/llm_council_for_trae" || (echo "missing $(LCT_DIR)/src/llm_council_for_trae" >&2; exit 1)
	@test -f "$(LCT_SKILL_SRC)/SKILL.md" || (echo "missing $(LCT_SKILL_SRC)/SKILL.md" >&2; exit 1)
	@if [ -e "$(LCT_SKILL_DEST)" ] && [ ! -L "$(LCT_SKILL_DEST)" ]; then \
		echo "refusing to overwrite non-symlink $(LCT_SKILL_DEST)" >&2; \
		exit 1; \
	fi
	@mkdir -p "$(BIN_DIR)"
	@printf '%s\n' '#!/bin/sh' 'PYTHONPATH="$(LCT_DIR)/src$${PYTHONPATH:+:$$PYTHONPATH}" exec $(PYTHON) -m llm_council_for_trae.cli "$$@"' > "$(BIN)"
	@chmod +x "$(BIN)"
	@$(MAKE) --no-print-directory install-skill LCT_DIR="$(LCT_DIR)" SKILLS_DIR="$(SKILLS_DIR)"
	@echo "installed $(BIN)"

install-skill:
	@test -f "$(LCT_SKILL_SRC)/SKILL.md" || (echo "missing $(LCT_SKILL_SRC)/SKILL.md" >&2; exit 1)
	@mkdir -p "$(SKILLS_DIR)"
	@if [ -e "$(LCT_SKILL_DEST)" ] && [ ! -L "$(LCT_SKILL_DEST)" ]; then \
		echo "refusing to overwrite non-symlink $(LCT_SKILL_DEST)" >&2; \
		exit 1; \
	fi
	@ln -sfn "$(LCT_SKILL_SRC)" "$(LCT_SKILL_DEST)"
	@echo "installed $(LCT_SKILL_DEST)"

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

check: test
	PYTHONPATH=src $(PYTHON) -m llm_council_for_trae.cli --help >/dev/null
	PYTHONPATH=src $(PYTHON) -m llm_council_for_trae.cli doctor --json >/dev/null
