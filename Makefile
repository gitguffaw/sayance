SKILL_DIR := $(HOME)/.claude/skills/posix
BIN_DIR   := $(HOME)/.local/bin
REPO_DIR  := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: install uninstall test

install:
	@mkdir -p $(SKILL_DIR) $(BIN_DIR)
	cp skill/SKILL.md $(SKILL_DIR)/SKILL.md
	cp skill/posix-lookup $(SKILL_DIR)/posix-lookup
	cp posix-tldr.json $(SKILL_DIR)/posix-tldr.json
	chmod +x $(SKILL_DIR)/posix-lookup
	ln -sf $(SKILL_DIR)/posix-lookup $(BIN_DIR)/posix-lookup
	@echo ""
	@echo "Installed:"
	@echo "  Skill  -> $(SKILL_DIR)/"
	@echo "  CLI    -> $(BIN_DIR)/posix-lookup"
	@echo ""
	@echo "Restart Claude Code to load the skill."

uninstall:
	rm -rf $(SKILL_DIR)
	rm -f $(BIN_DIR)/posix-lookup
	@echo "Removed skill and CLI."

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
