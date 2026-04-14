Status: ACTIVE
Expiry condition: when all five phases are implemented and acceptance criteria pass
Outcome:

---

# feat: Close Installed-Path Install Testing Gaps

## Overview

Install Testing (product-conformance testing) validates that the installed POSIX bridge — `skill/SKILL.md` + `posix-lookup` CLI — works correctly from a clean environment. Current Install Testing tests cover file presence, CLI functionality, and 155-count in an isolated HOME. Three gaps remain:

1. **No drift enforcement** between the four canonical bridge sources (`posix-utilities.txt`, `posix-tldr.json`, `posix-core.md`, `skill/SKILL.md`)
2. **No per-target install isolation** — `install-claude` and `install-codex` are tested only via `install-all`, plus a real symlink bug on partial uninstall
3. **No live proof** that a fresh CLI session discovers the installed skill and uses the bridge

The product is the installed bridge, not a compiled binary. This plan closes the gaps for the installed-path definition.

## Problem Statement / Motivation

The existing `--validate-bridge` (`benchmark_core/runner.py:188-276`) checks `posix-utilities.txt` against `posix-core.md` and `posix-tldr.json` but never touches `skill/SKILL.md`. The installed product could drift from the repo-level bridge assets silently. Meanwhile, `test_product.sh` checks file presence and counts but not content agreement across sources. And no automated test proves the bridge actually activates in a fresh CLI session — the core claim of the project is unverified at the installed path.

## Proposed Solution

Five workstreams, ordered by dependency and determinism:

### Phase 1: Fix Symlink Bug on Partial Uninstall

**Problem discovered during analysis:** Both `install-claude` and `install-codex` (`Makefile:25,33`) `ln -sf` to the same `~/.local/bin/posix-lookup`. `install-all` runs `install-claude` then `install-codex` (`Makefile:10`), so the symlink points to the codex copy after a normal install. `uninstall-codex` (`Makefile:45`) removes `~/.codex/skills/posix/` but does not touch the symlink — leaving it dangling even though the claude copy still exists. Verified locally: after `install-all` then `uninstall-codex`, `posix-lookup pax` fails with "No such file or directory." The reverse (`uninstall-claude` after `install-all`) leaves a working CLI because the symlink already points to codex.

**Fix:** Each single-target uninstall checks whether the symlink points to its own skill dir. If so:
- If the other target's copy exists, repoint the symlink there
- Otherwise, remove the symlink

**Files:** `Makefile` (uninstall-claude, uninstall-codex targets)

### Phase 2: Shared Drift Validator

Extend `validate_posix_bridge()` in `benchmark_core/runner.py` to also check `skill/SKILL.md`:

- Extract utility names from SKILL.md using the same `\b{name}\b` word-boundary regex used for `posix-core.md` (tolerate false-positive prose matches because missing-utility is the dangerous direction)
- Add **bidirectional** enforcement: flag utilities present in any source but absent from `posix-utilities.txt` (catches accidental additions, not just omissions)
- Add SKILL.md path to `benchmark_core/config.py`
- Wire into `--validate-bridge` (existing entry point, enhanced for repo-level checks)

**Repo vs installed validation — two distinct checks:**
`--validate-bridge` reads hardcoded repo-root paths from `benchmark_core/config.py:5-9` (`SCRIPT_DIR / "posix-core.md"`, etc.). It validates the *source* files, not the *installed* copies. Calling it from `test_product.sh` against an isolated HOME would still read the repo files, missing drift in the installed product entirely.

The fix requires two layers:
1. **Repo-level** (enhanced `--validate-bridge`): add SKILL.md to the existing four-source check. Validates source consistency before install. No path changes needed — `config.py` already resolves relative to `SCRIPT_DIR`.
2. **Installed-level** (`test_product.sh`): add a shell-native content check that extracts utility names from the *installed* `SKILL.md`, `posix-tldr.json`, and `posix-lookup --list` output, then asserts all three agree on 155 names. This stays in pure shell (no Python import of benchmark_core) and validates the installed artifacts directly.

The shell check does not need to re-validate `posix-utilities.txt` or `posix-core.md` — those are repo-level source files that are not installed. The installed-level check validates that the *shipped* artifacts are internally consistent.

**Shell extraction method for SKILL.md utility names:** SKILL.md uses three patterns:
1. `*   name:` bullet entries (most utilities) — extract with `grep '^\*' | sed 's/^\*   //; s/:.*//'`
2. Comma-separated bare lines like `uucp, uustat, uux` and the SCCS line — split on `, ` and strip descriptions
3. CORE_TRIVIAL comma-separated inline list — same comma split

All three can be handled by: strip markdown headers/prose, split on commas and newlines, trim whitespace, sort. Compare the resulting sorted list against `posix-lookup --list | sort` and `python3 -c "import json; print('\n'.join(sorted(json.load(open('$INSTALLED_TLDR')))))"`. If all three produce the same 155 names, the installed artifacts are consistent.

**Files:** `benchmark_core/runner.py`, `benchmark_core/config.py` (repo-level); `scripts/test_product.sh` (installed-level)

### Phase 3: Single-Target Install Tests

Extend `scripts/test_product.sh` to test each install target independently:

1. **install-claude only:** isolated HOME, `make install-claude`, validate CLI resolves, `posix-lookup pax` works, symlink points to claude dir, uninstall leaves no dangling artifacts
2. **install-codex only:** same sequence for codex
3. **install-all:** existing test (already works)
4. **Partial uninstall:** install-all, uninstall-claude, verify symlink repoints to codex, CLI still works

Each sub-test gets its own temp HOME to avoid interaction.

**Make target decision:** Fold single-target tests into `make test-product` rather than adding a separate target. Install Testing is already the "run before merge" gate — splitting it creates a target nobody remembers to run. The added time (~15s for three extra temp HOMEs) is acceptable for a pre-merge gate.

**Files:** `scripts/test_product.sh`

### Phase 4: Live Canary Tests (Opt-In)

**Prerequisites to resolve empirically before implementation:**
- [ ] Verify Claude Code auto-discovers skills in `~/.claude/skills/` from a clean HOME with no prior config (`HOME=$(mktemp -d) make install-claude && HOME=$SAME claude -p "list your skills"`)
- [ ] Verify Codex discovers `~/.codex/skills/` similarly

**Design decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Env var gate | `POSIX_LIVE_CANARY=1` (single var) | Simpler than per-target vars; live tests are always both-or-neither in practice |
| Behavior when unset | Silent skip with message: `"Skipping live canary (POSIX_LIVE_CANARY not set)"` | Prevents CI false-passes while avoiding surprise bills |
| Subprocess timeout | 60 seconds | CLI calls typically complete in 10-30s; 60s accommodates cold cache |
| Retry policy | Single attempt, informational | Nondeterministic LLM output makes hard gates flaky; capture raw response for human review |
| Assertion method | String-presence heuristic | Assert response contains `pax` (or `od`) AND does not contain `tar` (or `xxd`) as the recommended answer. Bare substring match — simple, deterministic, occasionally wrong on comparative phrasing like "Unlike tar, use pax" (counts as pass since pax is present and tar is not the recommendation). Accept this tradeoff for a single-attempt informational check. |

**Canary prompt design constraint:** Prompts must NOT contain "POSIX", "POSIX.1-2024", standards language, or the expected utility name — this matches the repo's Taboo rule (`docs/test-and-regression.md`, `benchmark_data.json` question_rules). The canary must test whether the *bridge* causes the LLM to choose the right tool, not whether the LLM already knows the answer from training data.

**Canary prompt candidates:**

```
# Canary A (archive/extract — tests pax vs tar)
"I need to create a portable archive of a directory tree using only standard Unix utilities. What single utility should I use? Answer with just the utility name and a one-line example."

# Canary B (hex dump — tests od vs xxd)
"I need to display a file's contents in hexadecimal using only standard Unix utilities. What single utility should I use? Answer with just the utility name and a one-line example."
```

These prompts are intentionally vague enough that an LLM *without* the bridge will typically reach for `tar` or `xxd`. An LLM *with* the bridge should discover `pax` and `od` via the skill's Discovery Map.

**Assertion logic (per canary):**
1. Parse stdout from CLI subprocess
2. Check response contains expected utility name (`pax` / `od`)
3. Check response does NOT recommend the trap alternative (`tar` / `xxd`) as the answer
4. Capture: response text, exit code, wall-clock latency, model name (from CLI version output)
5. Write results as JSON to stdout (caller can redirect to `results/lane-b/`)

**Telemetry captured per canary run:** canary name, provider, model, prompt, raw response, expected/trap utility, pass/fail, latency, timestamp. Written as JSON to stdout.

**Failure triage:** When a canary fails, check the raw response for bridge-specific evidence. "POSIX.1-2024" alone is NOT reliable bridge evidence — the model may know that phrase from training data. Look for artifacts that can only come from the installed skill:
- **Response mentions `posix-lookup`, references the skill by name, or quotes syntax from `posix-tldr.json`** → bridge was discovered and used, but the model still chose the wrong utility (test-design issue — refine prompt or accept as known limitation)
- **No bridge-specific artifacts in response** → bridge was not discovered (product issue — skill auto-discovery failed in the isolated HOME, or the model ignored the skill)
- **Correct utility present but trap utility also present** → ambiguous response (likely comparative phrasing — review manually, not a blocking failure)

**New Make targets:**
- `test-product-live-claude` — installs to isolated HOME, runs both canary prompts via `claude -p`
- `test-product-live-codex` — installs to isolated HOME, runs both canary prompts via `codex exec`
- Both gated on `POSIX_LIVE_CANARY=1`

**Files:** `scripts/test_product_live.sh` (new), `Makefile` (new targets)

### Phase 5: Documentation Cleanup

Two sub-tasks:

**5a. Binary language audit** — fix files that describe posix-lookup as a compiled binary:
- `README.md` — describe shipped artifact as "executable Python 3 CLI," not "binary"
- `CLAUDE.md` — same language fix in Key Files and Architecture sections
- `skill/SKILL.md` — verify no "binary" language in Syntax Lookup instructions
- `docs/plans/prd-posix-step-up-deepened.md` — label any Go/Rust/MCP references as "future-state only"

**5b. Install Testing definition update** — this plan expands Install Testing's required gate (drift validation, single-target tests) and adds an optional live extension (canary). The docs must distinguish these clearly to avoid implying that pre-merge Install Testing now requires billable API calls.

The canonical Install Testing definition lives in:
- `AGENTS.md:31,43-45` — Install Testing commands and validation guidance
- `docs/test-and-regression.md:19-30` — Dual-Lane Validation Model section
- `CLAUDE.md` — Install Testing references in "Running the Benchmark" and "Key Files"

Updates must:
1. Add the new non-billable checks (`--validate-bridge` with SKILL.md, single-target install tests) to the required pre-merge Install Testing gate
2. Document live canary targets as an **optional extension** of Install Testing, explicitly billable and opt-in, NOT part of the pre-merge gate
3. Follow the repo's sync rule (`AGENTS.md:5`, `CLAUDE.md:7`): when semantics change in one, update both in the same change

**Files:** `README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/test-and-regression.md`, `skill/SKILL.md`, `docs/plans/prd-posix-step-up-deepened.md`

## Technical Considerations

**SKILL.md utility extraction:** The Discovery Map content in SKILL.md uses mixed formatting — bullet lists, comma-separated inline lists (`uucp, uustat, uux`), and bare-line entries. The `\b{name}\b` regex approach matches all of these but also matches utility names appearing in prose descriptions (e.g., "file" in "file: guess data type"). This is acceptable because the check is bidirectional — a false positive in SKILL.md would only trigger if `posix-utilities.txt` was missing that utility, which is the ground truth file.

**Symlink semantics:** `readlink -f` is POSIX Issue 8 but may not be available on older macOS. Use `readlink` (without `-f`) to check symlink target in the Makefile.

**Cost isolation:** Live canary calls are billable. At current pricing, two prompts per provider is ~$0.02-0.05 total. The env var gate ensures this never runs accidentally in CI or local `make test`.

## System-Wide Impact

- **Interaction graph:** Drift validator enhancement touches `benchmark_core/runner.py` which is called by both `--validate-bridge` and `--inject-posix` preflight. Changes must preserve the existing `require_full_coverage` gating so Simulation Testing validation (expected_commands check) still works independently.
- **Error propagation:** Canary subprocess failures should never propagate as test-harness crashes. Wrap all subprocess calls in timeout + try/except with explicit exit codes.
- **State lifecycle risks:** Isolated HOME tmpdirs must be cleaned up on both success and failure paths. Phase 3 creates multiple temp HOMEs per run — use a parent temp dir with per-test subdirs and a single `trap 'rm -rf "$TEMP_ROOT"' EXIT` for cleanup.
- **API surface parity:** Both providers (Claude, Codex) get identical test structure.

## Acceptance Criteria

### Drift Validator (Repo-Level)
- [ ] `python3 run_benchmark.py --validate-bridge` checks all four repo sources (posix-utilities.txt, posix-tldr.json, posix-core.md, skill/SKILL.md)
- [ ] Removing one utility from any repo source causes validation failure
- [ ] Adding an extra utility to any repo source causes validation failure (bidirectional)

### Drift Validator (Installed-Level)
- [ ] `test_product.sh` checks installed SKILL.md, installed posix-tldr.json, and `posix-lookup --list` agree on 155 utility names
- [ ] Check runs against artifacts in the isolated HOME, not repo-root files
- [ ] `test_product_negative.sh` gains a drift-injection case: after install, remove one utility from installed SKILL.md and confirm the installed-level drift check fails

### Single-Target Install
- [ ] `make install-claude` alone produces a working `posix-lookup` in isolated HOME
- [ ] `make install-codex` alone produces a working `posix-lookup` in isolated HOME
- [ ] Partial uninstall (install-all then uninstall-claude) leaves working symlink pointing to codex
- [ ] Partial uninstall (install-all then uninstall-codex) leaves working symlink pointing to claude
- [ ] Full uninstall removes all artifacts including symlink

### Live Canary
- [ ] Empirical prerequisites pass: skill auto-discovery works in clean HOME for both CLIs, and CLI auth functions from an isolated HOME (auth tokens may live outside HOME — e.g., system keychain or XDG config — so a clean HOME may not break auth, but this must be verified)
- [ ] If clean HOME breaks CLI auth or config discovery, canary script documents the required bootstrap steps and applies them before the prompt call (e.g., symlinking auth config into the temp HOME)
- [ ] `POSIX_LIVE_CANARY=1 make test-product-live-claude` passes with bridge-aware response
- [ ] `POSIX_LIVE_CANARY=1 make test-product-live-codex` passes with bridge-aware response
- [ ] Without env var, both targets skip silently with informational message
- [ ] Canary captures telemetry JSON to stdout
- [ ] 60-second timeout prevents hanging

### Documentation
- [ ] No file in the repo describes posix-lookup as a "compiled binary"
- [ ] Go/Rust/MCP references labeled "future-state only" where they appear

## Dependencies & Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Claude Code does not auto-discover skills in clean HOME | Medium | Empirical verification required before Phase 4; if false, canary must bootstrap config |
| Codex skill discovery path differs from documented | Medium | Same empirical check; fallback is explicit `--skills-dir` flag if available |
| Canary nondeterminism produces flaky results | High | Single attempt, informational-only, raw response captured for human review |
| Regex extraction from SKILL.md matches prose not utility names | Low | Bidirectional check limits impact; false positives only fire if ground truth disagrees |
| Symlink fix breaks existing install-all workflow | Low | Phase 1 is tested independently before other phases |

## Implementation Order

1. **Phase 1** (symlink fix) — no dependencies, fixes a real product bug
2. **Phase 2** (drift validator) — no dependencies, deterministic, testable immediately
3. **Phase 3** (single-target tests) — depends on Phase 1 (symlink fix must land first)
4. **Phase 4** (live canary) — depends on empirical skill-discovery verification; implement last
5. **Phase 5** (docs) — no dependencies, can run in parallel with any phase

## Outstanding Items (Explicitly Out of Scope)

- Command Verification execution validation (separate plan: `docs/plans/Plan_for_track3-execution-validation.md`)
- CLI backoff jitter, q_id sanitization, fixed-seed question shuffling (PRD hardening)
- Compiled Go/Rust standalone binary (separate future project)
- Gemini skill installation path (no skill mechanism exists for Gemini CLI)

## Test Plan

**Local non-billable gate (runs on every change):**
```bash
python3 run_benchmark.py --validate-bridge   # now checks all 4 sources
make test-product                             # now includes single-target tests
make test-product-negative                    # existing + new drift-injection case
```

**Drift regression test (manual verification during development):**
```bash
# Remove one utility from each source, confirm validator fails
sed -i '' '/^pax$/d' posix-utilities.txt && python3 run_benchmark.py --validate-bridge  # expect fail
git checkout posix-utilities.txt
```

**Live canary (opt-in, requires CLI auth):**
```bash
POSIX_LIVE_CANARY=1 make test-product-live-claude
POSIX_LIVE_CANARY=1 make test-product-live-codex
```

## Sources & References

### Internal References
- Drift validator: `benchmark_core/runner.py:188-276` (`validate_posix_bridge()`)
- Bridge config paths: `benchmark_core/config.py:5-9` (repo-root-relative, not installed paths)
- Data loaders: `benchmark_core/providers.py:89-107`
- Install targets: `Makefile:1-33`
- Positive conformance: `scripts/test_product.sh`
- Negative conformance: `scripts/test_product_negative.sh`
- Skill artifact: `skill/SKILL.md`, `skill/posix-lookup`
- Install Testing definition: `AGENTS.md:31,43-45`, `docs/test-and-regression.md:19-30`
- Sync rule: `AGENTS.md:5`, `CLAUDE.md:7`

### Related Work
- Active plan: `docs/plans/Plan_for_track3-execution-validation.md` (Command Verification, independent)
- Active plan: `docs/plans/prd-posix-step-up-deepened.md` (Step-Up PRD, independent)
- Learning: `docs/solutions/workflow/ai-doc-lifecycle-drift.md` (doc drift prevention)
- Learning: `docs/solutions/logic-errors/llms-blind-to-posix-utilities.md` (root cause context)
