# Test and Regression Guide

## What Counts as a Regression

A regression is any change to the codebase, prompt, question set, or tool that makes our results worse or untrustworthy. Specifically:

| Symptom | Likely Cause |
|---|---|
| `total_billable_tokens` goes up for either LLM | A prompt got longer, or a question was made more ambiguous |
| `posix_compliance_rate` drops | A question was changed in a way that now leads the LLM away from the right tool |
| `usage_valid_results` drops below `report_visible_results` | A parser broke, telemetry drifted, or usage was marked invalid |
| `mean_step_count` for Codex spikes above its Track 1 baseline | The Step-Up prompt is causing detours, not reducing them |
| Gemini shows `usage_valid_results: 0` | The MCP prefix stripping broke, or the model API is down |
| A question contains the utility name, "POSIX", or standards language | The Taboo rule was violated — that question's data is worthless |

---

## Dual-Lane Validation Model

Use both lanes together:

- **Lane A (legacy, unchanged):** benchmark simulation checks in `run_benchmark.py` for comparability and metric tracking.
- **Lane B (additive):** installed product-path conformance checks for `SKILL.md` + `posix-lookup`.

Lane A does not replace Lane B, and Lane B does not replace Lane A.

Lane B commands:

```bash
make test-product
make test-product-negative
```

---

## Before Every Benchmark Run

1. **Syntax check:**
   ```bash
   python3 -m py_compile run_benchmark.py benchmark_core/*.py
   ```
   If this fails, do not run anything. Fix the syntax error first.

2. **Dry run:**
   ```bash
   python3 run_benchmark.py --dry-run
   ```
   Verify the questions shown in the output do not contain any of the expected command names. This is how you catch a Taboo rule violation before wasting money on API calls. The current corpus should report 40 questions.

Model-selection note:
- By default, Claude/Codex runs are pinned to:
  - `claude-opus-4-6`
  - `gpt-5.4`
- To change pins, pass:
  - `--claude-model <model-id>`
  - `--codex-model <model-id>`
- Unpinned runs require explicit bypass:
  - `--claude-model auto` and/or `--codex-model auto`
  - plus `--allow-unpinned-models`

3. **Single-question smoke test** (optional but cheap):
   ```bash
   python3 run_benchmark.py --llms claude --questions T01
   ```
   Verify the result file is written to `results/claude/` and the JSON is valid.

For Gemini specifically, use a stricter smoke test shape:

```bash
python3 run_benchmark.py --llms gemini --questions T01 --max-workers 1 --delay 30
```

This keeps Gemini at one request every 30 seconds and avoids concurrent calls.

---

## Lane B Product Conformance Checks

Run these for packaging/distribution changes and before releasing skill updates:

1. Happy-path conformance:
   ```bash
   make test-product
   ```
2. Failure-injection sensitivity:
   ```bash
   make test-product-negative
   ```

`make test-product` verifies install/uninstall in an isolated `HOME`, Claude/Codex skill file placement, CLI discoverability, lookup behavior, and 155-entry coverage.

`make test-product-negative` intentionally breaks installed artifacts and confirms failures are detected for:
- missing installed file
- broken symlink target
- malformed installed JSON

## Lane B CI Enforcement Constraint (Current Repo)

Observed for `gitguffaw/posix` on 2026-04-03:
- GitHub Actions is enabled and workflows can run.
- Required status-check merge gating via branch protection is unavailable for the current private-repo plan.

Until repo plan/visibility changes, use this enforcement model:
1. Run Lane B locally before merge/release:
   ```bash
   make test-product
   make test-product-negative
   ```
2. Treat GitHub workflow runs as informational visibility, not a hard merge gate.

---

## After Every Run

1. Check that a `summary-<timestamp>.json` was written to `results/`.
2. Open it and verify `usage_valid_results` equals `report_visible_results` for healthy token accounting.
3. If `usage_valid_results < report_visible_results`, inspect `usage_invalid_results` and `invalid_usage_reasons`.
4. If `report_visible_results < total_results`, inspect provider errors in `errors` and per-question files under `results/<llm>/`.
5. If you used `--results-dir <custom>`, verify that directory now contains exactly one latest `summary-*.json` and one latest `report-*.html` (older timestamped artifacts are pruned automatically).

## Comparison Report Checks

When reviewing `comparison-*.html`, confirm:
- Latency metrics are shown in seconds (`Mean Latency (s)` and error latencies like `12.4s`).
- `Total Cost (USD)` is not present in side-by-side metrics.
- Token context rows are present (`Total Input Tokens`, `Total Cached Tokens`, `Billable - Output Tokens`).

---

## Manual Activation Canary (Lane B)

Use this quick human check to verify real session loading behavior:

1. Restart Claude Code or Codex.
2. Ask a representative task that should require Tier 1 discovery + Tier 2 lookup.
3. Confirm the response reflects bridge behavior (correct POSIX utility selection and lookup-informed syntax).
4. If behavior looks un-bridged, run `make test-product` and inspect installed skill paths first.

---

## Validating the Step-Up Architecture (Track 2 Specific)

After running Track 2 (`--inject-posix`), verify these specific things before declaring it a success:

### 1. The LLM actually used the tool

Check `execution.tool_calls_by_type` in the individual result files. You should see `get_posix_syntax` called for Tier 2 and Tier 3 questions. If it's absent, the LLM answered from training data alone — the architecture didn't engage.

```bash
# Quick check: count how many results show get_posix_syntax calls
grep -r "get_posix_syntax" results/claude/
```

### 2. Trap hits dropped

Compare `failure_modes.non_posix_substitution` between Track 1 and Track 2 summaries. If Track 2 still shows the same trap hit rate as Track 1, the Tier 1 semantic hooks are not working — the LLM isn't connecting user intent to the right tool.

### 3. Token cost actually went down

Compare `total_billable_tokens` between Track 1 and Track 2 for the same LLM. Track 2 will have slightly higher *input* tokens (because `posix-core.md` is prepended), but *output* tokens should drop significantly. If total billable tokens are higher in Track 2, we made things worse.

### 4. Issue 8 refusals are zero

Check `issue8_refusal_count` in both tracks. The LLM should never say that `readlink`, `realpath`, or `timeout` are "not POSIX" — they are standard as of Issue 8 (2024). Any refusal here is a failure the Step-Up should fix.

---

## Checking the Question Set for Taboo Violations

The canonical Taboo rules live in `benchmark_data.json` under `meta.question_rules`. Read those before reviewing questions.

Run this before committing any changes to `benchmark_data.json`:

```bash
python3 run_benchmark.py --dry-run 2>&1
```

Review every question shown in the output against the rules in `benchmark_data.json`. Watch especially for:
- Expected command names that are also English words ("at", "test", "split", "join", "find", "cut", "sort", "comm", "tr", "nl")
- The word "POSIX" or any standards/compliance language
- Descriptions that mirror the expected tool's interface (flag names, output format, argument structure)

---

## Committing Changes

Before committing any change to `benchmark_data.json`, `run_benchmark.py`, or `benchmark_core/`:

1. Run `python3 -m py_compile run_benchmark.py benchmark_core/*.py` — must pass.
2. Run `python3 run_benchmark.py --dry-run` — verify questions look correct.
3. Do not commit result files. The `results/` directory is gitignored.
4. Do not commit API keys, credentials, or cost data.

---

## Known Issues to Watch

- **Gemini timeouts:** In the original 30-question Track 1 baseline, Gemini (`gemini-3.1-pro-preview`) timed out on 4/30 questions (T04, T21, T26, T30). This appears to be latency variance rather than quota exhaustion — the corresponding 30-question Track 2 run completed with no timeouts. If you see timeouts, rerun the same command; the benchmark resumes from cached files.

- **Gemini daily quota planning:** In this repo, assume Gemini is only safe for one benchmark call every 30 seconds and no more than 50 model calls per day unless your active account limits show otherwise. That means:
  - Track 1 baseline with the current 40-question corpus still fits: `python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30`
  - Track 2 Step-Up may exceed the daily quota because `TOOL_CALL: get_posix_syntax(...)` causes a second Gemini invocation for a question
  - If a run stops partway through, reuse the same results directory and resume on the next day

- **Codex step count:** Codex (GPT-5.4) runs 8.1 mean steps in Track 1 and 9.5 in Track 2. This is normal behavior — Codex is agentic by default. `mean_step_count` above 12 is a red flag; check for ambiguous question wording or injected context causing extra tool loops.

- **Claude cache state:** Anthropic charges differently for cache hits vs. cache misses. The `tokens.input_cached` field in results tracks this. Back-to-back runs of the same questions will show lower costs due to caching. Run Track 1 and Track 2 in separate sessions if you want cold-cache numbers.
