#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temp_root="$(mktemp -d)"

cleanup() {
  rm -rf "${temp_root}"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

expect_contains() {
  local text="$1"
  local expected="$2"
  local label="$3"
  [[ "${text}" == *"${expected}"* ]] || fail "${label}: missing '${expected}'"
}

echo "=== profile source contracts ==="

if mac_tar="$(python3 "${repo_dir}/skill/sayance-lookup" tar 2>&1)"; then
  fail "macos tar lookup unexpectedly succeeded"
else
  status=$?
fi
[[ "${status}" -eq 2 ]] || fail "macos tar lookup exited ${status}, expected 2"
expect_contains "${mac_tar}" "Not POSIX. Use 'pax' instead." "macos tar lookup"

mac_aliases="$(python3 "${repo_dir}/skill/sayance-lookup" --aliases)"
expect_contains "${mac_aliases}" "tar → pax" "macos aliases"

python3 "${repo_dir}/skill/sayance-lookup" --json tar | python3 -c \
  "import json,sys; data=json.load(sys.stdin); assert data['redirect']['to'] == 'pax'"

if python3 "${repo_dir}/skill/sayance-lookup" --local-tools >/dev/null 2>&1; then
  fail "macos lookup unexpectedly accepted --local-tools"
fi

omarchy_tar="$(python3 "${repo_dir}/profiles/omarchy/sayance-lookup" tar)"
expect_contains "${omarchy_tar}" "Omarchy:" "omarchy tar lookup"
expect_contains "${omarchy_tar}" "Strict POSIX alternative: pax" "omarchy tar lookup"

omarchy_tools="$(python3 "${repo_dir}/profiles/omarchy/sayance-lookup" --local-tools)"
expect_contains "${omarchy_tools}" "rg:" "omarchy local tools"
expect_contains "${omarchy_tools}" "sha256sum:" "omarchy local tools"

python3 "${repo_dir}/profiles/omarchy/sayance-lookup" --json tar | python3 -c \
  "import json,sys; data=json.load(sys.stdin); assert data['tar']['strict_posix'] == 'pax'; assert 'omarchy' in data['tar']"

echo "=== make install profile matrix ==="

for profile in macos omarchy; do
  for target in claude codex all; do
    home_dir="${temp_root}/${profile}-${target}"
    mkdir -p "${home_dir}"

    case "${target}" in
      claude) make_target="install-claude" ;;
      codex) make_target="install-codex" ;;
      all) make_target="install-all" ;;
    esac

    HOME="${home_dir}" make -s -C "${repo_dir}" PROFILE="${profile}" "${make_target}" >/dev/null

    cli="${home_dir}/.local/bin/sayance-lookup"
    [[ -x "${cli}" ]] || fail "${profile}/${target}: CLI missing"
    [[ "$("${cli}" --version)" == "sayance 1.1.0" ]] || fail "${profile}/${target}: version mismatch"
    [[ "$("${cli}" --list | wc -l | tr -d ' ')" -eq 142 ]] || fail "${profile}/${target}: list count mismatch"

    case "${target}" in
      claude)
        [[ -d "${home_dir}/.claude/skills/sayance" ]] || fail "${profile}/${target}: Claude skill missing"
        [[ ! -e "${home_dir}/.codex" ]] || fail "${profile}/${target}: unexpected Codex files"
        skill_file="${home_dir}/.claude/skills/sayance/SKILL.md"
        ;;
      codex)
        [[ -d "${home_dir}/.codex/skills/sayance" ]] || fail "${profile}/${target}: Codex skill missing"
        [[ ! -e "${home_dir}/.claude" ]] || fail "${profile}/${target}: unexpected Claude files"
        skill_file="${home_dir}/.codex/skills/sayance/SKILL.md"
        ;;
      all)
        [[ -d "${home_dir}/.claude/skills/sayance" ]] || fail "${profile}/${target}: Claude skill missing"
        [[ -d "${home_dir}/.codex/skills/sayance" ]] || fail "${profile}/${target}: Codex skill missing"
        skill_file="${home_dir}/.codex/skills/sayance/SKILL.md"
        ;;
    esac

    if [[ "${profile}" == "macos" ]]; then
      grep -q '^# Sayance$' "${skill_file}" || fail "${profile}/${target}: wrong skill"
      if "${cli}" tar >/dev/null 2>&1; then
        fail "${profile}/${target}: tar unexpectedly succeeded"
      else
        status=$?
      fi
      [[ "${status}" -eq 2 ]] || fail "${profile}/${target}: tar exited ${status}, expected 2"
    else
      grep -q '^# Sayance for Omarchy$' "${skill_file}" || fail "${profile}/${target}: wrong skill"
      "${cli}" tar | grep -q 'Omarchy:' || fail "${profile}/${target}: Omarchy tar guidance missing"
      "${cli}" --local-tools | grep -q '^rg:' || fail "${profile}/${target}: local tools missing"
    fi

    HOME="${home_dir}" make -s -C "${repo_dir}" uninstall >/dev/null
  done
done

if HOME="${temp_root}/invalid" make -s -C "${repo_dir}" PROFILE=invalid install >/dev/null 2>&1; then
  fail "invalid make profile unexpectedly succeeded"
fi
[[ ! -e "${temp_root}/invalid/.claude" && ! -e "${temp_root}/invalid/.codex" ]] || \
  fail "invalid make profile wrote files"

invalid_installer_home="${temp_root}/invalid-installer"
mkdir -p "${invalid_installer_home}"
if HOME="${invalid_installer_home}" SAYANCE_PROFILE=invalid bash "${repo_dir}/install.sh" >/dev/null 2>&1; then
  fail "invalid installer profile unexpectedly succeeded"
fi
[[ ! -e "${invalid_installer_home}/.claude" && ! -e "${invalid_installer_home}/.codex" ]] || \
  fail "invalid installer profile wrote files"

echo "Profile contracts passed."
