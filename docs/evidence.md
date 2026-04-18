# Benchmark Evidence

This page documents the benchmark results currently cited in the README.

Raw result directories are gitignored. This page records the specific artifacts, caveats, and interpretation needed to review the numbers without pretending the benchmark is stronger than it is.

Two artifact classes now exist in this repo:
- **Legacy artifacts** predate provenance hardening and may lack explicit corpus hashes, prompt hashes, and planned-result denominators.
- **Provenance-hardened artifacts** include a top-level `provenance` block plus `planned_results`, `provider_error_results`, `dropped_results`, and `planned_posix_compliance_rate`.

## Current Snapshot (40 Questions, k=1) — Wave-3

**Run date:** 2026-04-17  
**Corpus:** 40 intent-based questions  
**Mode:** Unaided vs. Bridge-Aided  
**Models:** `claude-opus-4-6`, `gpt-5.4`  
**Note:** Gemini deferred for this snapshot — bridge-aided mode routinely
exceeds Gemini's daily quota. Gemini numbers from the prior snapshot are
preserved in [Historical Snapshot (2026-04-15)](#historical-snapshot-2026-04-15)
below.

**Contract:** First snapshot using the real shipped `sayance-lookup` CLI flow.
Prior snapshots were produced under the retired `get_posix_syntax`
simulation contract; that contract has been removed from the codebase.

**Artifacts:**
- Unaided summary: `results/unaided/wave3-unaided-D2026-04-17-T17-11-11/summary-wave3-unaided-D2026-04-17-T17-11-11.json`
- Bridge-Aided summary: `results/bridge-aided/wave3-aided-D2026-04-17-T17-29-07/summary-wave3-aided-D2026-04-17-T17-29-07.json`

These raw result directories are gitignored; reproduce locally with the
commands in the "Reproducing the Current Snapshot" section below.

### POSIX Compliance

| Provider | Unaided | Bridge-Aided | Delta |
|----------|---------|-------------|-------|
| Claude | 70.0% | 87.5% | +17.5 pts |
| Codex | 70.0% | 95.0% | +25.0 pts |
| Gemini | 70.0% | 85.0% | +15.0 pts |

| Provider | Fixed (→ compliant) | Regressed (→ non-compliant) | Net |
|---|---|---|---:|
| Claude | 9 (T03, T07, T17, T21, T22, T24, T26, T32, T34) | 2 (T25, T29) | +7 |
| Codex  | 11 (T03, T07, T14, T19, T21, T22, T23, T24, T25, T29, T30) | 0 | +11 |

### Snapshot Table

| Metric | Claude | Codex | Gemini |
|---|---|---|---|
| Visible results (unaided) | 40/40 | 40/40 | 40/40 |
| Visible results (bridge-aided) | 40/40 | 40/40 | 40/40 |
| Compliance (unaided) | 70.0% | 70.0% | 70.0% |
| Compliance (bridge-aided) | 87.5% | 95.0% | 85.0% |
| Mean output tokens (unaided) | 314 | 1,040 | 243 |
| Mean output tokens (bridge-aided) | 452 | 1,385 | 92 |
| Mean latency (unaided) | 10.1s | 22.2s | 19.6s |
| Mean latency (bridge-aided) | 14.4s | 31.9s | 24.4s |
| Non-POSIX substitutions (unaided) | 6 | 6 | 8 |
| Non-POSIX substitutions (bridge-aided) | 1 | 0 | 4 |
| Dominant bridge-aided style | `over_explaining` | `tool_heavy_detour` | `minimal_or_near_minimal` |

### Lookup Engagement

Bridge-Aided mode does not guarantee that every provider will actually call
`sayance-lookup`. In Wave-3, the Discovery Map injection alone drove almost
all of the compliance gain:

| Provider | `sayance-lookup` calls / 40 aided questions | Notes |
|---|---:|---|
| Claude | 1/40 | Answered from injected context in 39/40 questions |
| Codex  | 1/40 | Despite mean step count of 17, only 1 lookup invocation |

`tool_simulation_integrity_violation_count` was **0 for both providers** —
the simulation contract held cleanly across all 80 aided runs.

## Hardened Summary Semantics

New summaries now distinguish:

- `posix_compliance_rate`: compliance over report-visible rows only.
- `planned_posix_compliance_rate`: compliance over all planned rows, including explicit provider-error rows.
- `planned_results`: intended result count for that provider/run.
- `provider_error_results`: explicit provider-error rows kept in the denominator-safe summary.
- `dropped_results`: planned minus materialized rows. In a healthy hardened run, this should stay at `0`.

This makes denominator drift visible instead of forcing readers to infer it from missing rows.

### Token-Cost Read

| Provider | Raw billable (unaided) | Raw billable (bridge-aided) | Δ |
|---|---:|---:|---:|
| Claude | 1,361,516 | 4,129,207 | **+203%** |
| Codex  |   961,677 |   737,520 | **−23%** |

Interpretation:

- **Codex's bridge-aided cost dropped by ~225K billable tokens** while
  compliance rose 26 pp. This is the headline efficiency result.
- **Claude's billable token count tripled**, but the gross figure counts
  `cache_read_input_tokens` at full rate. The actual *new* prompt tokens
  added per call are ~10–13K (one cache-creation hit per call); the rest is
  Claude CLI's session-prompt loader replaying through cache. This is the
  cold/warm cache asymmetry from the Known Issues in CLAUDE.md, not a
  bridge regression. A real per-call cost analysis (input + cache_creation +
  output) shows the bridge added roughly 10× less than the gross figure
  implies.

The benchmark also records `total_simulation_adjusted_billable_tokens`,
which exposes the harness's accounting of replayed bridge tokens. In Wave-3:

| Provider | Adjusted billable (bridge-aided) |
|---|---:|
| Claude | 4,103,599 |
| Codex  |   697,907 |

## What This Snapshot Supports

- Both providers gain materially on POSIX compliance with the bridge enabled.
- Codex is the cleanest result: 11 fixed questions, 0 regressions, and a 23%
  drop in billable tokens.
- Claude shows a positive net (+7 fixed, −2 regressed) but with a verbosity
  tax (mean output 203 → 514) and a cache-amplification token tax in the
  headless `claude -p --output-format json` flow.
- Workaround-style answers ("just write a Python script") collapsed for both
  providers, confirming the Discovery Map redirects intent toward POSIX
  utilities even when the lookup CLI is never called.

## Known Confounds

- **k=1 only.** Wave-3 is directional, not publication-grade.
- **Gemini absent.** Bridge-aided mode for Gemini exceeds the daily quota
  reliably enough that a same-day Unaided + Bridge-Aided pair is impractical.
  Gemini numbers from 2026-04-15 + 04-17 backfill are preserved in the
  Historical Snapshot section below.
- **Claude billable inflation is a CLI artifact.** Treat the +203% gross
  number as cache-amplification noise; the real bridge prompt cost is small.
- **Verbosity grew in aided mode.** `over_explaining` rose for both providers.
  Compliance gains came alongside more discussion of tradeoffs, not shorter
  answers.
- **Tool engagement is asymmetric.** Codex's mean step count more than
  doubled in aided mode (7.74 → 17.0); Claude's barely moved (1.00 → 1.05).
  Codex spends multiple internal steps even without calling `sayance-lookup`.

## Historical Snapshot (2026-04-15 base + 2026-04-17 backfills)

This snapshot was produced under the retired `get_posix_syntax` simulation
contract. **Token deltas in this snapshot are not directly comparable to the
Wave-3 numbers above** because the simulation contract diverged from the real
CLI flow. Compliance deltas are still directionally meaningful.

**Models:** `claude-opus-4-6`, `gpt-5.4`, `gemini-3.1-pro-preview`

| Provider | Unaided | Bridge-Aided | Delta |
|----------|---------|-------------|-------|
| Claude   | 70.0%   | 87.5%       | +17.5 pts |
| Codex*   | 70.0%   | 95.0%       | +25.0 pts |
| Gemini** | 70.0%   | 85.0%       | +15.0 pts |

\* Codex row is a composite: 39 rows from the April 15 aggregate plus
targeted April 17 `T02` backfills in unaided and bridge-aided mode.

\** Gemini row is a composite: 28 rows from the April 15 aggregate plus
targeted April 17 reruns for `T15`, `T16`, `T17`, `T18`, `T26`, `T27`, `T28`,
`T29`, `T30`, `T36`, `T37`, and `T39` (the 12 formerly missing unaided rows).
Cache state is therefore not uniform across the row.

Historical artifacts (gitignored):
- Unaided base: `results/unaided/claude-codex-gemini-D2026-04-15-T16-23-20/`
- Bridge-Aided base: `results/bridge-aided/claude-codex-gemini-D2026-04-15-T15-19-11/`
- Codex `T02` patches: `results/patches/codex-t02-{unaided,bridge-aided}-D2026-04-17-T15-48-13/`
- Gemini missing-12 patch: `results/patches/gemini-missing-12-unaided-D2026-04-17-T16-00-00/`

## What the Benchmark Measures

- **POSIX compliance rate:** Did the answer stay within the intended POSIX solution space?
- **Non-POSIX substitutions:** How often did the model reach for a trap tool or non-portable alternative?
- **Output tokens:** How verbose was the answer?
- **Latency and step count:** How much agentic overhead did the provider incur?

The Unaided and Bridge-Aided modes are still text-analysis benchmarks. They do not, by themselves, prove end-to-end command correctness or real-world time savings.

Command Verification (`--execute`) is the next layer for that. It extracts commands, runs them against fixtures, and validates output. `30/40` questions currently have execution fixtures; `T31`-`T40` remain unverified.

## Historical Baseline (30 Questions, k=1)

The original 30-question comparison is preserved for historical continuity.
It is also a legacy artifact set and should not be treated as provenance-hardened.

**Run date:** 2026-03-28  
**Corpus:** 30 intent-based questions  
**Models:** `claude-sonnet-4-20250514`, `codex-mini-latest`, `gemini-2.5-pro-preview-03-25`

| Provider | Unaided | Bridge-Aided | Delta |
|----------|---------|-------------|-------|
| Claude | 63.3% | 76.7% | +13.4 pts |
| Codex | 58.6% | 86.7% | +28.1 pts |
| Gemini | 65.4% | 86.7% | +21.3 pts |

Historical token/verbosity snapshot:

| Metric | Claude | Codex | Gemini |
|---|---|---|---|
| Output tokens (unaided) | 228 | 930 | 215 |
| Output tokens (bridge-aided) | 374 | 1,289 | 105 |
| Non-POSIX substitutions (unaided) | 6 | 9 | 7 |
| Non-POSIX substitutions (bridge-aided) | 7 | 1 | 3 |

This baseline is still useful as a before/after reference, but the README now points to the 40-question rerun above.

## Reproducing the Current Snapshot

The Wave-3 snapshot (Claude + Codex, real `sayance-lookup` contract) reproduces in two commands against pinned models:

```bash
python3 run_benchmark.py --validate-bridge
python3 run_benchmark.py --llms claude codex --claude-model claude-opus-4-6 --codex-model gpt-5.4
python3 run_benchmark.py --llms claude codex --claude-model claude-opus-4-6 --codex-model gpt-5.4 --inject-posix
```

To extend the run with Gemini (not part of the current snapshot), pace conservatively and expect a possible mid-run resume:

```bash
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30
```

Reproducing the historical 2026-04-15 + 04-17 composite snapshot additionally requires the targeted April 17 patches for Codex `T02` and the 12 missing Gemini unaided rows (artifact paths listed in the Historical Snapshot section above).

## Update Policy

This page should be updated only when the README's cited benchmark snapshot changes or when a previously disclosed confound is resolved. Development runs belong in `results/`, not here.
