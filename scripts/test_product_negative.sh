#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_case() {
  local case_name="$1"
  local mode="$2"
  local tmp_home
  local lane_path
  tmp_home="$(mktemp -d)"
  lane_path="${tmp_home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

  HOME="${tmp_home}" make -C "${repo_dir}" install-all >/dev/null

  case "${mode}" in
    broken_symlink)
      rm -f "${tmp_home}/.codex/skills/posix/posix-lookup"
      ;;
    malformed_json)
      printf '{broken\n' > "${tmp_home}/.codex/skills/posix/posix-tldr.json"
      ;;
    missing_data)
      rm -f "${tmp_home}/.codex/skills/posix/posix-tldr.json" "${tmp_home}/.claude/skills/posix/posix-tldr.json"
      ;;
    *)
      echo "Unknown mode: ${mode}"
      HOME="${tmp_home}" make -C "${repo_dir}" uninstall >/dev/null || true
      rm -rf "${tmp_home}"
      exit 1
      ;;
  esac

  if HOME="${tmp_home}" PATH="${lane_path}" posix-lookup pax >/dev/null 2>&1; then
    echo "FAIL: ${case_name} did not fail as expected."
    HOME="${tmp_home}" make -C "${repo_dir}" uninstall >/dev/null || true
    rm -rf "${tmp_home}"
    exit 1
  fi

  HOME="${tmp_home}" make -C "${repo_dir}" uninstall >/dev/null || true
  rm -rf "${tmp_home}"
  echo "PASS: ${case_name}"
}

run_case "broken symlink target is detected" "broken_symlink"
run_case "malformed installed JSON is detected" "malformed_json"
run_case "missing installed JSON data is detected" "missing_data"

echo "Lane B failure-injection sensitivity checks passed."
