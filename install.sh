#!/usr/bin/env bash
set -euo pipefail

check_old_brand_artifacts() {
  local found_old_brand="0"

  if [[ -d "${HOME}/.claude/skills/posix" ]]; then
    found_old_brand="1"
  fi

  if [[ -d "${HOME}/.codex/skills/posix" ]]; then
    found_old_brand="1"
  fi

  if [[ "${found_old_brand}" == "1" ]]; then
    echo "Notice: detected old-brand skill artifacts under ~/.claude/skills/posix and/or ~/.codex/skills/posix."
    echo "Notice: to remove them safely, run scripts/uninstall-old-brand.sh from a local checkout."
    echo ""
  fi
}

# Sayance — one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/main/install.sh | bash
#
# Installs the Sayance skill for Claude Code and/or Codex CLI.
# Pass "claude", "codex", or "all" (default) as an argument.

readonly REPO_RAW="https://raw.githubusercontent.com/gitguffaw/sayance/main"
readonly TARGET="${1:-all}"

check_old_brand_artifacts

install_for() {
  local agent="$1"
  local skill_dir

  case "$agent" in
    claude) skill_dir="${HOME}/.claude/skills/sayance" ;;
    codex)  skill_dir="${HOME}/.codex/skills/sayance" ;;
    *) echo "Unknown agent: $agent" >&2; exit 1 ;;
  esac

  local bin_dir="${HOME}/.local/bin"

  echo "Installing Sayance for ${agent}..."
  mkdir -p "${skill_dir}" "${bin_dir}"

  curl -fsSL "${REPO_RAW}/skill/SKILL.md"        -o "${skill_dir}/SKILL.md"
  curl -fsSL "${REPO_RAW}/skill/sayance-lookup"     -o "${skill_dir}/sayance-lookup"
  curl -fsSL "${REPO_RAW}/skill/sayance-tldr.json"  -o "${skill_dir}/sayance-tldr.json"

  chmod +x "${skill_dir}/sayance-lookup"
  ln -sf "${skill_dir}/sayance-lookup" "${bin_dir}/sayance-lookup"

  echo "  Installed: ${skill_dir}/"
  echo "  CLI:       ${bin_dir}/sayance-lookup"
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
echo "Verify: sayance-lookup pax"
