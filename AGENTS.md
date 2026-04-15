# Repository Guidelines

## Governance and Sync

- CLAUDE.md is canonical for benchmark behavior, runtime semantics, provider CLI quirks, and result interpretation.
- AGENTS.md is canonical for process, code style, validation commands, PR hygiene, and operational workflow.
- `benchmark_data.json` (`meta.question_rules`) is canonical for question-rule semantics; `posix-utilities.txt` is canonical for POSIX utility scope.
- Sync rule: when a topic changes in one file that affects the other, update both in the same change.
- Conflict rule: behavior/runtime conflicts resolve to CLAUDE.md; process/style conflicts resolve to AGENTS.md.

## Project Structure & Module Organization

This repository is a small, stdlib-only Python benchmark. `run_benchmark.py` is the stable CLI entrypoint and compatibility facade. Internal implementation lives under `benchmark_core/` (`cli`, `runner`, `providers`, `execution`, `reporting`, `models`, `config`). Benchmark inputs live in `benchmark_data.json`, and the POSIX utility source of truth lives in `posix-utilities.txt`. Design rationale and research are under `docs/design-rationale/`. Generated output is written under `results/`, with mode roots at `results/unaided/`, `results/bridge-aided/`, `results/execute/`, and `results/bridge-aided-execute/`. Each benchmark invocation writes to its own run directory using `label-DYYYY-MM-DD-THH-MM-SS`, for example `claude-codex-D2026-04-10-T08-55-15`. Each run directory also includes a `run.json` manifest so context is not encoded only in the folder name. Generated output is ignored by Git.

## Build, Test, and Development Commands

Use Python directly; there is no virtualenv or build step.

- `python3 run_benchmark.py --dry-run` checks question selection and CLI wiring without making API calls.
- `python3 run_benchmark.py --validate-bridge` verifies `posix-core.md` + `posix-tldr.json` cover all 155 utilities and exits.
- `python3 run_benchmark.py --llms gemini claude` runs selected providers only.
- `python3 run_benchmark.py --llms claude --claude-model claude-opus-4-6` runs Claude with the pinned baseline model (also the default).
- `python3 run_benchmark.py --llms codex --codex-model gpt-5.4` runs Codex with the pinned baseline model (also the default).
- `python3 run_benchmark.py --questions T01 T02 --k 3` repeats specific questions for comparison.
- `python3 run_benchmark.py --judge claude` enables grading when you want token and accuracy data.
- `python3 run_benchmark.py --no-grade` skips LLM-as-judge grading (token-only mode).
- `python3 run_benchmark.py --inject-posix` runs the Bridge-Aided simulation: injects `posix-core.md` into the prompt and simulates Syntax Lookup tool calls. It now fails fast if bridge coverage is incomplete.
- `python3 run_benchmark.py --execute` runs extracted commands against fixtures for Command Verification.
- `python3 run_benchmark.py --inject-posix --execute` combines Bridge-Aided + Command Verification (Bridge-Aided Verification).
- In custom `--results-dir` runs, only the latest `summary-*.json` and `report-*.html` are retained in that directory.
- `make test-product` runs Install Testing product-path conformance checks in an isolated `HOME` (includes single-target install tests, installed-level drift validation, and partial-uninstall symlink verification).
- `make test-product-negative` runs Install Testing failure-injection checks (missing file, broken symlink, malformed JSON, installed SKILL.md drift).
- `make test-product-live-claude` / `make test-product-live-codex` run opt-in live canary tests (requires `POSIX_LIVE_CANARY=1`; billable API calls, NOT part of the pre-merge gate).
- `python3 -m py_compile run_benchmark.py benchmark_core/*.py` is the fastest syntax sanity check before committing.
- `make test-repo` runs repo structural integrity checks (source artifact presence, JSON validity, 155-utility coherence across all four sources, CLI executable sanity, installer references, fixture directory coverage).
- `make verify` runs all verification checks in sequence: syntax, unit tests, repo integrity, product conformance, failure injection. This is the canonical single command for pre-commit and CI validation.

## Coding Style & Naming Conventions

Follow the existing Python style across `benchmark_core/` and `run_benchmark.py`: 4-space indentation, explicit type hints, dataclasses for captured results, and small helper functions for provider-specific parsing. Keep dependencies in the standard library unless there is a strong reason not to. When invoking external CLIs, pass argument lists to `subprocess.run()` instead of shell strings. Use snake_case for functions and variables, and uppercase names for constants and enum members.

## Testing Guidelines

Unit tests live in `tests/` (token accounting, reporting integrity) and run via `python3 -m unittest`. Repo integrity checks live in `scripts/verify_repo.py` and run via `make test-repo`. The unified command is `make verify`.

Use a three-path validation approach:
- Simulation Testing (legacy): dry runs and focused benchmark runs.
- Install Testing (additive): installed product-path checks via `make test-product` and `make test-product-negative`. Includes single-target install isolation, installed artifact drift validation, and partial-uninstall symlink correctness. Optional live canary extension (`make test-product-live-claude` / `make test-product-live-codex`) is billable and informational — not part of the pre-merge gate.
- Repo Integrity: structural coherence checks via `make test-repo`.

For any change, run `make verify` before committing. For logic changes, also run at least one targeted Simulation Testing command such as `python3 run_benchmark.py --dry-run --questions T01`. If you change parsing, grading, or result serialization, note a sample JSON path from the relevant timestamped run directory under `results/`, but do not commit generated output.

## Commit & Pull Request Guidelines

Current history uses Conventional Commit prefixes such as `feat:`. Keep commit subjects short, imperative, and scoped to one benchmark change. There is no PR template, so include what changed, which commands you ran, whether API-backed runs were executed, and any scoring assumptions affected. If a change alters prompts, grading, or POSIX coverage, include a before/after example in the PR description.

## Post-Run Documentation Checklist

Run after every benchmark run that produces results. Doc drift is the primary risk in this project — it compounds silently.

**Immediate (before closing the terminal):**
- [ ] Did any result contradict a Known Issues entry in CLAUDE.md? Update it with observed behavior and `[OBSERVED date]`.
- [ ] Did any result confirm or refute a speculative claim in any reference doc? Replace with observed fact.
- [ ] Did a planning doc's expiry condition get met? Fill in Outcome, set Status to SUPERSEDED, move to `docs/archive/`.

**In the same commit as the results:**
- [ ] Does CLAUDE.md Known Issues still match reality? Each bullet must have an `[OBSERVED date]` tag.
- [ ] Are there one-shot scripts (`patch_*`, `migrate_*`, `fix_once_*`) in the repo root that were run to produce this result? Delete them now.

## Repository-Specific Notes

Treat POSIX.1-2024 Issue 8 as canonical when editing questions or expected answers. Check `CLAUDE.md` before changing CLI behavior, token accounting, or provider quirks such as Gemini noise stripping and Codex's `--skip-git-repo-check` flag.

For benchmark behavior and runtime assumptions, follow CLAUDE.md.
