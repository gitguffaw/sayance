# Benchmark Evidence

This page documents the benchmark results currently cited in the README.

Raw result directories are gitignored. This page records the specific artifacts, caveats, and interpretation needed to review the numbers without pretending the benchmark is stronger than it is.

Two artifact classes now exist in this repo:
- **Legacy artifacts** predate provenance hardening and may lack explicit corpus hashes, prompt hashes, and planned-result denominators.
- **Provenance-hardened artifacts** include a top-level `provenance` block plus `planned_results`, `provider_error_results`, `dropped_results`, and `planned_posix_compliance_rate`.

## Current Snapshot (40 Questions, k=1)

**Run date:** 2026-04-15  
**Corpus:** 40 intent-based questions  
**Mode:** Unaided vs. Bridge-Aided  
**Models:** `claude-opus-4-6`, `gpt-5.4`, `gemini-3.1-pro-preview`

**Artifacts:**
- Unaided summary: `results/unaided/claude-codex-gemini-D2026-04-15-T16-23-20/summary-claude-codex-gemini-D2026-04-15-T16-23-20.json`
- Bridge-Aided summary: `results/bridge-aided/claude-codex-gemini-D2026-04-15-T15-19-11/summary-claude-codex-gemini-D2026-04-15-T15-19-11.json`

Note: these raw result directories are gitignored; the paths above describe artifacts produced locally when re-running the snapshot. See the "Reproducing the Current Snapshot" section below.

These runs are useful for regression tracking and product direction. They are not publication-grade statistical claims.
They are also **legacy artifacts** relative to the current hardened schema: they do not carry the new provenance and planned-denominator fields yet.

### POSIX Compliance

| Provider | Unaided | Bridge-Aided | Delta |
|----------|---------|-------------|-------|
| Claude | 70.0% | 87.5% | +17.5 pts |
| Codex | 69.2% | 94.9% | +25.6 pts |
| Gemini | 60.7%* | 85.0% | +24.3 pts |

\* Gemini's unaided rate is computed over `28` visible results. That run had `12` provider errors.

These are **visible-row** compliance rates. In provenance-hardened summaries, the planned-row denominator is exposed separately as `planned_posix_compliance_rate`.

### Snapshot Table

| Metric | Claude | Codex | Gemini |
|---|---|---|---|
| Visible results (unaided) | 40/40 | 39/39** | 28/40 |
| Visible results (bridge-aided) | 40/40 | 39/39** | 40/40 |
| Compliance (unaided) | 70.0% | 69.2% | 60.7%* |
| Compliance (bridge-aided) | 87.5% | 94.9% | 85.0% |
| Mean output tokens (unaided) | 314 | 1,052 | 243 |
| Mean output tokens (bridge-aided) | 452 | 1,392 | 92 |
| Mean latency (unaided) | 10.1s | 22.3s | 20.7s |
| Mean latency (bridge-aided) | 14.4s | 32.1s | 24.4s |
| Non-POSIX substitutions (unaided) | 6 | 6 | 7 |
| Non-POSIX substitutions (bridge-aided) | 1 | 0 | 3 |
| Dominant bridge-aided style | `over_explaining` | `tool_heavy_detour` | `minimal_or_near_minimal` |

\** Codex is missing `T02` in both fresh reruns. Treat the current Codex snapshot as a `39`-question comparison until that benchmark-path issue is resolved.

### Lookup Engagement

Bridge-Aided mode does not guarantee that every provider will actually use the explicit lookup path. In the current rerun:

| Provider | Questions with `get_posix_syntax` calls | Notes |
|---|---:|---|
| Claude | 1/40 | Mostly benefited from prompt injection alone |
| Codex | 35/39 | Lookup path engaged heavily |
| Gemini | 37/40 | Lookup path engaged heavily |

This matters when interpreting the results. Sayance is currently a mix of injected context and optional lookup behavior, not a fully enforced tool gate.

## Hardened Summary Semantics

New summaries now distinguish:

- `posix_compliance_rate`: compliance over report-visible rows only.
- `planned_posix_compliance_rate`: compliance over all planned rows, including explicit provider-error rows.
- `planned_results`: intended result count for that provider/run.
- `provider_error_results`: explicit provider-error rows kept in the denominator-safe summary.
- `dropped_results`: planned minus materialized rows. In a healthy hardened run, this should stay at `0`.

This makes denominator drift visible instead of forcing readers to infer it from missing rows.

### Token-Cost Read

Raw billable tokens increased in Bridge-Aided mode for all three providers:

| Provider | Raw billable unaided | Raw billable bridge-aided |
|---|---:|---:|
| Claude | 1,967,017 | 3,358,750 |
| Codex | 1,075,623 | 1,579,552 |
| Gemini | 347,609 | 546,811 |

That is expected in the current simulation path. Bridge-Aided mode prepends the Discovery Map and may trigger a second model turn for tool replay.

The benchmark therefore also records **simulation-adjusted** Sayance billable totals:

| Provider | Unaided billable | Bridge-Aided simulation-adjusted billable |
|---|---:|---:|
| Claude | 1,967,017 | 3,320,074 |
| Codex | 1,075,623 | 959,177 |
| Gemini | 347,609 | 225,699 |

Interpretation:
- Claude improved on POSIX compliance, but did not show a token-efficiency win in this rerun.
- Codex improved strongly on compliance, and its adjusted Sayance cost improved despite verbose answers.
- Gemini improved on both visible compliance and adjusted Sayance cost, and its answers got much shorter.

## What This Snapshot Supports

- All three providers improved POSIX compliance in Bridge-Aided mode.
- Gemini showed the cleanest visible gain: better compliance, shorter answers, and no provider errors with Sayance enabled.
- Codex improved the most on POSIX-target selection, but remained verbose and tool-heavy.
- Claude improved on compliance and trap avoidance, but in this rerun rarely used the explicit lookup path.

## Known Confounds

- **k=1 only.** These runs are directional, not publication-grade.
- **Current cited snapshot is legacy.** The April 15 artifacts predate provenance hardening, so they do not expose the new corpus/prompt fingerprint fields or planned-result metrics.
- **Raw Sayance cost is an upper bound.** The harness replays prompt context during simulated lookup, so raw billable cost overstates the eventual value of correct-first-time behavior.
- **Prompt injection and lookup usage are not the same thing.** Claude mostly benefited from injected context without taking the explicit lookup path.
- **Gemini unaided is denominator-unstable.** The `12` provider errors in the unaided run mean part of the Sayance lift may reflect reliability, not just tool selection.
- **Codex coverage is incomplete in the latest rerun.** `T02` is missing in both fresh Codex tracks, so the current Codex table is based on a 39-question subset.

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

At minimum:

```bash
python3 run_benchmark.py --validate-bridge
python3 run_benchmark.py --llms claude codex gemini
python3 run_benchmark.py --llms claude codex gemini --inject-posix
```

Pinned models for Claude and Codex should be used when reproducing the current comparison:

```bash
python3 run_benchmark.py --llms claude codex --claude-model claude-opus-4-6 --codex-model gpt-5.4
python3 run_benchmark.py --llms claude codex --claude-model claude-opus-4-6 --codex-model gpt-5.4 --inject-posix
```

Gemini runs require conservative pacing and may need to be resumed if the provider fails mid-run.

## Update Policy

This page should be updated only when the README's cited benchmark snapshot changes or when a previously disclosed confound is resolved. Development runs belong in `results/`, not here.
