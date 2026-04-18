# Benchmarks

## What We Are Measuring

The primary metric is **POSIX compliance** — did it actually choose a correct,
portable tool path? The secondary metric is **token cost** — how much verbosity or
invocation overhead was added to reach that answer.

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

**Observed results (Unaided baseline, Wave-3, 40-question corpus, 2026-04-17):**

| Provider | POSIX Compliance | Mean Output Tokens | Mean Steps |
|----------|------------------|--------------------|------------|
| Claude (`claude-opus-4-6`) | 65.0% | 203 | 1.00 |
| Codex (`gpt-5.4`)          | 66.7% | 1,035 | 7.74 |

Codex burns 5× more output tokens than Claude due to multi-step agentic behavior. Both providers show non-POSIX substitution rates of ~15% in the unaided baseline (Claude: 5/40 non-POSIX, 9/40 workaround; Codex: 6/40 non-POSIX, 7/40 workaround).

Gemini was deferred from Wave-3 because bridge-aided mode exceeds the daily quota; the prior 2026-04-15 unaided Gemini result (60.7%) is preserved in [docs/evidence.md](evidence.md#historical-snapshot-2026-04-15).

---

### Bridge-Aided (With Sayance)

**Purpose:** Measure tool-selection compliance for POSIX tasks and track
bridge-aided behavior end-to-end.

Token cost is a secondary observation. It is provider-dependent: Codex
saves billable tokens; Claude pays a cache-amplification tax in the
headless `claude -p --output-format json` flow.

**What changes:** `sayance-core.md` is prepended to every prompt. For non-trivial commands, the LLM is instructed to invoke `sayance-lookup <utility>` in bash to fetch POSIX syntax before answering.

**How to run:**
```bash
python3 run_benchmark.py --llms claude codex --inject-posix
```

**What to look for:**
- Is tool selection improving compared to Unaided, and is POSIX compliance
  rising?
- Did the LLM call `sayance-lookup` before answering? (Check `execution.tool_calls_by_type`)
- Did `failure_modes.workaround_instead_of_native_utility` drop to near zero?
- Did `posix_compliance_rate` improve?

**Observed results (Bridge-Aided, Wave-3, 40-question corpus, 2026-04-17):**

| Provider | POSIX Compliance | Mean Output Tokens | Mean Steps | Δ Billable |
|----------|------------------|--------------------|------------|-----------:|
| Claude (`claude-opus-4-6`) | 82.5% (+17.5pp) | 514 | 1.05 | +203% |
| Codex (`gpt-5.4`)          | 92.5% (+25.8pp) | 2,140 | 17.0 | **−23%** |

Compliance improved for both providers. Codex is a clean win: 11 fixes,
0 regressions, and 23% lower billable tokens. Claude shows +9 fixes vs.
2 regressions (T25, T29 — both verbose "needs approval" responses).
`workaround_instead_of_native_utility` collapsed for both providers
(Claude 9→1, Codex 7→1) — the strongest single signal that the bridge
redirects "I'll just write a script" intent into POSIX utility selection.

`over_explaining` rose for both providers (Claude 14→29, Codex 24→27)
— bridge-aided answers grow longer because the Discovery Map gives the
LLMs more context to discuss tradeoffs.

Codex's mean step count more than doubled (7.74 → 17.0) without a matching
rise in actual `sayance-lookup` calls (1/40 across both providers). The
extra steps are internal Codex reasoning; the bridge prompt expands the
solution space the model considers.

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
- Bridge-Aided does **not** reliably fit in one day: the Sayance simulation can trigger a second Gemini call when the model emits a `sayance-lookup` command call, so a 40-question run can exceed `50` calls.
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
