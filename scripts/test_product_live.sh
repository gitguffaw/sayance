#!/usr/bin/env bash
set -euo pipefail

# Live canary test: installs Sayance into an isolated HOME,
# runs prompts through Claude/Codex CLI, and asserts the response
# recommends the correct POSIX utility (pax not tar, od not xxd).
#
# The assertion requires a word-boundary hit on the expected utility
# AND no non-negated mention of the trap utility. Phrases like "Use pax.
# Avoid tar." count as correct — see scripts/canary_assert.py.
#
# Canary failures are emitted as WARN, not hard failures, because LLM
# responses are nondeterministic. Only infrastructure errors set a
# non-zero exit code. Gate on WARN-in-stderr if you need stricter
# enforcement.
#
# Gated on SAYANCE_LIVE_CANARY=1.  Usage:
#   SAYANCE_LIVE_CANARY=1 ./scripts/test_product_live.sh [claude|codex|all]

# ---------------------------------------------------------------------------
# Gate: skip unless explicitly opted in
# ---------------------------------------------------------------------------
if [[ "${SAYANCE_LIVE_CANARY:-}" != "1" ]]; then
  echo "Skipping live canary (SAYANCE_LIVE_CANARY not set)"
  exit 0
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
readonly REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TIMEOUT_S=60
readonly PROVIDER_ARG="${1:-all}"

# Canary prompts — no "POSIX" or standards language (Taboo rule)
readonly PROMPT_ARCHIVE="I need to create a portable archive of a directory tree using only standard Unix utilities. What single utility should I use? Answer with just the utility name and a one-line example."
readonly PROMPT_HEXDUMP="I need to display a file's contents in hexadecimal using only standard Unix utilities. What single utility should I use? Answer with just the utility name and a one-line example."

# Track overall results: 0 = clean, 1 = infrastructure error
exit_code=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ts_iso() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# run_with_timeout SECONDS CMD [ARGS...]
# Prefers GNU `timeout`, falls back to `gtimeout` (homebrew coreutils),
# and finally to a Perl alarm-based fallback so default-PATH macOS
# (no coreutils installed) still enforces the canary timeout instead of
# exiting 127. Preserves GNU timeout's exit-code-124-on-timeout convention.
run_with_timeout() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "${secs}" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "${secs}" "$@"
  else
    perl -e '
      use strict; use warnings;
      my $timeout = shift @ARGV;
      my $pid = fork();
      die "fork: $!" unless defined $pid;
      if ($pid == 0) { exec { $ARGV[0] } @ARGV; exit 127; }
      eval {
        local $SIG{ALRM} = sub { die "__timeout__\n" };
        alarm $timeout;
        waitpid($pid, 0);
        alarm 0;
      };
      if ($@ && $@ eq "__timeout__\n") {
        kill "TERM", $pid;
        sleep 1;
        kill "KILL", $pid;
        waitpid($pid, 0);
        exit 124;
      }
      exit $? >> 8;
    ' "$secs" "$@"
  fi
}

# emit_telemetry canary provider expected trap pass response latency_s
emit_telemetry() {
  local canary="$1" provider="$2" expected="$3" trap_util="$4"
  local pass="$5" response="$6" latency_s="$7"
  # Escape response for safe JSON embedding
  local escaped
  escaped="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
  printf '{"canary":"%s","provider":"%s","expected":"%s","trap":"%s","pass":%s,"response":%s,"latency_s":%s,"timestamp":"%s"}\n' \
    "$canary" "$provider" "$expected" "$trap_util" "$pass" "$escaped" "$latency_s" "$(ts_iso)"
}

# triage_failure response — print diagnostic when a canary fails
triage_failure() {
  local response="$1"
  if echo "$response" | grep -qi "sayance-lookup\|sayance-tldr"; then
    echo "  TRIAGE: Bridge was discovered but model chose wrong utility." >&2
  else
    echo "  TRIAGE: Bridge was NOT discovered — skill may not be installed or loaded." >&2
  fi
}

# ---------------------------------------------------------------------------
# run_canary provider canary_name prompt expected trap_util
# ---------------------------------------------------------------------------
run_canary() {
  local provider="$1" canary="$2" prompt="$3" expected="$4" trap_util="$5"
  local tmp_home response rc start_s end_s latency_s pass lower

  tmp_home="$(mktemp -d)"
  # Cleanup this temp HOME on return
  # shellcheck disable=SC2064
  trap "rm -rf '${tmp_home}'" RETURN

  # Install bridge for this provider
  if ! HOME="${tmp_home}" make -C "${REPO_DIR}" "install-${provider}" >/dev/null 2>&1; then
    echo "FAIL [infra]: make install-${provider} failed" >&2
    exit_code=1
    return 1
  fi

  # Verify CLI is on the expected path
  local lane_bin="${tmp_home}/.local/bin"
  if [[ ! -x "${lane_bin}/sayance-lookup" ]]; then
    echo "FAIL [infra]: sayance-lookup not found after install" >&2
    exit_code=1
    return 1
  fi

  # Check that the provider CLI exists on the real PATH
  if ! command -v "$provider" >/dev/null 2>&1; then
    echo "FAIL [infra]: ${provider} CLI not found on PATH" >&2
    exit_code=1
    return 1
  fi

  # Run the prompt with timeout
  start_s="$(date +%s)"
  rc=0
  case "$provider" in
    claude)
      response="$(HOME="${tmp_home}" \
        run_with_timeout "${TIMEOUT_S}" \
        claude -p "$prompt" --output-format json 2>/dev/null)" || rc=$?
      ;;
    codex)
      response="$(HOME="${tmp_home}" \
        run_with_timeout "${TIMEOUT_S}" \
        codex exec --json --skip-git-repo-check "$prompt" 2>/dev/null)" || rc=$?
      ;;
  esac
  end_s="$(date +%s)"
  latency_s=$(( end_s - start_s ))

  # Timeout (exit code 124) or other infrastructure failure
  if [[ $rc -eq 124 ]]; then
    echo "FAIL [infra]: ${provider} timed out after ${TIMEOUT_S}s for canary ${canary}" >&2
    exit_code=1
    return 1
  elif [[ $rc -ne 0 ]]; then
    echo "FAIL [infra]: ${provider} exited ${rc} for canary ${canary}" >&2
    exit_code=1
    return 1
  fi

  # Assertion: word-boundary match on expected utility AND no non-negated
  # trap mention. Delegates to scripts/canary_assert.py, which reuses
  # benchmark_core.providers._trap_match_is_negated so phrases like
  # "Use pax. Avoid tar." count as correct.
  local assert_reason assert_rc
  assert_reason="$(printf '%s' "$response" | python3 "${REPO_DIR}/scripts/canary_assert.py" --expected "$expected" --trap "$trap_util" 2>&1 >/dev/null)" || assert_rc=$?
  assert_rc="${assert_rc:-0}"
  if [[ "$assert_rc" -eq 0 ]]; then
    pass="true"
  elif [[ "$assert_rc" -eq 1 ]]; then
    pass="false"
  else
    echo "FAIL [infra]: canary assertion helper failed (${assert_rc}) for ${provider} canary ${canary}: ${assert_reason}" >&2
    exit_code=1
    return 1
  fi

  # Emit telemetry
  emit_telemetry "$canary" "$provider" "$expected" "$trap_util" "$pass" "$response" "$latency_s"

  # Report result — failures are WARN (informational), not hard failures.
  # Callers that want to gate on canary outcome should grep stderr for WARN.
  if [[ "$pass" == "false" ]]; then
    echo "WARN: ${provider} canary '${canary}' — ${assert_reason#FAIL: }" >&2
    triage_failure "$response"
  else
    echo "PASS: ${provider} canary '${canary}' — found '${expected}'" >&2
  fi
}

# ---------------------------------------------------------------------------
# Determine which providers to test
# ---------------------------------------------------------------------------
providers=()
case "$PROVIDER_ARG" in
  claude) providers=(claude) ;;
  codex)  providers=(codex) ;;
  all)    providers=(claude codex) ;;
  *)
    echo "Usage: $0 [claude|codex|all]" >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# Run canaries
# ---------------------------------------------------------------------------
for provider in "${providers[@]}"; do
  run_canary "$provider" "archive" "$PROMPT_ARCHIVE" "pax" "tar"
  run_canary "$provider" "hexdump" "$PROMPT_HEXDUMP" "od"  "xxd"
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ $exit_code -eq 0 ]]; then
  echo "Live canary suite complete." >&2
else
  echo "Live canary suite finished with infrastructure errors." >&2
fi

exit $exit_code
