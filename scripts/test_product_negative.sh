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
      rm -f "${tmp_home}/.codex/skills/sayance/sayance-lookup"
      ;;
    malformed_json)
      printf '{broken\n' > "${tmp_home}/.codex/skills/sayance/sayance-tldr.json"
      ;;
    missing_data)
      rm -f "${tmp_home}/.codex/skills/sayance/sayance-tldr.json" "${tmp_home}/.claude/skills/sayance/sayance-tldr.json"
      ;;
    drift_skill)
      # Remove one utility (pax) from the installed SKILL.md to simulate drift
      # sed -i differs between macOS (BSD) and Linux (GNU)
      if sed --version >/dev/null 2>&1; then
        sed -i '/pax/d' "${tmp_home}/.claude/skills/sayance/SKILL.md"
      else
        sed -i '' '/pax/d' "${tmp_home}/.claude/skills/sayance/SKILL.md"
      fi
      ;;
    *)
      echo "Unknown mode: ${mode}"
      HOME="${tmp_home}" make -C "${repo_dir}" uninstall >/dev/null || true
      rm -rf "${tmp_home}"
      exit 1
      ;;
  esac

  local expected_fail=true

  if [ "${mode}" = "drift_skill" ]; then
    # For drift detection, we check that the installed SKILL.md utility count
    # no longer matches sayance-lookup --list count (142 vs 141).
    local skill_count list_count
    skill_count="$(python3 - "${tmp_home}/.claude/skills/sayance/SKILL.md" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
names = set()
for line in text.splitlines():
    line = line.strip()
    if not line or line.startswith('#') or line.startswith('```'):
        continue
    m = re.match(r'^\*\s+(\w+)\s*:', line)
    if m:
        names.add(m.group(1).lower())
        continue
    if ',' in line and not line.startswith('sayance') and not line.startswith('If'):
        parts = re.split(r':', line)[0]
        for part in re.split(r'[,\s]+', parts):
            word = part.strip().lower()
            if word and re.fullmatch(r'[a-z][a-z0-9_]*', word):
                names.add(word)
print(len(names))
PY
    )"
    list_count="$(PATH="${lane_path}" sayance-lookup --list | wc -l | tr -d ' ')"

    if [ "${skill_count}" -ne "${list_count}" ]; then
      # Drift detected — counts differ, which is what we want
      expected_fail=true
    else
      echo "FAIL: ${case_name} — SKILL.md count (${skill_count}) still matches --list (${list_count}) after removing pax"
      HOME="${tmp_home}" make -C "${repo_dir}" uninstall >/dev/null || true
      rm -rf "${tmp_home}"
      exit 1
    fi
  else
    # Standard negative test: sayance-lookup pax should fail
    if HOME="${tmp_home}" PATH="${lane_path}" sayance-lookup pax >/dev/null 2>&1; then
      echo "FAIL: ${case_name} did not fail as expected."
      HOME="${tmp_home}" make -C "${repo_dir}" uninstall >/dev/null || true
      rm -rf "${tmp_home}"
      exit 1
    fi
  fi

  HOME="${tmp_home}" make -C "${repo_dir}" uninstall >/dev/null || true
  rm -rf "${tmp_home}"
  echo "PASS: ${case_name}"
}

run_case "broken symlink target is detected" "broken_symlink"
run_case "malformed installed JSON is detected" "malformed_json"
run_case "missing installed JSON data is detected" "missing_data"
run_case "installed SKILL.md drift is detected" "drift_skill"

echo "Install Testing failure-injection sensitivity checks passed."
