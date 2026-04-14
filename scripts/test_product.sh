#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temp_root="$(mktemp -d)"

cleanup() {
  rm -rf "${temp_root}"
}
trap cleanup EXIT

pass_count=0
fail_count=0

pass() {
  echo "  PASS: $1"
  pass_count=$((pass_count + 1))
}

fail() {
  echo "  FAIL: $1"
  fail_count=$((fail_count + 1))
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

make_in() {
  # Run make with an isolated HOME
  local home="$1"; shift
  HOME="${home}" make -C "${repo_dir}" "$@" >/dev/null
}

lane_path_for() {
  echo "$1/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}

# Extract sorted utility names from an installed SKILL.md.
# Handles three formatting patterns:
#   1. Bullet entries:  "*   name: description"
#   2. Comma-separated bare lines: "uucp, uustat, uux"
#   3. CORE_TRIVIAL / SHELL_BUILTINS_MISC inline lists
# Strips everything after the first colon on bullet lines.
extract_skill_utilities() {
  local skill_file="$1"
  python3 - "${skill_file}" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path).read()
names = set()

# Only parse Discovery Map section (between "## Discovery Map" and "## Syntax Lookup")
tier1_match = re.search(r'## Discovery Map[^\n]*\n(.*?)## Syntax Lookup', text, re.DOTALL)
if not tier1_match:
    sys.exit("Could not find Discovery Map section in SKILL.md")
tier1 = tier1_match.group(1)

for line in tier1.splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    # Strip leading bullet marker if present
    bare = re.sub(r'^\*\s+', '', line)
    # Single-utility bullet: "name: description" (no commas before colon)
    m = re.match(r'^(\w+)\s*:', bare)
    if m and ',' not in bare.split(':')[0]:
        names.add(m.group(1).lower())
        continue
    # Comma-separated utility list: all tokens must be short lowercase words.
    # Handles both bare lines and bullet lines with commas (e.g., SCCS line)
    if ',' in bare:
        before_colon = re.split(r':', bare)[0]
        tokens = [t.strip().lower() for t in before_colon.split(',') if t.strip()]
        # Accept line only if ALL tokens look like utility names (1-12 chars, alpha/digits)
        if tokens and all(re.fullmatch(r'[a-z][a-z0-9_]{0,11}', t) for t in tokens):
            names.update(tokens)
for n in sorted(names):
    print(n)
PY
}

# Extract sorted utility names from installed posix-tldr.json
extract_tldr_utilities() {
  local tldr_file="$1"
  python3 -c "import json; print('\n'.join(sorted(k.lower() for k in json.load(open('${tldr_file}')))))"
}

# ---------------------------------------------------------------------------
# Installed-level drift check: assert SKILL.md, posix-tldr.json, and
# posix-lookup --list all agree on the same 155 utility names.
# ---------------------------------------------------------------------------
check_installed_drift() {
  local home="$1"
  local skill_dir="$2"
  local label="$3"
  local lane_path
  lane_path="$(lane_path_for "${home}")"

  local skill_names tldr_names list_names
  skill_names="$(extract_skill_utilities "${skill_dir}/SKILL.md")"
  tldr_names="$(extract_tldr_utilities "${skill_dir}/posix-tldr.json")"
  list_names="$(PATH="${lane_path}" posix-lookup --list | tr '[:upper:]' '[:lower:]' | sort)"

  local skill_count tldr_count list_count
  skill_count="$(echo "${skill_names}" | wc -l | tr -d ' ')"
  tldr_count="$(echo "${tldr_names}" | wc -l | tr -d ' ')"
  list_count="$(echo "${list_names}" | wc -l | tr -d ' ')"

  if [ "${skill_count}" -ne 155 ]; then
    fail "${label}: SKILL.md has ${skill_count} utilities, expected 155"
    return
  fi
  if [ "${tldr_count}" -ne 155 ]; then
    fail "${label}: posix-tldr.json has ${tldr_count} utilities, expected 155"
    return
  fi
  if [ "${list_count}" -ne 155 ]; then
    fail "${label}: posix-lookup --list has ${list_count} utilities, expected 155"
    return
  fi

  # Compare pairwise
  local diff_skill_tldr diff_tldr_list
  diff_skill_tldr="$(diff <(echo "${skill_names}") <(echo "${tldr_names}") || true)"
  diff_tldr_list="$(diff <(echo "${tldr_names}") <(echo "${list_names}") || true)"

  if [ -n "${diff_skill_tldr}" ]; then
    fail "${label}: SKILL.md and posix-tldr.json disagree on utility names"
    echo "${diff_skill_tldr}" | head -10
    return
  fi
  if [ -n "${diff_tldr_list}" ]; then
    fail "${label}: posix-tldr.json and posix-lookup --list disagree"
    echo "${diff_tldr_list}" | head -10
    return
  fi

  pass "${label}: all installed artifacts agree on 155 utilities"
}

# ---------------------------------------------------------------------------
# Test: install-all (existing test, enhanced with drift check)
# ---------------------------------------------------------------------------
echo "=== install-all ==="
home_all="${temp_root}/home-all"
mkdir -p "${home_all}"
make_in "${home_all}" install-all

claude_skill="${home_all}/.claude/skills/posix"
codex_skill="${home_all}/.codex/skills/posix"
lane_path="$(lane_path_for "${home_all}")"

# File presence
test -f "${claude_skill}/SKILL.md"       && pass "claude SKILL.md present"   || fail "claude SKILL.md missing"
test -x "${claude_skill}/posix-lookup"   && pass "claude posix-lookup exec"  || fail "claude posix-lookup not executable"
test -f "${claude_skill}/posix-tldr.json" && pass "claude posix-tldr.json"   || fail "claude posix-tldr.json missing"
test -f "${codex_skill}/SKILL.md"        && pass "codex SKILL.md present"    || fail "codex SKILL.md missing"
test -x "${codex_skill}/posix-lookup"    && pass "codex posix-lookup exec"   || fail "codex posix-lookup not executable"
test -f "${codex_skill}/posix-tldr.json"  && pass "codex posix-tldr.json"    || fail "codex posix-tldr.json missing"

# CLI functionality
PATH="${lane_path}" command -v posix-lookup >/dev/null && pass "CLI on PATH" || fail "CLI not on PATH"
PATH="${lane_path}" posix-lookup pax >/dev/null        && pass "lookup pax"  || fail "lookup pax failed"

# JSON mode
PATH="${lane_path}" posix-lookup --json od | python3 -c \
  "import json,sys; data=json.load(sys.stdin); assert 'od' in data and isinstance(data['od'], list)" \
  && pass "JSON mode od" || fail "JSON mode od failed"

# 155-count via --list
count="$(PATH="${lane_path}" posix-lookup --list | wc -l | tr -d ' ')"
test "${count}" -eq 155 && pass "--list count = 155" || fail "--list count = ${count}, expected 155"

# Installed-level drift check (both skill dirs)
check_installed_drift "${home_all}" "${claude_skill}" "drift-claude"
check_installed_drift "${home_all}" "${codex_skill}" "drift-codex"

# Uninstall
make_in "${home_all}" uninstall
test ! -e "${claude_skill}"               && pass "uninstall claude dir"    || fail "claude dir remains"
test ! -e "${codex_skill}"                && pass "uninstall codex dir"     || fail "codex dir remains"
test ! -e "${home_all}/.local/bin/posix-lookup" && pass "uninstall symlink" || fail "symlink remains"

# ---------------------------------------------------------------------------
# Test: install-claude only
# ---------------------------------------------------------------------------
echo ""
echo "=== install-claude only ==="
home_claude="${temp_root}/home-claude"
mkdir -p "${home_claude}"
make_in "${home_claude}" install-claude

claude_only="${home_claude}/.claude/skills/posix"
lane_claude="$(lane_path_for "${home_claude}")"

test -f "${claude_only}/SKILL.md"        && pass "claude-only SKILL.md"     || fail "claude-only SKILL.md missing"
test -x "${claude_only}/posix-lookup"    && pass "claude-only exec"         || fail "claude-only not executable"
PATH="${lane_claude}" posix-lookup pax >/dev/null && pass "claude-only lookup" || fail "claude-only lookup failed"

# Symlink should point to claude dir
link_target="$(readlink "${home_claude}/.local/bin/posix-lookup" 2>/dev/null || true)"
if [ "${link_target}" = "${claude_only}/posix-lookup" ]; then
  pass "claude-only symlink target correct"
else
  fail "claude-only symlink target: ${link_target}"
fi

check_installed_drift "${home_claude}" "${claude_only}" "drift-claude-only"

# Uninstall claude-only — symlink should be removed (no codex fallback)
make_in "${home_claude}" uninstall-claude
test ! -e "${claude_only}" && pass "claude-only dir removed" || fail "claude-only dir remains"
test ! -e "${home_claude}/.local/bin/posix-lookup" && pass "claude-only symlink removed" || fail "claude-only symlink remains"

# ---------------------------------------------------------------------------
# Test: install-codex only
# ---------------------------------------------------------------------------
echo ""
echo "=== install-codex only ==="
home_codex="${temp_root}/home-codex"
mkdir -p "${home_codex}"
make_in "${home_codex}" install-codex

codex_only="${home_codex}/.codex/skills/posix"
lane_codex="$(lane_path_for "${home_codex}")"

test -f "${codex_only}/SKILL.md"        && pass "codex-only SKILL.md"      || fail "codex-only SKILL.md missing"
test -x "${codex_only}/posix-lookup"    && pass "codex-only exec"          || fail "codex-only not executable"
PATH="${lane_codex}" posix-lookup pax >/dev/null && pass "codex-only lookup" || fail "codex-only lookup failed"

link_target="$(readlink "${home_codex}/.local/bin/posix-lookup" 2>/dev/null || true)"
if [ "${link_target}" = "${codex_only}/posix-lookup" ]; then
  pass "codex-only symlink target correct"
else
  fail "codex-only symlink target: ${link_target}"
fi

check_installed_drift "${home_codex}" "${codex_only}" "drift-codex-only"

make_in "${home_codex}" uninstall-codex
test ! -e "${codex_only}" && pass "codex-only dir removed" || fail "codex-only dir remains"
test ! -e "${home_codex}/.local/bin/posix-lookup" && pass "codex-only symlink removed" || fail "codex-only symlink remains"

# ---------------------------------------------------------------------------
# Test: partial uninstall — install-all then uninstall-codex
# (This is the broken case: symlink points to codex after install-all)
# ---------------------------------------------------------------------------
echo ""
echo "=== partial uninstall: install-all then uninstall-codex ==="
home_partial="${temp_root}/home-partial-codex"
mkdir -p "${home_partial}"
make_in "${home_partial}" install-all
make_in "${home_partial}" uninstall-codex

lane_partial="$(lane_path_for "${home_partial}")"
# Symlink should have been repointed to claude
link_target="$(readlink "${home_partial}/.local/bin/posix-lookup" 2>/dev/null || true)"
if [ "${link_target}" = "${home_partial}/.claude/skills/posix/posix-lookup" ]; then
  pass "partial uninstall-codex: symlink repointed to claude"
else
  fail "partial uninstall-codex: symlink target = ${link_target}"
fi
PATH="${lane_partial}" posix-lookup pax >/dev/null && pass "partial uninstall-codex: CLI works" || fail "partial uninstall-codex: CLI broken"

# ---------------------------------------------------------------------------
# Test: partial uninstall — install-all then uninstall-claude
# ---------------------------------------------------------------------------
echo ""
echo "=== partial uninstall: install-all then uninstall-claude ==="
home_partial2="${temp_root}/home-partial-claude"
mkdir -p "${home_partial2}"
make_in "${home_partial2}" install-all
make_in "${home_partial2}" uninstall-claude

lane_partial2="$(lane_path_for "${home_partial2}")"
link_target="$(readlink "${home_partial2}/.local/bin/posix-lookup" 2>/dev/null || true)"
if [ "${link_target}" = "${home_partial2}/.codex/skills/posix/posix-lookup" ]; then
  pass "partial uninstall-claude: symlink stays at codex"
else
  fail "partial uninstall-claude: symlink target = ${link_target}"
fi
PATH="${lane_partial2}" posix-lookup pax >/dev/null && pass "partial uninstall-claude: CLI works" || fail "partial uninstall-claude: CLI broken"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
total=$((pass_count + fail_count))
echo "Install Testing product conformance: ${pass_count}/${total} passed."
if [ "${fail_count}" -gt 0 ]; then
  exit 1
fi
