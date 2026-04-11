CLAUDE_SKILL_DIR := $(HOME)/.claude/skills/posix
CODEX_SKILL_DIR  := $(HOME)/.codex/skills/posix
BIN_DIR          := $(HOME)/.local/bin
REPO_DIR         := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: install install-all install-claude install-codex uninstall uninstall-claude uninstall-codex test test-product test-product-negative test-product-live-claude test-product-live-codex

install: install-all

install-all: install-claude install-codex
	@echo ""
	@echo "Installed:"
	@echo "  Claude -> $(CLAUDE_SKILL_DIR)/"
	@echo "  Codex  -> $(CODEX_SKILL_DIR)/"
	@echo "  CLI    -> $(BIN_DIR)/posix-lookup"
	@echo ""
	@echo "Restart Claude Code / Codex to load the skill."

install-claude:
	@mkdir -p $(CLAUDE_SKILL_DIR) $(BIN_DIR)
	cp skill/SKILL.md $(CLAUDE_SKILL_DIR)/SKILL.md
	cp skill/posix-lookup $(CLAUDE_SKILL_DIR)/posix-lookup
	cp skill/posix-tldr.json $(CLAUDE_SKILL_DIR)/posix-tldr.json
	chmod +x $(CLAUDE_SKILL_DIR)/posix-lookup
	ln -sf $(CLAUDE_SKILL_DIR)/posix-lookup $(BIN_DIR)/posix-lookup

install-codex:
	@mkdir -p $(CODEX_SKILL_DIR) $(BIN_DIR)
	cp skill/SKILL.md $(CODEX_SKILL_DIR)/SKILL.md
	cp skill/posix-lookup $(CODEX_SKILL_DIR)/posix-lookup
	cp skill/posix-tldr.json $(CODEX_SKILL_DIR)/posix-tldr.json
	chmod +x $(CODEX_SKILL_DIR)/posix-lookup
	ln -sf $(CODEX_SKILL_DIR)/posix-lookup $(BIN_DIR)/posix-lookup

uninstall:
	rm -rf $(CLAUDE_SKILL_DIR)
	rm -rf $(CODEX_SKILL_DIR)
	rm -f $(BIN_DIR)/posix-lookup
	@echo "Removed Claude+Codex skill installs and CLI."

uninstall-claude:
	rm -rf $(CLAUDE_SKILL_DIR)
	@LINK=$$(readlink $(BIN_DIR)/posix-lookup 2>/dev/null); \
	if [ "$$LINK" = "$(CLAUDE_SKILL_DIR)/posix-lookup" ]; then \
		if [ -x $(CODEX_SKILL_DIR)/posix-lookup ]; then \
			ln -sf $(CODEX_SKILL_DIR)/posix-lookup $(BIN_DIR)/posix-lookup; \
			echo "Repointed symlink to Codex copy."; \
		else \
			rm -f $(BIN_DIR)/posix-lookup; \
			echo "Removed dangling symlink."; \
		fi; \
	fi
	@echo "Removed Claude skill install."

uninstall-codex:
	rm -rf $(CODEX_SKILL_DIR)
	@LINK=$$(readlink $(BIN_DIR)/posix-lookup 2>/dev/null); \
	if [ "$$LINK" = "$(CODEX_SKILL_DIR)/posix-lookup" ]; then \
		if [ -x $(CLAUDE_SKILL_DIR)/posix-lookup ]; then \
			ln -sf $(CLAUDE_SKILL_DIR)/posix-lookup $(BIN_DIR)/posix-lookup; \
			echo "Repointed symlink to Claude copy."; \
		else \
			rm -f $(BIN_DIR)/posix-lookup; \
			echo "Removed dangling symlink."; \
		fi; \
	fi
	@echo "Removed Codex skill install."

test:
	@echo "=== posix-lookup pax ==="
	@python3 skill/posix-lookup pax
	@echo ""
	@echo "=== posix-lookup --list ==="
	@python3 skill/posix-lookup --list
	@echo ""
	@echo "=== posix-lookup --json od ==="
	@python3 skill/posix-lookup --json od
	@echo ""
	@echo "=== posix-lookup bad-util (expect error) ==="
	@python3 skill/posix-lookup bad-util 2>&1; true
	@echo ""
	@echo "All tests passed."

test-product:
	@./scripts/test_product.sh

test-product-negative:
	@./scripts/test_product_negative.sh

test-product-live-claude:
	@POSIX_LIVE_CANARY=1 ./scripts/test_product_live.sh claude

test-product-live-codex:
	@POSIX_LIVE_CANARY=1 ./scripts/test_product_live.sh codex
