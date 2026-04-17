# Sayance

*Semantic AnalYsis And Natural Command Engine*

In 1986, Jon Bentley challenged Donald Knuth — the legendary author of *The Art of Computer Programming* — to demonstrate his new literate-programming system (WEB) in the "Programming Pearls" column of *Communications of the ACM*. The task was simple: read a text file and output the N most frequently occurring words along with their counts, sorted by frequency.

Knuth delivered a meticulously engineered Pascal program that ran more than ten pages and hundreds of lines long. It was a masterpiece of custom data structures, thoughtful algorithms, and interwoven documentation — exactly the kind of beautiful, over-engineered solution a brilliant mind would build from scratch.

Doug McIlroy (Unix pioneer and inventor of the pipe) reviewed it. After polite praise, he demolished the entire effort by replacing Knuth's multi-page program with a six-line POSIX shell pipeline:

```sh
tr -cs A-Za-z '\n' |
tr A-Z a-z |
sort |
uniq -c |
sort -rn |
sed ${1}q
```

McIlroy didn't just solve the problem — he showed that the right combination of tiny, battle-tested command-line tools could outperform a hand-crafted masterpiece in elegance, speed, and maintainability.

That was 1986. Today, LLMs have the same blind spot Knuth had — they reach for bespoke solutions instead of the tools that are already there.

**LLMs don't know the shell tools that already exist.** They reach for `tar` when `pax` is right there. They write Python scripts to hex-dump a file instead of calling `od`. They reject `readlink` as "not POSIX" even though it's been standard since 2024. Every wrong tool is wasted tokens, wasted time, and a fragile non-portable script you now have to maintain.

**Sayance** fixes that with a two-layer reference injection system — and proves it works across Claude, Codex, and Gemini.

## How It Works

The fix isn't more training data. LLMs already *know* what `comm`, `paste`, `tsort`, and `csplit` do — they just don't reach for them. Training data is dominated by GNU/Linux blog posts and Stack Overflow answers, so the model's prior overwhelmingly favors `tar` over `pax` even when it knows both exist ([Patil et al., "Gorilla," 2023](https://arxiv.org/abs/2305.15334) — name familiarity bias is the #1 cause of wrong tool selection in LLM function-calling benchmarks).

Sayance doesn't teach. It *activates recall*. Two layers, each doing one job:

### Layer 1: Discovery Map — "What exists"

A ~925-token semantic map of all 142 macOS-available POSIX utilities, injected into the agent's context at session start. Each utility gets a 2-5 word hook — enough to trigger recognition, not enough to bloat the window.

```
[COMPARING_MERGING]
lines unique to file A vs B, set difference -> comm (NOT diff)
merge columns from files side by side -> paste
relational join on shared field (like SQL JOIN) -> join
```

The design is research-informed, not ad hoc:

- **~925 tokens deployed, under a 2,000-token hard ceiling.** Needle-in-the-haystack studies (Anthropic, 2024; Google, 2024) show near-perfect retrieval for injected context under 2K tokens across all major models. At sub-1K, positional degradation drops below 5%.
- **8 namespaces with `[BRACKET_CAPS]` headers.** Grouped tools with categorical headers show 15-30% higher selection accuracy versus flat lists ([Qin et al., "ToolLLM," 2023](https://arxiv.org/abs/2307.16789)). The bracket format triggers structural attention modes in code-trained transformers ([Clark et al., 2019](https://arxiv.org/abs/1906.04341)).
- **"One Verb, One Tool" rule.** Verb overlap is the #1 collision vector in tool-selection benchmarks — tools sharing a primary verb see 3-5x higher confusion rates ([Patil et al., "Gorilla," 2023](https://arxiv.org/abs/2305.15334)). No two entries in the same namespace share a verb.
- **Negation with positive-first framing.** `pax: portable archive (NOT tar)` reduces wrong-tool selection by 40-60% ([Tang et al., 2024](https://arxiv.org/abs/2306.06624)). Standalone negation without an alternative is worse than nothing — the ironic process effect ([Shi et al., 2023](https://arxiv.org/abs/2302.00093)).

### Layer 2: Syntax Lookup — "How to use it correctly"

A zero-dependency CLI the LLM calls via bash. No MCP server, no schema tokens, no persistent process. The LLM's bash tool is always registered — zero additional context overhead. An MCP tool would add 79-120 tokens of schema per session for no benefit. ([docs/architecture](docs/architecture.md))

```bash
$ sayance-lookup pax
  Create portable archive: pax -w -f archive.pax directory/
  Copy directory tree: pax -rw src/ dest/
  DO NOT USE tar (not guaranteed POSIX).

$ sayance-lookup sed
  Replace all occurrences: sed 's/foo/bar/g' file > tmp && mv tmp file
  DO NOT USE -i (not POSIX). Always use redirect and mv.
```

The Discovery Map tells the agent *what exists*. Syntax Lookup tells it *how to use it correctly*. Together: ~925 tokens cached at session start, plus 50-200 tokens per on-demand lookup.

## What the Latest Benchmark Shows

Latest snapshot: 40-question corpus, `k=1`, rerun on `2026-04-15`. Models: `claude-opus-4-6`, `gpt-5.4`, and `gemini-3.1-pro-preview`.

These numbers are useful for regression tracking and product direction. They are not publication-grade statistical claims.
They also predate the provenance-hardening work in this repo, so treat them as **legacy artifacts** rather than fully self-authenticating benchmark records.

### POSIX Compliance: Unaided vs Bridge-Aided

| Provider | Unaided | Bridge-Aided | Delta |
|:---------|:--------|:-------------|:------|
| **Claude** | `███████░░░` 70% | `█████████░` 88% | **+18 pts** |
| **Codex** | `███████░░░` 69% | `██████████` 95% | **+26 pts** |
| **Gemini** | `██████░░░░` 61%* | `████████░░` 85% | **+24 pts** |

\* Gemini's unaided run had `12` provider errors, so the `61%` figure is computed over `28` visible results rather than the full `40`.

### Snapshot (40 questions, k=1)

| | Claude | Codex | Gemini |
|:---|:---:|:---:|:---:|
| **Compliance (unaided)** | 70% | 70% | 61%* |
| **Compliance (bridge-aided)** | 88% | 95% | 85% |
| **Mean output tokens (unaided)** | 314 | 1,040 | 243 |
| **Mean output tokens (bridge-aided)** | 452 | 1,385 | 92 |
| **Mean latency (unaided)** | 10.1s | 22.2s | 20.7s |
| **Mean latency (bridge-aided)** | 14.4s | 31.9s | 24.4s |
| **Non-POSIX substitutions (unaided)** | 6 | 6 | 7 |
| **Non-POSIX substitutions (bridge-aided)** | 1 | 0 | 3 |
| **Visible results** | 40/40 both | 40/40 both** | 28/40 unaided, 40/40 bridge |
| **Dominant bridge-aided style** | over_explaining | tool_heavy_detour | minimal_or_near_minimal |

\** The Codex row is a composite backfill: `39` rows from the April 15, 2026 aggregate plus targeted April 17, 2026 `T02` reruns in unaided and bridge-aided mode. It is not a fresh single-run 40-question Codex rerun.

- **All three providers improved POSIX compliance** in the bridge-aided run.
- **Gemini** showed the cleanest visible gain: higher compliance, much shorter answers, and no provider errors in bridge mode.
- **Codex** improved the most on tool selection, but remained verbose and tool-heavy.
- **Claude** improved on compliance and trap avoidance, but in this rerun it rarely invoked the explicit lookup path.
- **Raw billable tokens did not decrease** in this simulation path. Bridge mode prepends the Discovery Map and may trigger a second model turn for lookup replay, so raw bridge cost is an upper bound rather than the final efficiency story.

### What These Numbers Mean

Unaided and Bridge-Aided runs measure POSIX-target selection, verbosity, and latency on a fixed text-only benchmark. They do not, by themselves, prove end-to-end command correctness or real-world time savings.

Current benchmark artifacts use two denominator styles:
- `posix_compliance_rate` uses only report-visible rows.
- `planned_posix_compliance_rate` keeps explicit provider-error rows in the denominator.

Pre-hardening runs may only expose the visible-row denominator and may not include a provenance block or planned-result counts.

The `--execute` flag enables Command Verification, which runs extracted commands against fixtures and validates output. `30/40` questions currently have execution fixtures; `T31`-`T40` remain unverified. The working hypothesis is that Sayance's upfront cost can still be worthwhile if it reduces retry loops and wrong-tool detours downstream.

## Install the Skill

No virtualenv needed. Pure stdlib Python 3.

### Prerequisites

The installer places the `sayance-lookup` binary under `~/.local/bin`. Make sure that directory is on your `PATH` before restarting your agent, or the CLI call will fail even though the files are on disk.

```bash
# Bash (~/.bashrc) or Zsh (~/.zshrc):
export PATH="$HOME/.local/bin:$PATH"
```

After install, confirm with `command -v sayance-lookup` — it should resolve under `~/.local/bin`.

### One-line install (no clone required)

```bash
# Claude Code + Codex (stable, recommended)
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/v1.0.1/install.sh | bash

# Claude Code only
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/v1.0.1/install.sh | bash -s claude

# Codex only
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/v1.0.1/install.sh | bash -s codex

# Bleeding-edge (tracks main, not a release)
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/main/install.sh | SAYANCE_REF=main bash
```

### Codex native installer

From inside a Codex session:

```
$skill-installer install https://github.com/gitguffaw/sayance/tree/main/skill
```

### From source

```bash
git clone https://github.com/gitguffaw/sayance.git
cd sayance
make install         # both Claude + Codex
make install-claude  # Claude Code only
make install-codex   # Codex only
```

### Verify

```bash
sayance-lookup pax
sayance-lookup --list
```

After install, restart Claude Code or Codex. The skill auto-loads the semantic map into each session. The LLM calls `sayance-lookup <utility>` via bash whenever it needs exact syntax.

```bash
# Dev workflow — edit and iterate
make test                  # test from repo without installing
make test-product          # Install Testing: product-path conformance (isolated HOME)
make test-product-negative # Install Testing: failure-injection sensitivity checks
make uninstall             # remove skill and CLI
```

## Run the Benchmark

```bash
# Dry run (no API calls)
python3 run_benchmark.py --dry-run

# Validate bridge completeness (required before trusted Step-Up runs)
python3 run_benchmark.py --validate-bridge

# Run unaided (no injection) for Claude + Codex
python3 run_benchmark.py --llms claude codex

# Run bridge-aided (with injection) for Claude + Codex
python3 run_benchmark.py --llms claude codex --inject-posix
```

`--inject-posix` now fails fast if `sayance-core.md` and `sayance-tldr.json` do not fully cover the 142 macOS-available POSIX Issue 8 utilities.
The excluded utilities are listed in `docs/macos-excluded-utilities.md`.

Model selection defaults:
- Claude is pinned by default to `claude-opus-4-6`.
- Codex is pinned by default to `gpt-5.4`.
- To change pinned models, pass `--claude-model <model-id>` and/or `--codex-model <model-id>`.
- Unpinned runs are blocked by default. To bypass intentionally, use `--claude-model auto` and/or `--codex-model auto` together with `--allow-unpinned-models`.

Fresh unaided commands (provider-isolated):

```bash
# Claude unaided (pinned default: claude-opus-4-6)
python3 run_benchmark.py --llms claude --claude-model claude-opus-4-6 --results-dir results/unaided-claude-2026-04-03

# Codex unaided (pinned default: gpt-5.4)
python3 run_benchmark.py --llms codex --codex-model gpt-5.4 --results-dir results/unaided-codex-2026-04-03

# Gemini unaided (quota-safe profile)
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30 --results-dir results/unaided-gemini-2026-04-03
```

Summary validity semantics:
- Token metrics use `usage_valid_results`.
- Visibility metrics use `report_visible_results`.
- Planned-run metrics use `planned_results` and `planned_posix_compliance_rate` in provenance-hardened summaries.
- `usage_invalid_results` and `invalid_usage_reasons` explain parser/telemetry issues.
- `provider_error_results` and `dropped_results` make denominator integrity explicit in hardened summaries.
- `valid_results` remains as a backward-compatible alias of `usage_valid_results`.
- In custom `--results-dir` runs, benchmark artifacts are retained as a single latest pair (`summary-*.json` and `report-*.html`) to avoid ambiguous multi-summary directories.
- In comparison HTML, latency is shown in seconds and token context rows include input/cached/billable-minus-output values.

## Validation

This repo uses three complementary validation paths:

- **Simulation Testing:** benchmark simulation path (`run_benchmark.py` in Unaided / Bridge-Aided / Command Verification modes). Preserves historical comparability and benchmark metrics.
- **Install Testing:** shipped-product conformance for installed `SKILL.md` + `sayance-lookup`. Includes single-target install tests, drift detection, and partial-uninstall verification.
- **Repo Integrity:** structural coherence checks for source-of-truth artifacts. Validates 142-utility (macOS subset) count consistency across all four sources, JSON validity, CLI sanity, and fixture coverage.

The canonical single command for all validation:

```bash
make verify
```

This runs five stages in order: syntax check, unit tests, repo integrity, product conformance, and failure injection. All must pass before merging.

Individual targets are also available:

```bash
make test-repo               # repo structural integrity only
make test-product             # install/uninstall conformance
make test-product-negative    # failure injection sensitivity
```

GitHub Actions CI runs `make verify` on every push and pull request to `main`.

## Artifact Trust Levels

- **Provenance-hardened artifacts** include a top-level `provenance` block plus explicit `planned_results`, `provider_error_results`, and `planned_posix_compliance_rate` fields.
- **Legacy artifacts** predate that schema. They remain useful for directional history, but they are weaker for audit-grade comparison because corpus/prompt provenance and planned-denominator metrics may be missing.

## Repository Map

| File | Purpose |
|------|---------|
| `skill/SKILL.md` | **The Product** — Claude Code skill combining Discovery Map + Syntax Lookup instruction |
| `skill/sayance-lookup` | **Syntax Lookup CLI** — executable Python 3 CLI, zero deps, called via bash |
| `skill/sayance-tldr.json` | Syntax lookup database (shared by CLI and benchmark) |
| `sayance-core.md` | **Discovery Map** — semantic map of all 142 macOS-available POSIX utilities (~925 tokens) |
| `Makefile` | Build, test, and install pipeline |
| `run_benchmark.py` | Stable benchmark CLI entrypoint + compatibility facade |
| `benchmark_core/` | Internal benchmark implementation (`cli`, `runner`, `providers`, `execution`, `reporting`, `models`, `config`) |
| `benchmark_data.json` | 40 intent-based questions with expected POSIX answers |
| `macOS-posix-utilities.txt` | All 142 macOS-available POSIX Issue 8 utilities (canonical list) |

## Output Files

```
results/
  unaided/<llm>/                    per-question Unaided results
  bridge-aided/<llm>/               per-question Bridge-Aided results
  execute/<llm>/                    per-question Command Verification results
  bridge-aided-execute/<llm>/       per-question Bridge-Aided Verification results
  unaided-scheduled-5h/            scheduled Unaided series (runNN + logs)
  bridge-aided-scheduled-5h/       scheduled Bridge-Aided series (runNN + logs)
```

For custom `--results-dir` runs, only the latest `summary-*.json` and `report-*.html` are retained in that directory.

Results are gitignored and not committed.

## Notes

- POSIX.1-2024 Issue 8 is canonical: [pubs.opengroup.org](https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html)
- `readlink`, `realpath`, and `timeout` are POSIX in Issue 8. Models trained pre-2024 incorrectly reject these — that's a scoreable failure.
- For runtime quirks and provider-specific gotchas (Gemini quota, Codex git-check, CLI noise prefixes), see the "Known Issues" section in [CLAUDE.md](CLAUDE.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor guide, validation requirements, and code style.

## Further Reading

- [Architecture](docs/architecture.md) — how the two-layer system works
- [Benchmark Methodology](docs/benchmarks.md) — how we measure
- [Benchmark Evidence](docs/evidence.md) — provenance and reproducibility of published numbers
- [Test & Regression](docs/test-and-regression.md) — validation procedures

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
