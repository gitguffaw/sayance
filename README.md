# posix

**LLMs are bad at shell tasks. This benchmark proves it — and measures how bad.**

Every time you ask an AI assistant for a shell command, it reasons out loud, hedges, reaches for `grep` when `cut` was right there, and bills you for the detour. This project measures that waste precisely: token by token, utility by utility, across 30 real POSIX shell tasks.

The deeper question: if we hand the model a compact POSIX reference before it answers, does it stop burning tokens on things it should already know?

## What It Measures

Two things:

- **Token cost** — how many tokens the model actually burned (vs. the minimal correct answer)
- **POSIX compliance** — whether the model reached for the right standard utility or substituted something non-POSIX

`benchmark_data.json` contains 30 intent-based questions across three tiers:

| Tier | Examples |
|------|---------|
| Tier 1 | `sort`, `find`, `sed`, `grep` |
| Tier 2 | `od`, `nl`, `readlink`, `realpath` |
| Tier 3 | `tsort`, `cksum`, `uuencode`, `mkfifo`, `pr` |

Each question has a known minimal correct answer. The benchmark measures the gap.

## Two Tracks

### Track 1: Raw Capability

The model gets only the question. No hints, no reference material.

This is the baseline — how models perform cold.

```bash
python3 run_benchmark.py --llms claude codex
```

### Track 2: Step-Up

The benchmark prepends `posix-core.md` and simulates a syntax lookup step using `posix-tldr.json`.

This tests the hypothesis: does a compact POSIX reference reduce detours and improve compliance?

```bash
python3 run_benchmark.py --llms claude codex --inject-posix
```

Compare Track 1 vs Track 2 on the same model. If the Step-Up reduces output waste and lifts compliance, the reference is worth building.

## Results (30 questions, k=1, all three providers)

### Track 1 — Raw Capability (no reference material)

| Provider | Mean Output Tokens | POSIX Compliance | Top Failure Mode |
|----------|-------------------:|:----------------:|------------------|
| Claude | 228 | 63.3% | over_explaining (10) |
| Codex | 930 | 58.6% | over_explaining (14) |
| Gemini | 215 | 65.4% | over_explaining (11) |

### Track 2 — Step-Up (with `posix-core.md` + syntax lookup)

| Provider | Mean Output Tokens | POSIX Compliance | Top Failure Mode |
|----------|-------------------:|:----------------:|------------------|
| Claude | 374 | 76.7% | over_explaining (18) |
| Codex | 1,289 | 86.7% | tool_heavy_detour (25) |
| Gemini | 105 | 86.7% | minimal_or_near_minimal (24) |

### What Changed

- **Compliance went up across the board.** Codex and Gemini jumped from ~60% to ~87%. Claude improved from 63% to 77%.
- **Gemini got more concise.** Output tokens dropped 51% (215 → 105) while compliance rose 21 points. The reference material let it answer shorter and better.
- **Codex and Claude got more verbose.** Output tokens increased — but that's tool narration overhead, not wrong answers. Both used the lookup tool correctly; Codex narrated every step.
- **The real cost question is Track 3's job.** Track 1/2 only prove compliance in a controlled text-analysis environment. The hypothesis: a wrong first answer triggers retries and debugging that burn far more tokens than the Step-Up overhead. Track 3 will measure this by actually executing the suggested commands.

## Quick Start

No virtualenv or build step required. Pure stdlib Python 3.

```bash
# Syntax check
python3 -m py_compile run_benchmark.py

# Dry run (no API calls)
python3 run_benchmark.py --dry-run

# Single-provider baseline
python3 run_benchmark.py --llms claude

# All three providers
python3 run_benchmark.py --llms claude codex gemini

# Step-Up run
python3 run_benchmark.py --llms claude codex gemini --inject-posix
```

For Gemini, add `--max-workers 1 --delay 30` if you're on a tight quota. See Notes below.

## Output Files

```
results/
  by-provider/<llm>/current/    per-question Track 1 results (T01_run0.json … T30_run0.json)
  by-provider/<llm>/stepup/     per-question Track 2 results
  by-run/track1-<provider>/     aggregate summary + HTML report for Track 1
  by-run/track2-<provider>/     aggregate summary + HTML report for Track 2
  by-run/final-comparison/      three-way comparison report + merged JSON summaries
```

Results are gitignored and not committed.

## What to Look At

The numbers that matter most:

| Field | What it tells you |
|-------|------------------|
| `total_billable_tokens` | Total cost of the run |
| `mean_output_tokens` | Average verbosity per answer |
| `total_estimated_excess_output_tokens` | Estimated waste vs. minimal answer |
| `posix_compliance_rate` | How often the model reached for the right tool |
| `issue8_refusal_count` | How often the model incorrectly rejected a valid POSIX utility |
| `failure_modes` | Breakdown of how answers went wrong |
| `mean_step_count` | Average reasoning steps per answer |

## Repository Map

| File | Purpose |
|------|---------|
| `run_benchmark.py` | Main CLI — provider adapters, parsing, grading, reporting |
| `benchmark_data.json` | Question set with expected answers and required concepts |
| `posix-utilities.txt` | All 155 POSIX Issue 8 utilities (source of truth) |
| `posix-core.md` | Tier 1 semantic map (injected in Track 2) |
| `posix-tldr.json` | Syntax lookup source (injected in Track 2) |

## Notes

- POSIX.1-2024 Issue 8 is canonical: [pubs.opengroup.org](https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html)
- `readlink`, `realpath`, and `timeout` are POSIX in Issue 8. Models trained on older data will flag them as non-POSIX — that's a scoreable failure.
- Gemini CLI may prepend an `MCP issues detected...` line; the benchmark strips it before parsing. Gemini is safe at one call every 30 seconds, max 50 calls/day on most accounts. A 30-question Track 1 fits; Track 2 may exceed the daily limit since the Step-Up simulation can trigger a second call per question.
- Codex uses `--skip-git-repo-check` because the benchmark is often run outside a normal git-repo workflow.

## Further Reading

- [docs/benchmarks.md](docs/benchmarks.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/test-and-regression.md](docs/test-and-regression.md)
- [CLAUDE.md](CLAUDE.md)
