# Repository Guidelines

## Governance and Sync

- CLAUDE.md is canonical for benchmark behavior, runtime semantics, provider CLI quirks, and result interpretation.
- AGENTS.md is canonical for process, code style, validation commands, PR hygiene, and operational workflow.
- `benchmark_data.json` (`meta.question_rules`) is canonical for question-rule semantics; `posix-utilities.txt` is canonical for POSIX utility scope.
- Sync rule: when a topic changes in one file that affects the other, update both in the same change.
- Conflict rule: behavior/runtime conflicts resolve to CLAUDE.md; process/style conflicts resolve to AGENTS.md.

## Project Structure & Module Organization

This repository is a small, stdlib-only Python benchmark. `run_benchmark.py` is the main entrypoint and contains the CLI, provider adapters, grading flow, and JSON parsing. Benchmark inputs live in `benchmark_data.json`, and the POSIX utility source of truth lives in `posix-utilities.txt`. Research notes and planning docs are under `docs/brainstorms/`, `docs/plans/`, and `docs/solutions/`. Generated output is written to `results/`, which is ignored by Git.

## Build, Test, and Development Commands

Use Python directly; there is no virtualenv or build step.

- `python3 run_benchmark.py --dry-run` checks question selection and CLI wiring without making API calls.
- `python3 run_benchmark.py --llms gemini claude` runs selected providers only.
- `python3 run_benchmark.py --questions Q1 Q2 --k 3` repeats specific questions for comparison.
- `python3 run_benchmark.py --judge claude` enables grading when you want token and accuracy data.
- `python3 -m py_compile run_benchmark.py` is the fastest syntax sanity check before committing.

## Coding Style & Naming Conventions

Follow the existing Python style in `run_benchmark.py`: 4-space indentation, explicit type hints, dataclasses for captured results, and small helper functions for provider-specific parsing. Keep dependencies in the standard library unless there is a strong reason not to. When invoking external CLIs, pass argument lists to `subprocess.run()` instead of shell strings. Use snake_case for functions and variables, and uppercase names for constants and enum members.

## Testing Guidelines

There is no dedicated `tests/` directory yet, so use dry runs and focused benchmark runs as the primary validation path. For logic changes, run `python3 -m py_compile run_benchmark.py` and at least one targeted command such as `python3 run_benchmark.py --dry-run --questions Q1`. If you change parsing, grading, or result serialization, note a sample JSON path from `results/`, but do not commit generated output.

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

**Before the next planning session:**
- [ ] Pull `docs/plans/`. Any plan whose expiry condition has been met must be archived before a new plan is created.

## Repository-Specific Notes

Treat POSIX.1-2024 Issue 8 as canonical when editing questions or expected answers. Check `CLAUDE.md` before changing CLI behavior, token accounting, or provider quirks such as Gemini noise stripping and Codex's `--skip-git-repo-check` flag.

For benchmark behavior and runtime assumptions, follow CLAUDE.md.
