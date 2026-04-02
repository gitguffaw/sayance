# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Governance and Sync

- CLAUDE.md is canonical for benchmark behavior, runtime assumptions, provider quirks, prompt semantics, and result interpretation.
- AGENTS.md is canonical for process, code style, validation commands, PR hygiene, and engineering workflow.
- `benchmark_data.json` (`meta.question_rules`) is canonical for question-rule semantics.
- POSIX.1-2024 Issue 8 is canonical for utility semantics and POSIX standard scope.
- Sync rule: when a topic changes in one file that affects the other, update both in the same change.
- Conflict rule: behavior/runtime conflicts resolve to CLAUDE.md; process/style conflicts resolve to AGENTS.md.
- For coding/process constraints, runbook details, and commit behavior, follow AGENTS.md.

## Project Purpose

**posix** is a benchmarking and measurement tool that quantifies how many tokens LLMs burn when reasoning about POSIX shell commands. The goal is to determine whether a hyper-efficient POSIX command reference is worth building.

The canonical source of truth is **POSIX.1-2024 (Issue 8)**: https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html — which defines **155 utilities**.

## Running the Benchmark

Command examples below are convenience references. Canonical command/runbook details are in AGENTS.md.

```bash
# Dry run (no API calls)
python3 run_benchmark.py --dry-run

# Run specific LLMs
python3 run_benchmark.py --llms gemini
python3 run_benchmark.py --llms gemini claude codex

# Safe Gemini baseline under tight quota
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30

# Run specific questions
python3 run_benchmark.py --questions Q1 Q2 Q16

# Change the grading judge
python3 run_benchmark.py --judge claude
```

No virtual environment or dependencies needed — pure stdlib Python 3.

## Architecture

Single-file CLI tool (`run_benchmark.py`) that:
1. Calls LLM CLIs via `subprocess.run()` (list form, no shell injection)
2. Parses JSON output from each CLI for token usage data
3. Uses LLM-as-judge for accuracy grading (secondary metric)
4. Saves results to `results/` as JSON

**CLI invocation patterns:**
- Claude: `claude -p "prompt" --output-format json`
- Gemini: `gemini -p "prompt" -o json`
- Codex: `codex exec --json --skip-git-repo-check "prompt"`

## Key Files

- `posix-utilities.txt` — All 155 POSIX Issue 8 utilities (source of truth)
- `benchmark_data.json` — Structured questions with expected answers and required concepts
- `run_benchmark.py` — Benchmark runner (being rebuilt for token measurement)
- `docs/plans/` — Implementation plans (the deepened plan is the current roadmap)
- `docs/brainstorms/` — Design exploration documents

## Known Issues

- **Gemini MCP prefix**: Gemini CLI prepends "MCP issues detected..." to output. Must strip before any JSON parsing.
- **Gemini quota planning**: For this repo, assume Gemini is safe at one benchmark call every 30 seconds and no more than 50 calls per day unless the active account limits clearly show otherwise. A 30-question Track 1 baseline fits. Track 2 may exceed the daily quota because the Step-Up simulation can trigger a second Gemini call for a question.
- **Codex git-check behavior**: Use `--skip-git-repo-check` when running outside a git repository. In this repo, use it only if you need to bypass local checks.
- **POSIX Issue 8 vs 7**: `readlink`, `realpath`, and `timeout` are now POSIX (Issue 8, 2024). LLMs trained on older data will incorrectly call these "not POSIX." `c99` is now `c17`. The batch `q*` utilities and `fort77` were removed.

## Important Context

- The primary metric is **token cost**, not accuracy. Accuracy is secondary.
- Token counts differ across providers (different tokenizers). Use native tokens for cost, tiktoken o200k_base for cross-model comparison.
- Cache state (cold vs warm) creates 10x cost difference on Anthropic. Track per result.
- LLM-as-judge is susceptible to prompt injection. Never use the same model as both test subject and judge.
