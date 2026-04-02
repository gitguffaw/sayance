Status: ACTIVE
Expiry condition: when Track 3 benchmark run completes and all implementation steps are marked done
Outcome:

---

## Status Summary

**Last updated:** 2026-04-02  
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

*   **Tier 1 (`posix-core.md`):** A heavily condensed semantic map of the 155 utilities injected into the agent's context as a Factory Skill. It provides a 2-4 word semantic hook (e.g., `pax: portable archive (NOT tar)`) so the agent knows the tool exists. Max size: ~800 tokens.
*   **Tier 2 (Syntax Lookup Tool):** An agent-native tool (`get_posix_syntax`) backed by a local database (`posix-tldr.json`). Agents are instructed to call this tool *before* executing a Tier 1 utility in the shell. Accepts batch arrays for pipeline lookups.

*Future consideration:* If Tier 2 coverage proves insufficient after Track 3 validation, a Tier 3 spec search tool can be added. This is deferred until data motivates it.

### Research Insights

**Architecture Validation:**
- The 2-tier progressive disclosure pattern is architecturally sound for this constraint space. The clean separation (Tier 1 = discovery, Tier 2 = syntax) prevents scope creep and keeps token budgets predictable.
- Two tools is the sweet spot for MCP tool economics. Every tool schema costs tokens every turn. More than 2 tools adds context-window tax; fewer loses the discovery/syntax separation.

**Tier 2 Coverage Gap:**
Tier 2 currently covers only 29 of ~85 non-trivial utilities. This creates a "discovery-to-lookup cliff" — the agent finds a utility in Tier 1 but gets no syntax from Tier 2. Expanding Tier 2 to cover all utilities tested in `benchmark_data.json` is the minimum; covering all non-trivial utilities is the goal. At 155 utilities x ~50 tokens each, the full Tier 2 database is ~7,750 tokens — a lookup problem, not a search problem.

**Tool Schema Best Practices:**
The `get_posix_syntax` tool schema should be designed for maximum LLM tool-calling reliability:

```json
{
  "name": "get_posix_syntax",
  "description": "Look up exact POSIX.1-2024 (Issue 8) syntax for one or more utilities. Returns pure-POSIX synopsis, flags, and common traps. NO GNU/BSD extensions. Call this BEFORE using any utility from the POSIX semantic map.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "utilities": {
        "type": "array",
        "items": { "type": "string" },
        "minItems": 1,
        "maxItems": 10,
        "description": "POSIX utility names. For pipelines, include all tools (e.g. ['sort', 'uniq', 'comm'])."
      }
    },
    "required": ["utilities"]
  },
  "annotations": {
    "readOnlyHint": true,
    "idempotentHint": true,
    "openWorldHint": false
  }
}
```

**Tool Result Format:**
Return compact JSON keyed by utility name:
```json
{
  "sed": {
    "synopsis": "sed [-n] script [file...]",
    "posix_flags": ["-n", "-e"],
    "traps": ["NO -i (GNU)", "NO -r (GNU)"],
    "example": "sed 's/old/new/g' input > output"
  }
}
```
For errors, return the POSIX alternative directly: `"'xxd' is NOT POSIX. For hex dump, use: od -A x -t x1z"`.

**Cross-Provider Forced Tool Use:**
All three major providers support forcing specific tool calls:
- Claude: `tool_choice: {"type": "tool", "name": "get_posix_syntax"}`
- OpenAI: `tool_choice: {"type": "function", "function": {"name": "..."}}`
- Gemini: `toolConfig.functionCallingConfig.mode: "ANY"` + `allowedFunctionNames`

## 3. Design Principles for Tier 1 Semantic Hooks

Each entry in `posix-core.md` follows these rules:

- **2-5 words per hook.** Below 3 words, LLMs confuse similar tools. Above 5, the 800-token budget is exceeded.
- **Disambiguate by mechanism, not outcome.** `sed` = regex stream, `tr` = 1-to-1 character swap, `awk` = column/field logic.
- **One Verb, One Tool.** Within each namespace, no two tools share a primary verb.
- **Trap inversion for known hallucination traps.** Format: `tool: positive description (NOT wrong_tool)`. Limit to 8-12 negation markers total.
- **Affirmative corrections for Issue 8 additions.** Use `(IS POSIX)` instead of negation for utilities LLMs incorrectly reject.
- **8 categorical namespaces with `[BRACKET_CAPS]` headers.** Bracketed ALL-CAPS headers trigger "structured data scanning" mode.
- **Order by query frequency.** `[TEXT_DATA_PROC]` first (most common queries), `[DEV_BUILD]` and `[IPC_COMM]` last.

## 4. Edge Cases & Risks

### The Rebellious Agent (Hallucination)
The LLM reads `pax` in Tier 1 but ignores Tier 2 and confidently guesses the syntax (e.g., `pax -z`).

*Mitigation:* MCP `instructions` field provides always-on baseline enforcement. Rich error results from Tier 2 correct misconceptions inline. The benchmark tracks `tool_calls_by_type` to detect non-compliance.

*Observed in Track 2:* Codex showed `tool_heavy_detour` as its dominant pattern (25/30 questions) — meaning it called the tool correctly but narrated every step verbosely. This is not a compliance failure.

### The Context Flood
The `posix-tldr.json` database is wrapped behind the `get_posix_syntax` tool interface with a hard array cap of 10 utilities per call. The agent never has raw file access.

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
**Status: Partial — 29 utilities covered**

*   **Task:** Expand `posix-tldr.json` to cover all utilities tested in `benchmark_data.json` and add graceful fallback for missing utilities.
*   **Gap:** Verify every `expected_commands` value in `benchmark_data.json` has a corresponding entry in `posix-tldr.json`.
*   **Acceptance Criteria:**
    *   [ ] Every `expected_commands` value in `benchmark_data.json` has a corresponding entry in `posix-tldr.json`.
    *   [ ] Tool returns a structured "not yet covered" response for utilities in Tier 1 but missing from Tier 2.
    *   [ ] Array input validated: min 1, max 10 utility names per call.

### Step 3: Harden the Test Harness
**Status: Partial**

`--inject-posix` is wired. Tool simulation works via text pattern matching. Open items:

*   [ ] Rate-limit backoff with exponential jitter for all CLI invocations.
*   [ ] Tool-call command extraction validates against `posix-tldr.json` keys.
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

### Step 6: Track 3 — Execution Validation
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
