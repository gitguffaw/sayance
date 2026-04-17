# Changelog

All notable changes to Sayance are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/gitguffaw/sayance/releases/tag/v1.0.0
