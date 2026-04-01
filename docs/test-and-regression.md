# Test and Regression Guide

## What Counts as a Regression

A regression is any change to the codebase, prompt, question set, or tool that makes our results worse or untrustworthy. Specifically:

| Symptom | Likely Cause |
|---|---|
| `total_billable_tokens` goes up for either LLM | A prompt got longer, or a question was made more ambiguous |
| `posix_compliance_rate` drops | A question was changed in a way that now leads the LLM away from the right tool |
| `valid_results` drops below `total_results` | A parser broke — JSON output from a CLI changed format |
| `mean_step_count` for Codex spikes above its Track 1 baseline | The Step-Up prompt is causing detours, not reducing them |
| Gemini shows `valid_results: 0` | The MCP prefix stripping broke, or the model API is down |
| A question contains the utility name | The Taboo rule was violated — that question's data is worthless |

---

## Before Every Benchmark Run

1. **Syntax check:**
   ```bash
   python3 -m py_compile run_benchmark.py
   ```
   If this fails, do not run anything. Fix the syntax error first.

2. **Dry run:**
   ```bash
   python3 run_benchmark.py --dry-run
   ```
   Verify the questions shown in the output do not contain any of the expected command names. This is how you catch a Taboo rule violation before wasting money on API calls.

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

## After Every Run

1. Check that a `summary-<timestamp>.json` was written to `results/`.
2. Open it and verify `valid_results` equals `total_results` for each LLM you ran.
3. If `valid_results < total_results`, open the individual result files in `results/<llm>/` to find which questions failed and why.

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

Run this before committing any changes to `benchmark_data.json`:

```bash
python3 run_benchmark.py --dry-run 2>&1
```

Review every question shown in the output. For each question, mentally check: does any word in the question match or closely resemble the `expected_commands` for that question?

Known high-risk words to watch for:
- "sort", "find", "split", "join" — exact command names
- "combine", "merge" — close synonyms for `join` or `paste`
- "link", "resolve" — close synonyms for `readlink`/`realpath`
- "schedule" + time of day — hints at `at`
- "checksum", "fingerprint" — partially hints at `cksum` but acceptable since it doesn't specify which tool

---

## Committing Changes

Before committing any change to `benchmark_data.json` or `run_benchmark.py`:

1. Run `python3 -m py_compile run_benchmark.py` — must pass.
2. Run `python3 run_benchmark.py --dry-run` — verify questions look correct.
3. Do not commit result files. The `results/` directory is gitignored.
4. Do not commit API keys, credentials, or cost data.

---

## Known Issues to Watch

- **Gemini 429 / MODEL_CAPACITY_EXHAUSTED:** The `gemini-3.1-pro-preview` model is frequently capacity-constrained. When this happens, Gemini returns non-JSON error output that fails parsing. Gemini is excluded from the default run until this stabilizes. Add `gemini` explicitly with `--llms claude codex gemini` when you want to include it.

- **Gemini daily quota planning:** In this repo, assume Gemini is only safe for one benchmark call every 30 seconds and no more than 50 model calls per day unless your active account limits show otherwise. That means:
  - Track 1 baseline with Gemini alone is safe: `python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30`
  - Track 2 Step-Up may exceed the daily quota because `TOOL_CALL: get_posix_syntax(...)` causes a second Gemini invocation for that question
  - If a run stops partway through, reuse the same results directory and resume on the next day

- **Codex step count creep:** Codex (GPT-5.4) tends to take 8–10 agentic steps even for simple questions. `mean_step_count` above 10 is a red flag — something in the prompt is triggering extra tool use. Check if the question wording is ambiguous or if the injected context is causing confusion.

- **Claude cache state:** Anthropic charges differently for cache hits vs. cache misses. The `tokens.input_cached` field in results tracks this. Back-to-back runs of the same questions will show lower costs due to caching. Run Track 1 and Track 2 in separate sessions if you want cold-cache numbers.
