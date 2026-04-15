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

**This project builds the semantic bridge that fixes that.** A two-layer reference injection system gives LLMs just enough context to discover and correctly use the 142 POSIX.1-2024 (Issue 8) utilities available on macOS — saving both time and tokens. (POSIX defines 155; 13 are excluded because Apple has never shipped them. See `docs/macos-excluded-utilities.md`.)

- **Discovery Map (`posix-core.md` / `skill/SKILL.md`):** ~925-token semantic map injected into agent context via Claude Code skill. Tells the LLM what exists.
- **Syntax Lookup (`posix-lookup` CLI):** Zero-dependency executable Python 3 CLI backed by `posix-tldr.json`, called via bash. Tells the LLM how to use it correctly. No MCP — zero schema token overhead.

The benchmark (`run_benchmark.py`) is a utility for proving the solution works — it is not the product. The product is the bridge.

Validation uses two paths:
- Simulation Testing (legacy, unchanged): benchmark simulation path for comparability.
- Install Testing (additive): installed product-path conformance for `SKILL.md` + `posix-lookup`, including single-target install tests, installed artifact drift validation, and partial-uninstall symlink correctness. Optional live canary extension (billable, opt-in) tests fresh-session bridge activation.

The canonical source of truth is **POSIX.1-2024 (Issue 8)**: https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html — which defines **155 utilities**. The bridge ships 142 (macOS-available subset). See `docs/macos-excluded-utilities.md` for the 13 exclusions and rationale.

## Running the Benchmark

Command examples below are convenience references. Canonical command/runbook details are in AGENTS.md.

```bash
# Dry run (no API calls)
python3 run_benchmark.py --dry-run

# Validate bridge completeness (core + tldr)
python3 run_benchmark.py --validate-bridge

# Install Testing: product conformance (installed skill + CLI)
make test-product
make test-product-negative

# Install Testing: optional live canary (billable, opt-in)
POSIX_LIVE_CANARY=1 make test-product-live-claude
POSIX_LIVE_CANARY=1 make test-product-live-codex

# Run specific LLMs
python3 run_benchmark.py --llms gemini
python3 run_benchmark.py --llms gemini claude codex

# Model pins for unaided runs
python3 run_benchmark.py --llms claude --claude-model claude-opus-4-6
python3 run_benchmark.py --llms codex --codex-model gpt-5.4

# Safe Gemini unaided under tight quota
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
4. `benchmark_core/execution.py` handles Command Verification fixture setup and execution validation.
5. `benchmark_core/reporting.py` writes terminal, summary JSON, and HTML reports.
6. `benchmark_core/models.py` defines dataclasses/result filters; `benchmark_core/config.py` holds path/runtime config.

Results are saved under `results/` as JSON/HTML, with mode roots at `results/unaided/` for Unaided runs, `results/bridge-aided/` for Bridge-Aided runs, `results/execute/` for Command Verification, and `results/bridge-aided-execute/` for Bridge-Aided Verification. Each invocation writes to its own run directory using `label-DYYYY-MM-DD-THH-MM-SS`, for example `claude-codex-D2026-04-10-T08-55-15`. Each run directory also includes a `run.json` manifest so experiment context is not stored only in the folder name.

**CLI invocation patterns:**
- Claude: `claude -p "prompt" --output-format json`
- Gemini: `gemini -p "prompt" -o json`
- Codex: `codex exec --json --skip-git-repo-check "prompt"`

## Key Files

- `skill/SKILL.md` — **The product** — Claude Code skill (Discovery Map + Syntax Lookup instruction)
- `skill/posix-lookup` — **Syntax Lookup CLI** — executable Python 3 CLI, zero deps, called via bash
- `skill/posix-tldr.json` — Syntax lookup database (shared by CLI and benchmark)
- `posix-core.md` — Discovery Map (also embedded in SKILL.md)
- `Makefile` — `make test`, `make test-product`, `make test-product-negative`, `make test-product-live-claude`, `make test-product-live-codex`, `make install`, `make uninstall`
- `macOS-posix-utilities.txt` — All 142 macOS-available POSIX Issue 8 utilities (source of truth)
- `benchmark_data.json` — Structured questions with expected answers and required concepts
- `run_benchmark.py` — Stable facade + CLI entrypoint
- `benchmark_core/` — Internal benchmark implementation modules
- `fixtures/` — Per-question test fixtures for Command Verification
- `fixtures/manifest.json` — Maps question IDs to fixture specs and validation types
- `docs/design-rationale/` — Research backing design decisions (semantic compression, bridge architecture)

## Known Issues

- [OBSERVED 2026-04-02] **Gemini MCP prefix**: Gemini CLI prepends "MCP issues detected..." to output. Must strip before any JSON parsing. `strip_cli_noise()` handles this plus ~10 other known noise prefixes.
- [OBSERVED 2026-04-02] **Gemini quota planning**: Gemini is hardcoded to 1 worker with a 30-second minimum delay between calls (`GEMINI_MIN_DELAY_SECONDS`). Assume no more than 50 calls per day unless the active account limits clearly show otherwise. A 40-question Unaided run still fits, but only with 10 calls of headroom. Bridge-Aided runs may exceed the daily quota because the bridge simulation can trigger a second Gemini call for a question.
- [OBSERVED 2026-04-02] **Codex git-check behavior**: Use `--skip-git-repo-check` when running outside a git repository. In this repo, use it only if you need to bypass local checks.
- [OBSERVED 2026-04-02] **POSIX Issue 8 vs 7**: `readlink`, `realpath`, and `timeout` are now POSIX (Issue 8, 2024). LLMs trained on older data will incorrectly call these "not POSIX." `c99` is now `c17`. The batch `q*` utilities and `fort77` were removed.
- [OBSERVED 2026-04-03] **Bridge completeness gate**: Incomplete semantic bridge coverage can corrupt Bridge-Aided benchmark runs. `run_benchmark.py --inject-posix` now performs strict preflight validation and exits if `posix-core.md` or `posix-tldr.json` drift from 142-utility (macOS subset) coverage.
- [OBSERVED 2026-04-03] **GitHub merge-gate plan limit (this repo)**: `gitguffaw/posix` has Actions enabled, but branch protection required status checks for this private repository return HTTP 403 ("Upgrade to GitHub Pro or make this repository public"). Install Testing CI can run for visibility; enforce Install Testing locally until plan/visibility changes.

## Important Context

- The primary metrics are **tokens and time**, not accuracy. Accuracy is secondary. Cost tracking has been removed from the codebase.
- Token counts differ across providers (different tokenizers). Use native tokens for comparison, tiktoken o200k_base for normalization.
- Token validity is explicit: prefer `usage_valid_results`, `report_visible_results`, `usage_invalid_results`, and `invalid_usage_reasons`. `valid_results` remains a compatibility alias of `usage_valid_results`.
- Custom `--results-dir` runs retain only the latest `summary-*.json` and `report-*.html` to prevent ambiguous artifact sets.
- **Measurement modes**: Unaided and Bridge-Aided runs measure token efficiency and response time only — they do not execute commands. The `--execute` flag enables Command Verification, which runs extracted commands against fixtures and validates output. 30/40 questions have execution fixtures; T31-T40 are unverified.
- Cache state (cold vs warm) creates 10x token difference on Anthropic. Track per result.
- All providers run with 1 concurrent worker to avoid rate limiting. Gemini enforces a 30-second minimum delay between calls.
- LLM-as-judge is susceptible to prompt injection. Grading uses base64-encoded responses to mitigate. Never use the same model as both test subject and judge.
- `benchmark_data.json` (questions and expected answers), `posix-tldr.json`, and `fixtures/` are frozen datasets for cross-model comparison. Do not modify them to fix benchmark results unless we are creating new base data because.
