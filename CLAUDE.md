# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Governance and Sync

- CLAUDE.md is canonical for benchmark behavior, runtime assumptions, provider quirks, prompt semantics, and result interpretation.
- AGENTS.md is canonical for process, code style, validation commands, PR hygiene, and engineering workflow.
- `benchmark_data.json` (`meta.question_rules`) is canonical for question-rule semantics.
- POSIX.1-2024 is canonical for utility semantics and POSIX standard scope.
- Sync rule: when a topic changes in one file that affects the other, update both in the same change.
- Conflict rule: behavior/runtime conflicts resolve to CLAUDE.md; process/style conflicts resolve to AGENTS.md.
- For coding/process constraints, runbook details, and commit behavior, follow AGENTS.md.

## Why This Project Exists

LLMs are blind to most POSIX utilities. They reach for `tar` instead of `pax`, write Python scripts instead of calling `od`, and reject `readlink` as "not POSIX." Every wrong tool wastes tokens, wastes time, and produces fragile non-portable code.

**This project builds the semantic bridge that fixes that.** A two-tier reference injection system gives LLMs just enough context to discover and correctly use the 155 utilities defined in POSIX.1-2024 (Issue 8) — saving both time and tokens.

- **Tier 1 (`posix-core.md` / `skill/SKILL.md`):** ~925-token semantic map injected into agent context via Claude Code skill. Tells the LLM what exists.
- **Tier 2 (`posix-lookup` CLI):** Zero-dependency Python 3 binary backed by `posix-tldr.json`, called via bash. Tells the LLM how to use it correctly. No MCP — zero schema token overhead.

The benchmark (`run_benchmark.py`) is a utility for proving the solution works — it is not the product. The product is the bridge.

Validation uses two lanes:
- Lane A (legacy, unchanged): benchmark simulation path for comparability.
- Lane B (additive): installed product-path conformance for `SKILL.md` + `posix-lookup`.

The canonical source of truth is **POSIX.1-2024 (Issue 8)**: https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html — which defines **155 utilities**.

## Running the Benchmark

Command examples below are convenience references. Canonical command/runbook details are in AGENTS.md.

```bash
# Dry run (no API calls)
python3 run_benchmark.py --dry-run

# Validate bridge completeness (core + tldr)
python3 run_benchmark.py --validate-bridge

# Lane B product conformance (installed skill + CLI)
make test-product
make test-product-negative

# Run specific LLMs
python3 run_benchmark.py --llms gemini
python3 run_benchmark.py --llms gemini claude codex

# Model pins for baseline runs
python3 run_benchmark.py --llms claude --claude-model claude-opus-4-6
python3 run_benchmark.py --llms codex --codex-model gpt-5.4

# Safe Gemini baseline under tight quota
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30

# Run specific questions
python3 run_benchmark.py --questions T01 T02 T16

# Change the grading judge
python3 run_benchmark.py --judge claude
```

No virtual environment or dependencies needed — pure stdlib Python 3.

## Architecture

`run_benchmark.py` is the stable CLI entrypoint and compatibility facade. Internal implementation is split into `benchmark_core/` modules:
1. `benchmark_core/cli.py` parses CLI args and routes modes.
2. `benchmark_core/runner.py` orchestrates question/provider execution and grading.
3. `benchmark_core/providers.py` handles CLI invocation, token parsing, and response analysis.
4. `benchmark_core/execution.py` handles Track 3 fixture setup and command execution validation.
5. `benchmark_core/reporting.py` writes terminal, summary JSON, and HTML reports.
6. `benchmark_core/models.py` defines dataclasses/result filters; `benchmark_core/config.py` holds path/runtime config.

Results are saved under `results/` as JSON/HTML, with mode roots at `results/baseline/` for Track 1, `results/stepup/` for Track 2, `results/execute/` for Track 3, and `results/stepup-execute/` for Track 3b. Each invocation writes to its own run directory using `label-DYYYY-MM-DD-THH-MM-SS`, for example `claude-codex-D2026-04-10-T08-55-15`. Each run directory also includes a `run.json` manifest so experiment context is not stored only in the folder name.

**CLI invocation patterns:**
- Claude: `claude -p "prompt" --output-format json`
- Gemini: `gemini -p "prompt" -o json`
- Codex: `codex exec --json --skip-git-repo-check "prompt"`

## Key Files

- `skill/SKILL.md` — **The product** — Claude Code skill (Tier 1 map + Tier 2 CLI instruction)
- `skill/posix-lookup` — **Tier 2 CLI** — Python 3 binary, zero deps, called via bash
- `posix-tldr.json` — Syntax lookup database (shared by CLI and benchmark)
- `posix-core.md` — Tier 1 semantic map (also embedded in SKILL.md)
- `Makefile` — `make test`, `make test-product`, `make test-product-negative`, `make install`, `make uninstall`
- `posix-utilities.txt` — All 155 POSIX Issue 8 utilities (source of truth)
- `benchmark_data.json` — Structured questions with expected answers and required concepts
- `run_benchmark.py` — Stable facade + CLI entrypoint
- `benchmark_core/` — Internal benchmark implementation modules
- `fixtures/` — Per-question test fixtures for Track 3 execution validation
- `fixtures/manifest.json` — Maps question IDs to fixture specs and validation types
- `docs/plans/` — Implementation plans (the deepened plan is the current roadmap)

## Known Issues

- [OBSERVED 2026-04-02] **Gemini MCP prefix**: Gemini CLI prepends "MCP issues detected..." to output. Must strip before any JSON parsing. `strip_cli_noise()` handles this plus ~10 other known noise prefixes.
- [OBSERVED 2026-04-02] **Gemini quota planning**: For this repo, assume Gemini is safe at one benchmark call every 30 seconds and no more than 50 calls per day unless the active account limits clearly show otherwise. A 40-question Track 1 baseline still fits, but only with 10 calls of headroom. Track 2 may exceed the daily quota because the Step-Up simulation can trigger a second Gemini call for a question.
- [OBSERVED 2026-04-02] **Codex git-check behavior**: Use `--skip-git-repo-check` when running outside a git repository. In this repo, use it only if you need to bypass local checks.
- [OBSERVED 2026-04-02] **POSIX Issue 8 vs 7**: `readlink`, `realpath`, and `timeout` are now POSIX (Issue 8, 2024). LLMs trained on older data will incorrectly call these "not POSIX." `c99` is now `c17`. The batch `q*` utilities and `fort77` were removed.
- [OBSERVED 2026-04-03] **Bridge completeness gate**: Incomplete semantic bridge coverage can corrupt Step-Up benchmark runs. `run_benchmark.py --inject-posix` now performs strict preflight validation and exits if `posix-core.md` or `posix-tldr.json` drift from 155-utility coverage.
- [OBSERVED 2026-04-03] **GitHub merge-gate plan limit (this repo)**: `gitguffaw/posix` has Actions enabled, but branch protection required status checks for this private repository return HTTP 403 ("Upgrade to GitHub Pro or make this repository public"). Lane B CI can run for visibility; enforce Lane B locally until plan/visibility changes.

## Important Context

- The primary metric is **token cost**, not accuracy. Accuracy is secondary.
- Token counts differ across providers (different tokenizers). Use native tokens for cost, tiktoken o200k_base for cross-model comparison.
- Token validity is explicit: prefer `usage_valid_results`, `report_visible_results`, `usage_invalid_results`, and `invalid_usage_reasons`. `valid_results` remains a compatibility alias of `usage_valid_results`.
- Custom `--results-dir` runs retain only the latest `summary-*.json` and `report-*.html` to prevent ambiguous artifact sets.
- Comparison HTML uses seconds-based latency display and intentionally omits `Total Cost (USD)`; use token-context rows (`Total Input Tokens`, `Total Cached Tokens`, `Billable - Output Tokens`) when interpreting billable totals.
- Cache state (cold vs warm) creates 10x cost difference on Anthropic. Track per result.
- LLM-as-judge is susceptible to prompt injection. Grading uses base64-encoded responses to mitigate. Never use the same model as both test subject and judge.
- `benchmark_data.json` (questions and expected answers), `posix-tldr.json`, and `fixtures/` are frozen datasets for cross-model comparison. Do not modify them to fix benchmark results unless we are creating new base data because.
