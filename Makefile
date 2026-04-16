CLAUDE_SKILL_DIR := $(HOME)/.claude/skills/sayance
CODEX_SKILL_DIR  := $(HOME)/.codex/skills/sayance
BIN_DIR          := $(HOME)/.local/bin
REPO_DIR         := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: install install-all install-claude install-codex uninstall uninstall-claude uninstall-codex test test-product test-product-negative test-product-live-claude test-product-live-codex test-repo verify

install: install-all

install-all: install-claude install-codex
	@echo ""
	@echo "Installed:"
	@echo "  Claude -> $(CLAUDE_SKILL_DIR)/"
	@echo "  Codex  -> $(CODEX_SKILL_DIR)/"
	@echo "  CLI    -> $(BIN_DIR)/sayance-lookup"
	@echo ""
	@echo "Restart Claude Code / Codex to load the skill."

install-claude:
	@mkdir -p $(CLAUDE_SKILL_DIR) $(BIN_DIR)
	cp skill/SKILL.md $(CLAUDE_SKILL_DIR)/SKILL.md
	cp skill/sayance-lookup $(CLAUDE_SKILL_DIR)/sayance-lookup
	cp skill/sayance-tldr.json $(CLAUDE_SKILL_DIR)/sayance-tldr.json
	chmod +x $(CLAUDE_SKILL_DIR)/sayance-lookup
	ln -sf $(CLAUDE_SKILL_DIR)/sayance-lookup $(BIN_DIR)/sayance-lookup

install-codex:
	@mkdir -p $(CODEX_SKILL_DIR) $(BIN_DIR)
	cp skill/SKILL.md $(CODEX_SKILL_DIR)/SKILL.md
	cp skill/sayance-lookup $(CODEX_SKILL_DIR)/sayance-lookup
	cp skill/sayance-tldr.json $(CODEX_SKILL_DIR)/sayance-tldr.json
	chmod +x $(CODEX_SKILL_DIR)/sayance-lookup
	ln -sf $(CODEX_SKILL_DIR)/sayance-lookup $(BIN_DIR)/sayance-lookup

uninstall:
	rm -rf $(CLAUDE_SKILL_DIR)
	rm -rf $(CODEX_SKILL_DIR)
	rm -f $(BIN_DIR)/sayance-lookup
	@echo "Removed Claude+Codex skill installs and CLI."

uninstall-claude:
	rm -rf $(CLAUDE_SKILL_DIR)
	@LINK=$$(readlink $(BIN_DIR)/sayance-lookup 2>/dev/null); \
	if [ "$$LINK" = "$(CLAUDE_SKILL_DIR)/sayance-lookup" ]; then \
		if [ -x $(CODEX_SKILL_DIR)/sayance-lookup ]; then \
			ln -sf $(CODEX_SKILL_DIR)/sayance-lookup $(BIN_DIR)/sayance-lookup; \
			echo "Repointed symlink to Codex copy."; \
		else \
			rm -f $(BIN_DIR)/sayance-lookup; \
			echo "Removed dangling symlink."; \
		fi; \
	fi
	@echo "Removed Claude skill install."

uninstall-codex:
	rm -rf $(CODEX_SKILL_DIR)
	@LINK=$$(readlink $(BIN_DIR)/sayance-lookup 2>/dev/null); \
	if [ "$$LINK" = "$(CODEX_SKILL_DIR)/sayance-lookup" ]; then \
		if [ -x $(CLAUDE_SKILL_DIR)/sayance-lookup ]; then \
			ln -sf $(CLAUDE_SKILL_DIR)/sayance-lookup $(BIN_DIR)/sayance-lookup; \
			echo "Repointed symlink to Claude copy."; \
		else \
			rm -f $(BIN_DIR)/sayance-lookup; \
			echo "Removed dangling symlink."; \
		fi; \
	fi
	@echo "Removed Codex skill install."

test:
	@echo "=== sayance-lookup pax ==="
	@python3 skill/sayance-lookup pax
	@echo ""
	@echo "=== sayance-lookup --list ==="
	@python3 skill/sayance-lookup --list
	@echo ""
	@echo "=== sayance-lookup --json od ==="
	@python3 skill/sayance-lookup --json od
	@echo ""
	@echo "=== sayance-lookup bad-util (expect error) ==="
	@python3 skill/sayance-lookup bad-util 2>&1; true
	@echo ""
	@echo "All tests passed."

test-product:
	@./scripts/test_product.sh

test-product-negative:
	@./scripts/test_product_negative.sh

test-product-live-claude:
	@SAYANCE_LIVE_CANARY=1 ./scripts/test_product_live.sh claude

test-product-live-codex:
	@SAYANCE_LIVE_CANARY=1 ./scripts/test_product_live.sh codex

test-repo:
	@python3 scripts/verify_repo.py

verify:
	python3 -m py_compile run_benchmark.py benchmark_core/*.py
	python3 -m unittest
	$(MAKE) test-repo
	$(MAKE) test-product
	$(MAKE) test-product-negative
