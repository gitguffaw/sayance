# posix

**LLMs don't know the shell tools that already exist.** They reach for `tar` when `pax` is right there. They write Python scripts to hex-dump a file instead of calling `od`. They reject `readlink` as "not POSIX" even though it's been standard since 2024. Every wrong tool is wasted tokens, wasted time, and a fragile non-portable script you now have to maintain.

This project fixes that with a two-tier reference injection system — and proves it works across Claude, Codex, and Gemini.

## The Problem

POSIX.1-2024 (Issue 8) defines **155 shell utilities**. LLMs know maybe 30 of them well. The rest — `pax`, `od`, `cksum`, `uuencode`, `comm`, `tsort`, `pathchk` — are invisible. Training data is dominated by GNU/Linux blog posts and Stack Overflow answers that default to non-POSIX tools.

The result: you ask for a portable archive command and get `tar`. You ask for a hex dump and get `xxd`. You ask for a file checksum and get `md5sum`. None of these are POSIX. All of them cost you tokens explaining the wrong thing.

| You ask for | LLM suggests | POSIX answer |
|-------------|-------------|--------------|
| Portable archive | `tar` | `pax` |
| Hex dump | `xxd`, `hexdump` | `od` |
| File checksum | `md5sum`, `sha256sum` | `cksum` |
| Edit file in place | `sed -i` | `sed 's/…/' f > tmp && mv tmp f` |
| Recursive grep | `grep -r` | `find … -exec grep` |
| Resolve symlink | "not POSIX" | `readlink` (Issue 8) |

## The Solution

A two-tier progressive reference system that gives the LLM just enough context to reach for the right tool:

### Tier 1 — Discovery (`posix-core.md`)

A ~750-token semantic map of all 155 POSIX utilities (budget: 1,200 tokens), injected into the agent's context. Each utility gets a 2–5 word hook — enough to know it exists and when to reach for it.

```
[TEXT_DATA_PROC]
sed: regex stream editor (NO -i)
tr: 1-to-1 char translate/squeeze
awk: column/field logic + arithmetic
comm: side-by-side sorted-file diff (NOT diff)
```

The agent scans this and thinks: "oh, `comm` exists — I should look it up instead of writing a Python script."

### Tier 2 — Syntax Lookup (`posix-lookup` CLI)

A CLI tool backed by `posix-tldr.json` that returns POSIX-correct syntax, flags, and common traps. The LLM calls it via bash — no MCP server, no schema tokens, no persistent process.

```bash
$ posix-lookup pax
  Create portable archive: pax -w -f archive.pax directory/
  Copy directory tree: pax -rw src/ dest/
  DO NOT USE tar (not guaranteed POSIX).

$ posix-lookup sed
  Replace all occurrences: sed 's/foo/bar/g' file > tmp && mv tmp file
  DO NOT USE -i (not POSIX). Always use redirect and mv.
```

Tier 1 tells the agent what exists. Tier 2 tells it how to use it correctly. Together, they cost ~925 tokens of context (cached after first turn) plus ~50-200 tokens per on-demand lookup — and they work.

## The Proof

We tested this across three providers, 30 real shell tasks, with and without the Step-Up injection.

### POSIX Compliance: Before and After

| Provider | Without Step-Up | With Step-Up | Delta |
|:---------|:----------------|:-------------|:------|
| **Claude** | `██████░░░░` 63.3% | `████████░░` 76.7% | **+13.4 pts** |
| **Codex** | `██████░░░░` 58.6% | `█████████░` 86.7% | **+28.1 pts** |
| **Gemini** | `███████░░░` 65.4% | `█████████░` 86.7% | **+21.3 pts** |

### Full Results (30 questions, k=1)

| | Claude | Codex | Gemini |
|:---|:---:|:---:|:---:|
| **Compliance (before)** | 63.3% | 58.6% | 65.4% |
| **Compliance (after)** | 76.7% | 86.7% | 86.7% |
| **Output tokens (before)** | 228 | 930 | 215 |
| **Output tokens (after)** | 374 | 1,289 | 105 |
| **Non-POSIX substitutions (before)** | 6 | 9 | 7 |
| **Non-POSIX substitutions (after)** | 7 | 1 | 3 |
| **Dominant response style (after)** | over_explaining | tool_heavy_detour | minimal_or_near_minimal |

**Gemini** got both more correct *and* more concise — output tokens dropped 51% while compliance rose 21 points. 24 of 30 answers were classified `minimal_or_near_minimal` — the best outcome.

**Codex** jumped 28 points in compliance. Non-POSIX substitutions dropped from 9 to 1. Token count rose because it narrates tool usage verbosely (`tool_heavy_detour`), not because it gave worse answers.

**Claude** improved 13 points. Non-POSIX substitutions slightly increased (6 to 7) — the smallest gain, but compliance still rose due to fewer workarounds.

### What the Benchmark Doesn't Prove (Yet)

Tracks 1 and 2 measure compliance in a controlled text-analysis environment. No commands are actually executed. The real cost story — what happens when a wrong first answer triggers retries, debugging, and workaround scripts — is **Track 3's job**. The hypothesis: the Step-Up's small upfront cost prevents expensive downstream failure loops.

## Install the Skill

No virtualenv needed. Pure stdlib Python 3.

```bash
# Install the Claude Code skill + CLI
make install

# Verify it works
posix-lookup pax
posix-lookup --list
```

After install, restart Claude Code. The skill auto-loads the semantic map into every session. The LLM calls `posix-lookup <utility>` via bash whenever it needs exact syntax.

```bash
# Dev workflow — edit and iterate
make test       # test from repo without installing
make install    # deploy to ~/.claude/skills/posix/
make uninstall  # remove skill and CLI
```

## Run the Benchmark

```bash
# Dry run (no API calls)
python3 run_benchmark.py --dry-run

# Validate bridge completeness (required before trusted Step-Up runs)
python3 run_benchmark.py --validate-bridge

# Run baseline (no injection)
python3 run_benchmark.py --llms claude codex gemini

# Run with Step-Up injection
python3 run_benchmark.py --llms claude codex gemini --inject-posix
```

`--inject-posix` now fails fast if `posix-core.md` or `posix-tldr.json` do not fully cover the 155 POSIX Issue 8 utilities.

For Gemini, add `--max-workers 1 --delay 30` if you're on a tight API quota.

## Repository Map

| File | Purpose |
|------|---------|
| `skill/SKILL.md` | **The Product** — Claude Code skill combining Tier 1 map + Tier 2 CLI instruction |
| `skill/posix-lookup` | **Tier 2 CLI** — Python 3 binary, zero deps, called via bash |
| `posix-tldr.json` | Syntax lookup database (shared by CLI and benchmark) |
| `posix-core.md` | **Tier 1** — semantic map of all 155 POSIX utilities (~925 tokens) |
| `Makefile` | Build, test, and install pipeline |
| `run_benchmark.py` | Benchmark runner — provider adapters, grading, reporting |
| `benchmark_data.json` | 30 intent-based questions with expected POSIX answers |
| `posix-utilities.txt` | All 155 POSIX Issue 8 utilities (canonical list) |

## Output Files

```
results/
  by-provider/<llm>/current/    per-question Track 1 results
  by-provider/<llm>/stepup/     per-question Track 2 results
  by-run/track1-<provider>/     aggregate summary + HTML report
  by-run/track2-<provider>/     aggregate summary + HTML report
  by-run/final-comparison/      three-way comparison report
```

Results are gitignored and not committed.

## Notes

- POSIX.1-2024 Issue 8 is canonical: [pubs.opengroup.org](https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html)
- `readlink`, `realpath`, and `timeout` are POSIX in Issue 8. Models trained pre-2024 incorrectly reject these — that's a scoreable failure.
- Gemini is safe at one call every 30 seconds, max 50 calls/day on most accounts. Track 2 may exceed the daily limit since the Step-Up simulation can trigger a second call per question.
- Codex uses `--skip-git-repo-check` for benchmark execution context.

## Further Reading

- [Architecture](docs/architecture.md) — how the two-tier system works
- [Benchmark Methodology](docs/benchmarks.md) — how we measure
- [Test & Regression](docs/test-and-regression.md) — validation procedures
