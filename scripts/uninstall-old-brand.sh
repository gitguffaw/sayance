#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--dry-run]" >&2
}

ensure_home_is_safe() {
  if [[ -z "${HOME:-}" ]]; then
    echo "Error: HOME is unset or empty." >&2
    exit 1
  fi
}

ensure_within_home() {
  local path="$1"

  case "$path" in
    "${HOME}"/*) ;;
    *)
      echo "Error: refusing to touch path outside HOME: ${path}" >&2
      exit 1
      ;;
  esac
}

confirm_delete() {
  local answer

  if ! read -r -p "Delete this target? [y/N] " answer; then
    answer=""
  fi

  answer="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
  [[ "$answer" == "y" || "$answer" == "yes" ]]
}

remove_directory() {
  local path="$1"

  ensure_within_home "$path"

  if [[ ! -d "$path" ]]; then
    echo "Missing: ${path}"
    missing_count=$((missing_count + 1))
    return 0
  fi

  echo "Target: ${path}"
  existing_count=$((existing_count + 1))

  if [[ "$dry_run" == "1" ]]; then
    echo "[dry-run] Would remove directory: ${path}"
    dry_run_count=$((dry_run_count + 1))
    return 0
  fi

  if confirm_delete; then
    rm -r "$path"
    echo "Removed: ${path}"
    removed_count=$((removed_count + 1))
  else
    echo "Skipped: ${path}"
    skipped_count=$((skipped_count + 1))
  fi
}

remove_symlink() {
  local path="$1"
  local link_target

  ensure_within_home "$path"

  if [[ ! -e "$path" && ! -L "$path" ]]; then
    echo "Missing: ${path}"
    missing_count=$((missing_count + 1))
    return 0
  fi

  if [[ ! -L "$path" ]]; then
    echo "Skipped: ${path} (not a symlink)"
    skipped_count=$((skipped_count + 1))
    return 0
  fi

  link_target="$(readlink "$path")"
  if [[ "$link_target" != *"/skills/posix/"* ]]; then
    echo "Skipped: ${path} (unexpected symlink target: ${link_target})"
    skipped_count=$((skipped_count + 1))
    return 0
  fi

  echo "Target: ${path}"
  existing_count=$((existing_count + 1))

  if [[ "$dry_run" == "1" ]]; then
    echo "[dry-run] Would remove symlink: ${path} -> ${link_target}"
    dry_run_count=$((dry_run_count + 1))
    return 0
  fi

  if confirm_delete; then
    rm "$path"
    echo "Removed: ${path}"
    removed_count=$((removed_count + 1))
  else
    echo "Skipped: ${path}"
    skipped_count=$((skipped_count + 1))
  fi
}

case "${1:-}" in
  "")
    dry_run="0"
    ;;
  --dry-run)
    dry_run="1"
    ;;
  *)
    usage
    exit 1
    ;;
esac

ensure_home_is_safe

readonly CLAUDE_SKILL_DIR="${HOME}/.claude/skills/posix"
readonly CODEX_SKILL_DIR="${HOME}/.codex/skills/posix"
readonly LEGACY_BIN="${HOME}/.local/bin/posix-lookup"

existing_count=0
removed_count=0
skipped_count=0
missing_count=0
dry_run_count=0

remove_directory "${CLAUDE_SKILL_DIR}"
remove_directory "${CODEX_SKILL_DIR}"
remove_symlink "${LEGACY_BIN}"

echo ""
echo "Summary:"
echo "  existing targets: ${existing_count}"
echo "  removed: ${removed_count}"
echo "  skipped: ${skipped_count}"
echo "  missing: ${missing_count}"
if [[ "$dry_run" == "1" ]]; then
  echo "  dry-run removals previewed: ${dry_run_count}"
fi
