# posix

A stdlib-only Python benchmark for measuring how many tokens LLMs burn answering POSIX shell tasks.

The benchmark is built around POSIX.1-2024 (Issue 8). It measures two things:

- Token cost: how expensive the answer was
- POSIX compliance: whether the answer used the right standard utility and avoided non-POSIX substitutions

This repo exists to answer a practical question: if LLMs are wasteful or wrong on shell tasks, is a compact POSIX "step-up" system worth building?

## What It Benchmarks

`benchmark_data.json` contains 30 intent-based shell questions across three tiers:

- Tier 1: common utilities like `sort`, `find`, `sed`, `grep`
- Tier 2: less common but standard utilities like `od`, `nl`, `readlink`, `realpath`
- Tier 3: obscure POSIX tools like `tsort`, `cksum`, `uuencode`, `mkfifo`, `pr`

Each question has a minimal correct POSIX answer. The benchmark compares model responses against that baseline and records token usage, latency, failure modes, and optional judge scores.

## The Two Tracks

### Track 1: Raw Capability

The model gets only the question. No injected POSIX map, no syntax lookup step.

Use this to establish the baseline.

```bash
python3 run_benchmark.py --llms claude codex
```

### Track 2: Step-Up

The benchmark prepends `posix-core.md` and simulates a syntax lookup flow using `posix-tldr.json`.

Use this to test whether the Step-Up architecture reduces detours and improves compliance.

```bash
python3 run_benchmark.py --llms claude codex --inject-posix
```

## Quick Start

No virtualenv or build step is required.

```bash
# Syntax check
python3 -m py_compile run_benchmark.py

# Dry run
python3 run_benchmark.py --dry-run

# Single-provider baseline
python3 run_benchmark.py --llms claude

# Claude/Codex Step-Up
python3 run_benchmark.py --llms claude codex --inject-posix
```

## Gemini

Gemini is supported, but in this repo it should be treated conservatively unless your active account limits clearly allow more.

Use this safe Track 1 baseline shape:

```bash
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30
```

Working assumptions for Gemini in this repo:

- one benchmark call every 30 seconds
- no more than 50 model calls per day
- run Gemini alone
- do not use Gemini as the judge if you are trying to stay within the daily quota

Under that assumption, a 30-question Track 1 run fits in one day. Track 2 may not, because the Step-Up simulation can trigger a second Gemini call for a question.

If a Gemini run stops partway through, rerun the same command later and let the benchmark resume from cached files.

## Output Files

Each run writes per-question JSON plus summary/report artifacts:

- `results/<llm>/T##_run0.json`
- `results/summary-*.json`
- `results/report-*.html`

Generated results are gitignored and should not be committed.

## Repository Map

- [run_benchmark.py](run_benchmark.py): main CLI, provider adapters, parsing, grading, reporting
- [benchmark_data.json](benchmark_data.json): question set and expected answers
- [posix-utilities.txt](posix-utilities.txt): source of truth list of POSIX utilities
- [posix-core.md](posix-core.md): Tier 1 semantic map
- [posix-tldr.json](posix-tldr.json): Tier 2 syntax lookup source

## Interpreting Results

The most important summary fields are:

- `total_billable_tokens`
- `mean_output_tokens`
- `total_estimated_excess_output_tokens`
- `posix_compliance_rate`
- `issue8_refusal_count`
- `failure_modes`
- `mean_step_count`

For Track 1 vs Track 2, compare the same model across both runs. The goal is lower output waste and better POSIX compliance, not just a different prompt shape.

## Notes

- Treat POSIX.1-2024 Issue 8 as canonical.
- `readlink`, `realpath`, and `timeout` are POSIX in Issue 8.
- Gemini CLI output may include an `MCP issues detected...` prefix; the benchmark strips it before parsing.
- Codex uses `--skip-git-repo-check` because this benchmark is often run outside a normal git-repo workflow.

## Further Reading

- [docs/benchmarks.md](docs/benchmarks.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/test-and-regression.md](docs/test-and-regression.md)
- [CLAUDE.md](CLAUDE.md)
