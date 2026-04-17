# Changelog

All notable changes to Sayance are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] — 2026-04-17

### Fixed
- `scripts/test_product_live.sh` — canary assertion helper failures now surface
  as infrastructure failures instead of false-green semantic misses.
- `README.md`, `CONTRIBUTING.md` — source install and contributor quick-start
  examples now enter `sayance/` instead of the removed `posix/` checkout path.
- Unit test execution now uses discovery (`python3 -m unittest discover -s tests -t .`)
  instead of the drift-prone manual `test_all.py` aggregator.
- Codex benchmark invocation now closes inherited stdin and uses benchmark-mode
  prompt framing that preserves Bridge-Aided `TOOL_CALL` behavior, resolving the
  documented `T02` stall path.

### Changed
- Stable install one-liners and the default `install.sh` `SAYANCE_REF` now point
  at `v1.0.2`.

## [1.0.1] — 2026-04-17

### Removed
- `docs/design-rationale/` — nine files of pre-release internal research that
  contradicted the shipped product (referred to the CLI as `posix-ref`, cited
  155 utilities with ~48 bridge candidates instead of the shipped 142, quoted
  ~800/1,050-token plans instead of the deployed ~925, and listed features
  as "not yet built" that have since shipped). Deleting rather than rewriting
  avoids documentation drift.

### Fixed
- `docs/architecture.md` — corrected the Discovery Map size claim from
  "~800 tokens" to the actual ~925 tokens deployed.
- `CLAUDE.md`, `AGENTS.md`, `README.md` — removed references to the deleted
  `docs/design-rationale/` tree.

### Changed
- Stable install one-liner and `install.sh` default `SAYANCE_REF` now point at
  `v1.0.1`.

## [1.0.0] — 2026-04-17

First public release.

### Added
- Two-layer POSIX Issue 8 bridge for LLMs covering 142 macOS-available utilities:
  - Discovery Map (`skill/SKILL.md`, `sayance-core.md`) — ~925-token semantic map
    injected as a Claude Code / Codex skill.
  - Syntax Lookup CLI (`skill/sayance-lookup`) — zero-dependency Python 3
    executable backed by `sayance-tldr.json`.
- `--version` flag on both `sayance-lookup` and `run_benchmark.py`.
- `VERSION` file at the repo root and shipped alongside the skill as the single
  source of truth for the product version.
- Benchmark harness (`run_benchmark.py`, `benchmark_core/`) for proving the
  bridge works across Claude, Codex, and Gemini, including Unaided,
  Bridge-Aided, and Command Verification modes.
- Install paths: `make install`, `install.sh` one-liner, and per-agent
  installers for Claude Code (`~/.claude/skills/sayance`) and Codex CLI
  (`~/.codex/skills/sayance`). `sayance-lookup` is symlinked into
  `~/.local/bin`.
- Install Testing stages in `make verify`: repo integrity, installed-artifact
  drift detection, partial-uninstall symlink correctness, and failure
  injection.
- Optional live-canary tests (`SAYANCE_LIVE_CANARY=1 make test-product-live-*`)
  that validate fresh-session bridge activation against real providers.

[1.0.2]: https://github.com/gitguffaw/sayance/releases/tag/v1.0.2
[1.0.1]: https://github.com/gitguffaw/sayance/releases/tag/v1.0.1
[1.0.0]: https://github.com/gitguffaw/sayance/releases/tag/v1.0.0
