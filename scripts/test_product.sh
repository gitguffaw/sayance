#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_home="$(mktemp -d)"

cleanup() {
  rm -rf "${tmp_home}"
}
trap cleanup EXIT

run_make() {
  HOME="${tmp_home}" make -C "${repo_dir}" "$@" >/dev/null
}

lane_bin="${tmp_home}/.local/bin"
claude_skill="${tmp_home}/.claude/skills/posix"
codex_skill="${tmp_home}/.codex/skills/posix"
lane_path="${lane_bin}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

run_make install-all

test -f "${claude_skill}/SKILL.md"
test -x "${claude_skill}/posix-lookup"
test -f "${claude_skill}/posix-tldr.json"
test -f "${codex_skill}/SKILL.md"
test -x "${codex_skill}/posix-lookup"
test -f "${codex_skill}/posix-tldr.json"

PATH="${lane_path}" command -v posix-lookup >/dev/null
PATH="${lane_path}" posix-lookup pax >/dev/null

PATH="${lane_path}" posix-lookup --json od | python3 -c \
  "import json,sys; data=json.load(sys.stdin); assert 'od' in data and isinstance(data['od'], list)"

count="$(PATH="${lane_path}" posix-lookup --list | wc -l | tr -d ' ')"
test "${count}" -eq 155

python3 - <<PY
import json
from pathlib import Path
paths = [
    Path("${claude_skill}") / "posix-tldr.json",
    Path("${codex_skill}") / "posix-tldr.json",
]
for p in paths:
    data = json.loads(p.read_text())
    if len(data) != 155:
        raise SystemExit(f"{p} expected 155 entries, found {len(data)}")
PY

run_make uninstall

test ! -e "${claude_skill}"
test ! -e "${codex_skill}"
test ! -e "${lane_bin}/posix-lookup"

echo "Lane B product conformance checks passed."
