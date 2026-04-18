# Changelog

All notable changes to Sayance are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — 2026-04-17

### Changed
- Repaired the bridge contract from `get_posix_syntax` simulation wiring to the
  shipped `sayance-lookup` CLI contract. Supersedes the `TOOL_CALL` framing that
  v1.0.2 patched.
- Added drift-detection coverage for `sayance-lookup` and lookup payload
  consistency in repository verification.
- Added utility aliases to the shipped `sayance-lookup` CLI path.
- Enriched the hot-path TLDR layer for faster POSIX command recall.
- Reframed README and benchmark docs to emphasize POSIX compliance and
  tool-selection accuracy.
- Discovery Map text-parity check now anchors at `### [CORE_TRIVIAL]` in both
  `sayance-core.md` and `skill/SKILL.md`, ignoring the SKILL.md wrapper header
  and trailing blank line.
- Dead-tool reference scan tightened to active product/runner code only;
  legitimate historical mentions in README/CHANGELOG/architecture docs no
  longer trip the gate.

### Benchmark Rerun (Wave-3, 2026-04-17, real `sayance-lookup` contract)

First benchmark run after the contract repair. 40 questions, k=1, cold cache
start. `claude-opus-4-6` and `gpt-5.4` only — Gemini skipped due to daily
quota constraints.

| Provider | Mode | Compliance | Billable Tokens | Mean Output | Mean Latency | Mean Steps |
|---|---|---:|---:|---:|---:|---:|
| Claude | Unaided      | 65.0% | 1,361,516 |   203 |  8.0s | 1.00 |
| Claude | Bridge-Aided | **82.5%** | 4,129,207 |   514 | 18.0s | 1.05 |
| Codex  | Unaided      | 66.7% |   961,677 | 1,035 | 23.6s | 7.74 |
| Codex  | Bridge-Aided | **92.5%** |   737,520 | 2,140 | 43.3s | 17.0 |

Compliance flips (Unaided → Bridge-Aided):
- Claude: +9 fixed, −2 regressed (T25, T29) → net **+7** compliant
- Codex:  +11 fixed, **0 regressions** → net **+11** compliant

Inefficiency-mode shifts:
- `workaround_instead_of_native_utility` collapsed for both: Claude 9→1, Codex 7→1.
- Codex `non_posix_substitution` 6→2; Claude flat (5→6).
- `over_explaining` rose for both (Claude 14→29, Codex 24→27) — bridge-aided answers grow verbose.
- Codex `tool_heavy_detour` 2→10 — bridge engages multiple shell steps per question.

Notable telemetry:
- Actual `sayance-lookup` invocations across 80 aided runs: **2 total** (1 per
  provider). Most compliance gains come from Discovery Map injection alone, not
  from on-demand lookups.
- `tool_simulation_integrity_violation_count`: 0 in both providers.
- Claude `total_billable_tokens` rose +203% — the gross figure counts
  `cache_read_input_tokens` at full rate; the actual new tokens added per
  prompt are ~10–13K (one cache-creation hit per call).
- Codex billable tokens **fell 23%** (962K → 738K) despite compliance rising
  by 26pp.

Artifacts (gitignored, reproducible):
- Unaided summary: `results/unaided/wave3-unaided-D2026-04-17-T17-11-11/summary-wave3-unaided-D2026-04-17-T17-11-11.json`
- Bridge-Aided summary: `results/bridge-aided/wave3-aided-D2026-04-17-T17-29-07/summary-wave3-aided-D2026-04-17-T17-29-07.json`

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
