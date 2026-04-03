Status: ACTIVE
Expiry condition: when Track 3 benchmark run completes and all implementation steps are marked done
Outcome:

---

## Status Summary

**Last updated:** 2026-04-03  
**Track 1 (Raw Capability):** Complete — all three providers, 30 questions, k=1  
**Track 2 (Step-Up):** Complete — all three providers, 30 questions, k=1  
**Track 3 (Execution Validation):** Not started — see `docs/plans/Plan_for_track3-execution-validation.md`

### What We Know

Track 1 and Track 2 are done. Compliance improved in Track 2 across all three providers. The Step-Up architecture works for the compliance goal.

| Provider | T1 Compliance | T2 Compliance | T1 Mean Output Tokens | T2 Mean Output Tokens |
|----------|--------------|--------------|----------------------|----------------------|
| Claude | 63.3% | 76.7% | 228 | 374 |
| Codex | 58.6% | 86.7% | 930 | 1,289 |
| Gemini | 65.4% | 86.7% | 215 | 105 |

### What We Still Don't Know

Track 1 and Track 2 only prove compliance rates in a controlled environment. Neither track involved actual command execution. The real-world token cost story — what happens when a wrong answer triggers retries, debugging, and workaround scripts — is Track 3's job. The working hypothesis: Track 2's total real-world cost is substantially lower than Track 1's, even accounting for injection overhead.

### Known Accounting Issues

- The double-invocation tool simulation in `run_benchmark.py` double-counts input tokens in merged totals. Use `total_simulation_adjusted_billable_tokens` (not `total_billable_tokens`) when comparing tracks.
- Codex token accounting only captures the last JSONL `turn.completed` event. Multi-step runs (mean 8.1–9.5 steps) may undercount total usage by 3-10x. Codex cost figures should be treated as lower bounds.

### Data Integrity Incident (2026-04-03)

- Historical Gemini/Codex/Opus Step-Up runs are considered compromised where semantic bridge coverage was incomplete.
- Root cause: incomplete Tier 2 (`posix-tldr.json`) coverage and missing bridge preflight enforcement.
- Mitigation shipped:
  - `posix-tldr.json` expanded to full 155-utility coverage (matching `posix-utilities.txt`).
  - `run_benchmark.py` now has strict preflight validation (`--validate-bridge`).
  - `--inject-posix` now fails fast if `posix-core.md` or `posix-tldr.json` drift from 155-utility coverage.
- Operational consequence: affected historical runs must be treated as invalid for comparison and rerun under the new gate.

---

# Product Requirements Document (PRD): POSIX "Step-Up" Architecture

## 1. Problem Statement
LLMs lack working knowledge of the 155 native POSIX Issue 8 utilities. When asked to perform CLI tasks, they fail to realize native tools exist, hallucinate non-POSIX GNU flags, and write complex Python/Bash scripts as workarounds. This results in compute waste and fragile, non-portable code. We cannot inject full man pages into the prompt (context tax), nor can we rely on the LLM to proactively look up commands it doesn't know exist.

### Research Insights

**Root Cause Evidence (from `docs/solutions/logic-errors/llms-blind-to-posix-utilities.md`):**
LLM training data is dominated by GNU/Linux usage, Stack Overflow, and blog posts that default to non-POSIX tools. POSIX-only utilities like `pax`, `od`, `cksum`, `uuencode`, `comm`, `tsort`, and `pathchk` have minimal representation in training corpora. Additionally, POSIX Issue 8 (2024) added `readlink`, `realpath`, and `timeout` — but LLMs trained on pre-2024 data still reject these as "not POSIX."

**POSIX.1-2024 Confirmation (from IEEE spec rationale):**
The POSIX.1-2024 Issue 8 spec rationale confirms the addition of `readlink`, `realpath`, and `timeout`. Also notable: `c99` is now `c17`, and the batch `q*` utilities and `fort77` were removed. LLMs trained before June 2024 will have stale knowledge about all of these.

**Cross-Model Severity:** Research on tool selection from large catalogs (Patil et al., "Gorilla", 2023) shows that name familiarity bias causes LLMs to prefer tools they've seen more in training data. The `tar` over `pax` substitution is a textbook example — `tar` appears 1000x more in training corpora. This bias cannot be overcome by model training alone; it requires runtime intervention.

## 2. Solution: The 2-Tier "Step-Up" Architecture
A progressive, low-token reference mechanism that mirrors human developer workflows.

*   **Tier 1 (`posix-core.md`):** A heavily condensed semantic map of the 155 utilities injected into the agent's context as a Factory Skill. It provides a 2-4 word semantic hook (e.g., `pax: portable archive (NOT tar)`) so the agent knows the tool exists. Max size: ~1,200 tokens.
*   **Tier 2 (Syntax Lookup CLI):** A CLI binary (`posix-lookup`) backed by a local database (`posix-tldr.json`). Agents are instructed to run `posix-lookup <utility>` via bash *before* executing a Tier 1 utility in the shell. Chosen over MCP to avoid schema token overhead and maximize cross-platform reach (any agent with bash access).

*Future consideration:* If Tier 2 coverage proves insufficient after Track 3 validation, a Tier 3 spec search tool can be added. This is deferred until data motivates it.

### Research Insights

**Architecture Validation:**
- The 2-tier progressive disclosure pattern is architecturally sound for this constraint space. The clean separation (Tier 1 = discovery, Tier 2 = syntax) prevents scope creep and keeps token budgets predictable.
- CLI-via-bash was chosen over MCP after a structured engineering debate. MCP adds ~79-120 tokens of schema overhead per session; bash is always registered. The CLI also works across Claude Code, Cursor, Codex, Gemini CLI — any agent with shell access.

**Tier 2 Coverage Status (updated 2026-04-03):**
Tier 2 now covers all 155 POSIX Issue 8 utilities listed in `posix-utilities.txt`, eliminating the discovery-to-lookup cliff. Coverage is enforced by a benchmark preflight gate before Step-Up runs.

**CLI Distribution (Chosen over MCP):**
The `posix-lookup` CLI is a zero-dependency Python 3 script that returns syntax info from `posix-tldr.json`. It is invoked via bash, which is always available in the LLM's tool schema.

```bash
$ posix-lookup sed
  Replace all occurrences: sed 's/foo/bar/g' file > tmp && mv tmp file
  DO NOT USE -i (not POSIX). Always use redirect and mv.

$ posix-lookup --json od
{"od": ["Hex dump: od -A x -t x1z file", "DO NOT USE xxd or hexdump."]}
```

For pipeline lookups, the LLM calls `posix-lookup` once per utility. This is simpler than batch arrays and leverages the LLM's strongest tool-calling behavior (bash).

**Why not MCP?** MCP was evaluated in a structured 3-agent engineering debate. The conclusion: MCP adds ~79-120 tokens of schema overhead, requires a persistent server process, and limits reach to MCP-compatible clients. The CLI approach costs zero schema tokens and works anywhere with a terminal. MCP remains a future option for structured multi-client access.

**Future MCP path:** The CLI lookup function is isolated and trivially wrappable in a FastMCP server (~50 lines) if multi-client structured tool access (Cursor, Cline, Zed) becomes a priority.

## 3. Design Principles for Tier 1 Semantic Hooks

Each entry in `posix-core.md` follows these rules:

- **2-5 words per hook.** Below 3 words, LLMs confuse similar tools. Above 5, the 1,200-token budget is exceeded.
- **Disambiguate by mechanism, not outcome.** `sed` = regex stream, `tr` = 1-to-1 character swap, `awk` = column/field logic.
- **One Verb, One Tool.** Within each namespace, no two tools share a primary verb.
- **Trap inversion for known hallucination traps.** Format: `tool: positive description (NOT wrong_tool)`. Limit to 8-12 negation markers total.
- **Affirmative corrections for Issue 8 additions.** Use `(IS POSIX)` instead of negation for utilities LLMs incorrectly reject.
- **8 categorical namespaces with `[BRACKET_CAPS]` headers.** Bracketed ALL-CAPS headers trigger "structured data scanning" mode.
- **Order by query frequency.** `[TEXT_DATA_PROC]` first (most common queries), `[DEV_BUILD]` and `[IPC_COMM]` last.

## 4. Edge Cases & Risks

### The Rebellious Agent (Hallucination)
The LLM reads `pax` in Tier 1 but ignores Tier 2 and confidently guesses the syntax (e.g., `pax -z`).

*Mitigation:* The skill instruction ("Run `posix-lookup <utility>` to get exact syntax before executing") leverages the LLM's strongest tool-calling behavior — bash invocation. The CLI returns error messages that correct misconceptions inline. The benchmark tracks tool usage patterns to detect non-compliance.

*Observed in Track 2:* Codex showed `tool_heavy_detour` as its dominant pattern (25/30 questions) — meaning it called the tool correctly but narrated every step verbosely. This is not a compliance failure.

### The Context Flood
The `posix-tldr.json` database is wrapped behind the `posix-lookup` CLI. The agent calls it one utility at a time via bash. It never has raw file access to the JSON.

### Complex Pipelines
Tasks requiring three tools (e.g., `sort | uniq | comm`) trigger latency spikes if looked up sequentially. The tool accepts arrays and returns a keyed JSON object.

### Security Notes
- **Tool-call command extraction:** Validate extracted command against the keys of `posix-tldr.json` before building the follow-up prompt.
- **Question ID path traversal:** Add `re.match(r'^[A-Za-z0-9_-]+$', q_id)` validation in `result_path()`.

## 5. Implementation Steps

### Step 1: Deliver Tier 1 Skill
**Status: ✅ Complete**

`posix-core.md` exists, covers all 155 POSIX Issue 8 utilities, grouped by 8 categorical namespaces.

### Step 2: Expand Tier 2 Coverage
**Status: ✅ Complete — 155 utilities covered (2026-04-03)**

*   **Task:** Expand `posix-tldr.json` to full POSIX Issue 8 coverage and enforce bridge integrity.
*   **Delivered:** `posix-tldr.json` now contains 155 entries and is validated against `posix-utilities.txt`.
*   **Acceptance Criteria:**
    *   [x] Every `expected_commands` value in `benchmark_data.json` has a corresponding entry in `posix-tldr.json`.
    *   [x] Tier 2 coverage expanded from ~30 entries to 155 entries.
    *   [x] Preflight validator added (`python3 run_benchmark.py --validate-bridge`).
    *   [x] `--inject-posix` fails fast when bridge coverage is incomplete.

### Step 3: Harden the Test Harness
**Status: Partial**

`--inject-posix` is wired. Tool simulation works via text pattern matching. Open items:

*   [ ] Rate-limit backoff with exponential jitter for all CLI invocations.
*   [x] Bridge preflight now validates `posix-tldr.json` key integrity and expected-command coverage before Step-Up runs.
*   [ ] Question ID sanitized with `re.match(r'^[A-Za-z0-9_-]+$', q_id)`.
*   [ ] Question order randomized per run with a fixed seed for reproducibility.

### Step 4: Run Baseline (Track 1)
**Status: ✅ Complete (k=1)**

All three providers completed. Results:

| Provider | Valid Results | Mean Output Tokens | POSIX Compliance | Mean Steps |
|----------|--------------|-------------------|-----------------|------------|
| Claude | 30/30 | 228 | 63.3% | 1.0 |
| Codex | 29/30 | 930 | 58.6% | 8.1 |
| Gemini | 26/30 | 215 | 65.4% | 1.0 |

Codex had 1 timeout (T02). Gemini had 4 timeouts (T04, T21, T26, T30).

*Note: k=1 is sufficient to validate the architecture. k=5 would be needed for publication-quality statistical claims.*

### Step 5: Run Step-Up (Track 2) and Compare
**Status: ✅ Complete (k=1)**

All three providers completed with 30/30 valid results.

| Provider | Mean Output Tokens | POSIX Compliance | Mean Steps |
|----------|--------------------|-----------------|------------|
| Claude | 374 | 76.7% | 2.0 |
| Codex | 1,289 | 86.7% | 9.5 |
| Gemini | 105 | 86.7% | 2.8 |

**Pre-registered hypothesis evaluation:**

| Hypothesis | Result |
|-----------|--------|
| H1: Track 2 reduces mean output tokens by ≥20% | Mixed — Gemini ✅ (−51%), Claude ✗ (+64%), Codex ✗ (+39%). Output tokens increased for Claude and Codex due to tool narration overhead, not wrong answers. |
| H2: Track 2 reduces `non_posix_substitution` by ≥50% | Codex ✅ (9→1, −89%), Gemini ✅ (7→3, −57%), Claude ✗ (6→7, slightly worse) |
| H3: Track 2 achieves ≥80% POSIX compliance | Codex ✅ (86.7%), Gemini ✅ (86.7%), Claude ✗ (76.7%, close) |
| H4: Track 2 eliminates Issue 8 refusals | ✅ All three had 0 in both tracks |

**Key observation:** Output token counts are not the right efficiency metric for Codex in Track 2. Codex uses the tool correctly (86.7% compliance) but narrates every step. The real efficiency question — does correct-first-time reduce total real-world cost versus retry loops — is Track 3's job.

### Step 6: Ship Skill Distribution (CLI + Claude Code Skill)
**Status: ✅ Complete**

Built and deployed the production delivery mechanism for the POSIX Bridge:

*   **Architecture decision (QNT-53):** CLI skill via bash chosen over MCP after structured multi-agent debate. Zero schema tokens, universal agent compatibility.
*   **`posix-lookup` CLI (QNT-54):** Python 3 binary, zero deps, pure stdlib. Modes: lookup, --list, --json.
*   **`skill/SKILL.md` (QNT-55):** Claude Code skill combining Tier 1 semantic map + Tier 2 CLI instruction. Auto-loads into sessions (~925 tokens, cached).
*   **`Makefile` (QNT-56):** `make test`, `make install`, `make uninstall` pipeline.
*   **`skill/` directory (QNT-57):** Source of truth for distributable artifacts in the repo.

### Step 7: Track 3 — Execution Validation
**Status: Not started**

See `docs/plans/Plan_for_track3-execution-validation.md` for full spec.

The hypothesis to prove: a Track 1 model that reaches for the wrong tool will retry, debug, and potentially write its own script, burning orders of magnitude more tokens. A Track 2 model that reaches the correct command on the first attempt incurs none of that retry cost. Track 3 measures this delta by actually running the suggested commands.

## References

- POSIX.1-2024 (Issue 8): https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html
- POSIX Issue 8 rationale: https://pubs.opengroup.org/onlinepubs/9799919799/xrat/V4_xcu_chap01.html
- Liu et al., "Lost in the Middle" (2023) — context position effects
- Patil et al., "Gorilla" (2023) — tool selection from large catalogs
- Qin et al., "ToolLLM" (2023) — hierarchical tool organization
- Jiang et al., "LLMLingua" (2023) — prompt compression
- MCP spec (2025): tool annotations, instructions field, structuredContent
- Artificial Analysis methodology: https://artificialanalysis.ai/methodology
