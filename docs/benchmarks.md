# Benchmarks

## What We Are Measuring

The primary metric is **token cost** — how many tokens does an LLM burn to answer a real-world POSIX shell task? The secondary metric is **POSIX compliance** — did it actually give a correct, portable answer?

We are not measuring raw knowledge recall. We are measuring efficiency. A correct answer in 5 tokens beats a correct answer in 500. An answer that uses GNU extensions is wrong regardless of token count.

---

## The Question Set (`benchmark_data.json`)

30 task-based questions across three tiers of POSIX obscurity. Each question describes a real-world user intent and asks the LLM to provide a POSIX-compliant shell solution.

### Rules for Questions (The Taboo Rule)

Every question in the set must follow these rules. If a question violates any of them, the data it produces is corrupted and the question must be rewritten.

1. **No lexical leaks:** The name of the expected POSIX utility — or any close synonym — must never appear in the question. If the answer is `sort`, the word "sort" cannot be in the prompt. If the answer is `find`, the word "find" cannot be in the prompt.
2. **Intent-based framing:** The question must be phrased as a natural user problem or desired outcome, not a technical instruction. "I have a file and need to do X" not "Use utility Y to do X."
3. **No tool-leading:** Don't hint at the shape of the solution. Don't say "use a text processor" or "with a single command." Describe only what you want.
4. **Describe effects, not mechanisms:** Say "every occurrence should be replaced" not "use a substitution pattern."

### Question Tiers

- **Tier 1 (T01–T10):** Common utilities that any shell user has seen — `sort`, `find`, `sed`, `grep`, `cp`. An LLM that knows POSIX well should handle all of these.
- **Tier 2 (T11–T23):** Less common utilities that are POSIX-specified but often substituted with non-POSIX tools — `od` instead of `xxd`, `nl` instead of `cat -n`, `readlink`/`realpath` which are new in Issue 8.
- **Tier 3 (T24–T30):** Obscure or forgotten utilities that almost no LLM will reach for without help — `tsort`, `cksum`, `uuencode`, `mkfifo`, `pr`.

---

## The Two Benchmark Tracks

### Track 1: Raw Capability (No Help)

**Purpose:** Establish the LLM's true, unassisted POSIX baseline.

**What changes:** Nothing is injected. The LLM receives only the question. No `posix-core.md`, no syntax tool, no spec access.

**How to run:**
```bash
python3 run_benchmark.py --llms claude codex
```

**What to look for:**
- Does the LLM reach for non-POSIX tools (`tar`, `xxd`, `md5sum`)?
- Does it write Python scripts or complex Bash workarounds for things with a 1-line POSIX answer?
- Does it use GNU-only flags (`sed -i`, `grep -r`, `find -mmin`)?
- Token cost per question — this is the baseline we will compare against.

**Expected result:** High token cost on Tier 2 and Tier 3. Frequent non-POSIX substitutions. This is the problem we are solving.

---

### Track 2: Step-Up (With Our Changes)

**Purpose:** Prove that the Step-Up architecture reduces token cost and improves POSIX compliance.

**What changes:** `posix-core.md` is prepended to every prompt. The `get_posix_syntax` tool is available to the LLM during the run.

**How to run:**
```bash
python3 run_benchmark.py --llms claude codex --inject-posix
```

**What to look for:**
- Did token cost decrease compared to Track 1?
- Did the LLM call `get_posix_syntax` before answering? (Check `execution.tool_calls_by_type`)
- Did `trap_hits` drop to zero or near zero?
- Did `posix_compliance_rate` improve?

**Expected result:** Lower token cost. Fewer detours. Higher POSIX compliance. If this track doesn't beat Track 1, the architecture needs work.

---

## Running a Full Comparison

Run Track 1 first, then Track 2. Compare the summary files side by side.

```bash
# Track 1 — baseline, no help
python3 run_benchmark.py --llms claude codex

# Track 2 — with Step-Up architecture
python3 run_benchmark.py --llms claude codex --inject-posix
```

The key numbers to compare across the two runs:
- `total_billable_tokens` per LLM
- `mean_output_tokens` per LLM
- `posix_compliance_rate` per LLM
- `failure_modes` breakdown
- `mean_step_count` (Codex multi-step detours should collapse)

---

## Adding Gemini

Gemini is temporarily excluded from the default run while the `gemini-3.1-pro-preview` API capacity is unavailable. When it recovers, add it explicitly:

```bash
python3 run_benchmark.py --llms claude codex gemini
```

For this repo, use a conservative Gemini run profile unless your active account limits clearly allow more:

- Assume `1` benchmark call every `30` seconds.
- Assume no more than `50` model calls per day.
- Run Gemini alone, with `--max-workers 1`, so the benchmark never fans out concurrent Gemini calls.
- Track 1 baseline fits in one day: `30` questions = `30` Gemini calls.
- Track 2 does **not** reliably fit in one day: the Step-Up simulation can trigger a second Gemini call when the model emits `TOOL_CALL: get_posix_syntax(...)`, so a 30-question run can exceed `50` calls.
- Do not use Gemini as the judge if you are trying to stay within the daily quota.

Safe Track 1 baseline command:

```bash
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30
```

If a Gemini run stops early, rerun the same command on the next day. The benchmark will resume from the cached files already written under `results/gemini/`.

Note: The Gemini CLI prepends `MCP issues detected...` noise to its output. The benchmark strips this before JSON parsing. If Gemini results still show `valid_results: 0`, run a manual check:

```bash
gemini -p "echo test" -o json
```

And verify the output is parseable JSON after stripping the MCP prefix.

---

## Interpreting Results

| Metric | What it means |
|---|---|
| `total_billable_tokens` | Full cost of the run for this LLM |
| `mean_output_tokens` | Average verbosity per answer |
| `total_estimated_excess_output_tokens` | Tokens above the minimal correct answer |
| `posix_compliance_rate` | Fraction of answers that used only POSIX tools and flags |
| `issue8_refusal_count` | Times the LLM incorrectly said a valid Issue 8 tool "isn't POSIX" |
| `failure_modes` | Categorized breakdown of how answers went wrong |
| `mean_step_count` | How many agentic steps Codex took (1 = direct answer, higher = detour) |
