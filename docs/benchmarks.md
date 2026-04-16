# Benchmarks

## What We Are Measuring

The primary metric is **token cost** — how many tokens does an LLM burn to answer a real-world POSIX shell task? The secondary metric is **POSIX compliance** — did it actually give a correct, portable answer?

We are not measuring raw knowledge recall. We are measuring efficiency. A correct answer in 5 tokens beats a correct answer in 500. An answer that uses GNU extensions is wrong regardless of token count.

---

## The Question Set (`benchmark_data.json`)

40 task-based questions across three tiers of POSIX obscurity. Each question describes a real-world user intent and asks the LLM to provide a POSIX-compliant shell solution.

### Rules for Questions (The Taboo Rule)

Every question in the set must follow these rules. If a question violates any of them, the data it produces is corrupted and the question must be rewritten.

**The canonical rules live in `benchmark_data.json` under `meta.question_rules`.** That is the single source of truth. In summary: no utility names, no "POSIX" or standards language, no tool-leading, and questions must read like a real user asking for help.

### Question Difficulty

- **Common (T01–T10):** Common utilities that any shell user has seen — `sort`, `find`, `sed`, `grep`, `cp`. An LLM that knows POSIX well should handle all of these.
- **Uncommon (T11–T23):** Less common utilities that are POSIX-specified but often substituted with non-POSIX tools — `od` instead of `xxd`, `nl` instead of `cat -n`, `readlink`/`realpath` which are new in Issue 8.
- **Obscure (T24–T40):** Obscure, task-specific, or often-overlooked utilities that frontier models still commonly miss without help — `tsort`, `cksum`, `uuencode`, `csplit`, `getconf`, `logger`, `nice`.

---

## Benchmark Modes

### Unaided (No Help)

**Purpose:** Establish the LLM's true, unassisted POSIX baseline.

**What changes:** Nothing is injected. The LLM receives only the question. No `sayance-core.md`, no syntax tool, no spec access.

**How to run:**
```bash
python3 run_benchmark.py --llms claude codex
```

**What to look for:**
- Does the LLM reach for non-POSIX tools (`tar`, `xxd`, `md5sum`)?
- Does it write Python scripts or complex Bash workarounds for things with a 1-line POSIX answer?
- Does it use GNU-only flags (`sed -i`, `grep -r`, `find -mmin`)?
- Token cost per question — this is the baseline we will compare against.

**Observed results (Unaided baseline, original 30-question corpus):**

| Provider | POSIX Compliance | Mean Output Tokens | Mean Steps |
|----------|------------------|--------------------|------------|
| Claude | 63.3% | 228 | 1.0 |
| Codex | 58.6% | 930 | 8.1 |
| Gemini | 65.4% | 215 | 1.0 |

Codex burns 4× more output tokens than Claude or Gemini due to multi-step agentic behavior. All three providers show significant non-POSIX substitution rates.

---

### Bridge-Aided (With Sayance)

**Purpose:** Prove that Sayance reduces token cost and improves POSIX compliance.

**What changes:** `sayance-core.md` is prepended to every prompt. The `get_posix_syntax` tool is available to the LLM during the run.

**How to run:**
```bash
python3 run_benchmark.py --llms claude codex --inject-posix
```

**What to look for:**
- Did token cost decrease compared to Unaided?
- Did the LLM call `get_posix_syntax` before answering? (Check `execution.tool_calls_by_type`)
- Did `trap_hits` drop to zero or near zero?
- Did `posix_compliance_rate` improve?

**Observed results (Bridge-Aided, original 30-question corpus):**

| Provider | POSIX Compliance | Mean Output Tokens | Mean Steps |
|----------|------------------|--------------------|------------|
| Claude | 76.7% | 374 | 2.0 |
| Codex | 86.7% | 1,289 | 9.5 |
| Gemini | 86.7% | 105 | 2.8 |

Compliance improved across all three providers. Gemini's output tokens dropped by more than half (215 → 105) — the biggest efficiency gain. Codex compliance jumped 28pp but output tokens increased; `tool_heavy_detour` was the dominant failure mode (25/30 questions), meaning Codex used the tool correctly but narrated every step at length.

---

## Running a Full Comparison

Run Unaided first, then Bridge-Aided. Compare the summary files side by side.

```bash
# Unaided — baseline, no help
python3 run_benchmark.py --llms claude codex

# Bridge-Aided — with Sayance
python3 run_benchmark.py --llms claude codex --inject-posix
```

Model version selection:
- By default, Claude runs are pinned to `claude-opus-4-6` and Codex runs are pinned to `gpt-5.4`.
- To change pins, pass `--claude-model <model-id>` and/or `--codex-model <model-id>`.
- Unpinned runs are blocked by default. To bypass intentionally, use `--claude-model auto` and/or `--codex-model auto` plus `--allow-unpinned-models`.

The key numbers to compare across the two runs:
- `total_billable_tokens` per LLM
- `total_input_tokens` and `total_cached_tokens` per LLM
- `mean_output_tokens` per LLM
- `mean_latency_seconds` per LLM
- `posix_compliance_rate` per LLM
- `failure_modes` breakdown
- `mean_step_count`

Comparison report rendering notes:
- Latency is shown in seconds (`Mean Latency (s)`).
- `Total Cost (USD)` is intentionally omitted from side-by-side view.
- `Billable - Output Tokens` is included to make billable/input-output relationships explicit.

---

## Adding Gemini

Gemini runs successfully but requires a conservative rate profile due to quota constraints:

```bash
python3 run_benchmark.py --llms claude codex gemini
```

Use a conservative Gemini run profile unless your active account limits clearly allow more:

- Assume `1` benchmark call every `30` seconds.
- Assume no more than `50` model calls per day.
- Run Gemini alone, with `--max-workers 1`, so the benchmark never fans out concurrent Gemini calls.
- Unaided baseline fits in one day: `40` questions = `40` Gemini calls.
- Bridge-Aided does **not** reliably fit in one day: the Sayance simulation can trigger a second Gemini call when the model emits `TOOL_CALL: get_posix_syntax(...)`, so a 40-question run can exceed `50` calls.
- Do not use Gemini as the judge if you are trying to stay within the daily quota.

Safe Unaided baseline command:

```bash
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30
```

If a Gemini run stops early, rerun the same command on the next day. The benchmark will resume from the cached files already written under `results/gemini/`.

Note: The Gemini CLI prepends `MCP issues detected...` noise to its output. The benchmark strips this before JSON parsing. If Gemini results still show `usage_valid_results: 0`, run a manual check:

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
| `usage_valid_results` | Number of non-error results with valid token telemetry |
| `report_visible_results` | Number of non-error results shown in reports (includes usage-invalid) |
| `usage_invalid_results` | Number of non-error results excluded from token metrics |
| `invalid_usage_reasons` | Breakdown of why usage was marked invalid |
| `total_input_tokens` | Sum of provider-reported input tokens over usage-valid records |
| `total_cached_tokens` | Sum of provider-reported cache-hit input tokens over usage-valid records |
| `mean_latency_seconds` | Mean visible-record latency in seconds |
| `posix_compliance_rate` | Fraction of answers that used only POSIX tools and flags |
| `issue8_refusal_count` | Times the LLM incorrectly said a valid Issue 8 tool "isn't POSIX" |
| `failure_modes` | Categorized breakdown of how answers went wrong |
| `mean_step_count` | How many agentic steps Codex took (1 = direct answer, higher = detour) |

Compatibility note: `valid_results` is still emitted as a backward-compatible alias of `usage_valid_results`.
