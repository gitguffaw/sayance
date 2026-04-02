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

## Quick Start

No virtualenv or build step required. Pure stdlib Python 3.

```bash
# Syntax check
python3 -m py_compile run_benchmark.py

# Dry run (no API calls)
python3 run_benchmark.py --dry-run

# Single-provider baseline
python3 run_benchmark.py --llms claude

# Step-Up run
python3 run_benchmark.py --llms claude codex --inject-posix
```

## Gemini

Supported, but treat conservatively unless your account limits clearly allow more.

```bash
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30
```

Safe working assumptions: one call every 30 seconds, no more than 50 calls per day. A 30-question Track 1 run fits. Track 2 may not — the Step-Up simulation can trigger a second Gemini call per question.

If a run stops partway through, rerun the same command and the benchmark resumes from cached files.

## Output Files

```
results/<llm>/T##_run0.json     per-question results
results/summary-*.json          aggregate metrics
results/report-*.html           human-readable report
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
- Gemini CLI may prepend an `MCP issues detected...` line; the benchmark strips it before parsing.
- Codex uses `--skip-git-repo-check` because the benchmark is often run outside a normal git-repo workflow.

## Further Reading

- [docs/benchmarks.md](docs/benchmarks.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/test-and-regression.md](docs/test-and-regression.md)
- [CLAUDE.md](CLAUDE.md)
