# Contributing to Sayance

Thanks for your interest. Sayance is a small, focused two-layer reference injection system that helps LLMs discover and correctly use the 142 macOS-available POSIX.1-2024 utilities. Contributions that improve coverage, fix incorrect syntax entries, or strengthen the benchmark are welcome.

## Quick Start

```bash
git clone https://github.com/gitguffaw/sayance.git
cd sayance
make verify        # runs all validation checks
sayance-lookup pax   # confirm the CLI works
```

No virtualenv or external dependencies needed — pure stdlib Python 3.

## Before You Change Anything

Run `make verify`. It chains five stages in fast-to-slow order:

1. **Syntax check** — `python3 -m py_compile` on all Python files
2. **Unit tests** — `python3 -m unittest`
3. **Repo integrity** — source artifact presence, JSON validity, 142-utility (macOS subset) consistency across all four sources
4. **Product conformance** — install/uninstall in an isolated HOME, CLI behavior, drift detection
5. **Failure injection** — intentionally broken artifacts are detected correctly

All five must pass before proposing any change.

## What You Can Contribute

**Syntax entries (`sayance-tldr.json`):** Fix incorrect flags, add missing traps, improve examples. Every entry must reflect POSIX.1-2024 (Issue 8) — not GNU extensions, not BSD-specific behavior.

**Discovery Map (`sayance-core.md`, `skill/SKILL.md`):** Improve the 2-5 word semantic hooks that help LLMs find the right utility. Both files must stay in sync and cover all 142 macOS-available utilities.

**Benchmark questions (`benchmark_data.json`):** New questions must follow the Taboo rules defined in `benchmark_data.json` under `meta.question_rules`. The question text must never contain the expected utility name, the word "POSIX", or standards-specific language.

**Bug fixes and tooling:** Standard pull request process. Include what you changed, which commands you ran, and whether any API-backed tests were executed.

## What Not to Change Without Discussion

- The 142-utility macOS scope (see `docs/macos-excluded-utilities.md` for the 13 excluded from POSIX.1-2024's 155)
- Frozen benchmark datasets (`benchmark_data.json`, `fixtures/`, `sayance-tldr.json`) unless creating a new baseline
- The two-layer architecture (Discovery Map + Syntax Lookup)

Open an issue first if your change touches any of these.

## Submitting a Pull Request

1. Fork and branch from `main`.
2. Make your changes.
3. Run `make verify` — all stages must pass.
4. For question changes, also run `python3 run_benchmark.py --dry-run` to verify Taboo compliance.
5. Open a PR with:
   - What changed and why
   - Which validation commands you ran
   - Whether API-backed or live tests were executed (and if so, which models)

Do not commit `results/` directories, API keys, or cost data.

## Release Process

Sayance has a single public version axis: the product version, tracked in the
repo-root `VERSION` file. It is mirrored into `skill/VERSION` so
`sayance-lookup --version` works after install.

Internal fields (`benchmark_data.json.meta.version`, `PROMPT_TEMPLATE_VERSION`
in `benchmark_core/config.py`, and the `version` field in summary JSON) are
not user-facing and move on their own cadence — do not bump them to match the
product version.

To cut a release:

1. Bump `VERSION` and `skill/VERSION` to the new SemVer value.
2. Update the `install.sh` default `SAYANCE_REF` to `v<VERSION>`.
3. Update README one-liners to the new `v<VERSION>` (for example:
   `grep -n "raw.githubusercontent.com" README.md`).
4. Update `skill/SKILL.md` frontmatter `version:` to the new `VERSION`.
5. Add a new entry to `CHANGELOG.md` (Keep-a-Changelog format) dated today.
6. Run `make verify` — all stages must pass.
7. After merge, run the release one-liner from a scratch `HOME` and verify:
   `curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/v<VERSION>/install.sh | SAYANCE_REF=v<VERSION> bash`  
   then confirm `sayance-lookup --version` reports `v<VERSION>`.
8. Open a PR, get CI green, merge.
9. Tag the merge commit with an annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`.
10. Push the tag: `git push origin vX.Y.Z`.
11. Create a GitHub Release from the tag with the CHANGELOG excerpt as the body.

## Code Style

- Python: 4-space indentation, type hints, snake_case, stdlib only
- Shell: `set -euo pipefail`, quote variables, portable POSIX where possible
- Follow existing patterns in `benchmark_core/` and `scripts/`

## Reporting Issues

Use the issue templates. Bug reports need reproduction steps and environment details. Feature requests need a concrete use case.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
