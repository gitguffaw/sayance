#!/usr/bin/env bash
set -euo pipefail

# POSIX Semantic Bridge — one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/gitguffaw/posix/main/install.sh | bash
#
# Installs the POSIX bridge skill for Claude Code and/or Codex CLI.
# Pass "claude", "codex", or "all" (default) as an argument.

readonly REPO_RAW="https://raw.githubusercontent.com/gitguffaw/posix/main"
readonly TARGET="${1:-all}"

install_for() {
  local agent="$1"
  local skill_dir

  case "$agent" in
    claude) skill_dir="${HOME}/.claude/skills/posix" ;;
    codex)  skill_dir="${HOME}/.codex/skills/posix" ;;
    *) echo "Unknown agent: $agent" >&2; exit 1 ;;
  esac

  local bin_dir="${HOME}/.local/bin"

  echo "Installing POSIX bridge for ${agent}..."
  mkdir -p "${skill_dir}" "${bin_dir}"

  curl -fsSL "${REPO_RAW}/skill/SKILL.md"        -o "${skill_dir}/SKILL.md"
  curl -fsSL "${REPO_RAW}/skill/posix-lookup"     -o "${skill_dir}/posix-lookup"
  curl -fsSL "${REPO_RAW}/skill/posix-tldr.json"  -o "${skill_dir}/posix-tldr.json"

  chmod +x "${skill_dir}/posix-lookup"
  ln -sf "${skill_dir}/posix-lookup" "${bin_dir}/posix-lookup"

  echo "  Installed: ${skill_dir}/"
  echo "  CLI:       ${bin_dir}/posix-lookup"
}

case "$TARGET" in
  claude)
    install_for claude
    ;;
  codex)
    install_for codex
    ;;
  all)
    install_for claude
    install_for codex
    ;;
  *)
    echo "Usage: $0 [claude|codex|all]" >&2
    exit 1
    ;;
esac

echo ""
echo "Done. Restart Claude Code / Codex to load the skill."
echo "Verify: posix-lookup pax"
