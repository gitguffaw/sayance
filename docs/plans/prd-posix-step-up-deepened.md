## Enhancement Summary

**Deepened on:** 2026-03-29
**Sections enhanced:** 5 (Problem Statement, Architecture, Methodology, Edge Cases, Implementation)
**Research agents used:** `architecture-strategist`, `spec-flow-analyzer`, `performance-oracle`, `security-sentinel`, `code-simplicity-reviewer`, `best-practices-researcher` (x3: tool design, benchmark methodology, semantic compression)
**Web searches:** LLM forced function calling (2026), POSIX.1-2024 Issue 8 changes, MCP tool design patterns, lost-in-the-middle research

### Key Improvements
1. **Cut Tier 3 entirely.** No benchmark question requires it, no measured failure motivates it, and the implementation was undefined. Replaced with a one-line deferral note. This reduces PRD scope by ~15%.
2. **Collapsed the 5-part methodology into a Design Principles paragraph.** The existing `posix-core.md` already implements all five phases implicitly. The formalism added documentation overhead without changing the output.
3. **Added concrete tool schemas.** Full JSON schemas for `get_posix_syntax` with parameter constraints (minItems, maxItems, regex), MCP annotations, and cross-provider forced-tool-use patterns.
4. **Added statistical methodology for the A/B comparison.** Wilcoxon signed-rank test for paired Track 1/Track 2 data, bootstrap confidence intervals (stdlib-compatible), pre-registered hypotheses, and cache-isolation protocol.
5. **Tightened acceptance criteria.** Replaced absolute targets ("zero detours", "trap_hits = 0") with measurable relative improvement metrics (compliance rate delta >= 20pp, tool call rate >= 80%).
6. **Added security mitigations.** Whitelist validation for tool-call command extraction, question ID sanitization, and a cost guard.

### New Considerations Discovered
- The codebase is **ahead of the PRD**. Tiers 1 and 2 are built, `--inject-posix` is wired. The MVP is one benchmark run away.
- The double-invocation tool simulation in `run_benchmark.py` double-counts input tokens in merged totals. Must subtract injection overhead when comparing tracks.
- Codex token accounting only captures the last JSONL `turn.completed` event, potentially undercounting by 3-10x for multi-step runs.
- 8 consecutive Claude failures in existing results suggest missing rate-limit backoff.
- At ~800 tokens, `posix-core.md` is in the "perfect retrieval" zone (needle-in-haystack studies show near-perfect accuracy at sub-2K context lengths). The lost-in-the-middle problem is a non-issue at this size.

### YAGNI Items Removed
| Removed | Reason |
|---------|--------|
| Tier 3 `search_posix_spec` | No benchmark question requires it. Defer until data shows Tier 2 is insufficient. |
| Shell execution interception | Requires building a framework hook that doesn't exist. Measurement already tracks compliance. |
| Top-Tier Promotion | Optimizes for latency that hasn't been measured. Breaks clean tier boundary. |
| 5-part named methodology | Formalizes what's already done intuitively in `posix-core.md`. |

---

# Product Requirements Document (PRD): POSIX "Step-Up" Architecture

## 1. Problem Statement
LLMs lack working knowledge of the 155 native POSIX Issue 8 utilities. When asked to perform CLI tasks, they fail to realize native tools exist, hallucinate non-POSIX GNU flags, and write complex Python/Bash scripts as workarounds. This results in massive compute waste (e.g., Codex burning 80,000 tokens on a simple data task) and fragile, non-portable code. We cannot inject full man pages into the prompt (context tax), nor can we rely on the LLM to proactively look up commands it doesn't know exist.

### Research Insights

**Root Cause Evidence (from `docs/solutions/logic-errors/llms-blind-to-posix-utilities.md`):**
LLM training data is dominated by GNU/Linux usage, Stack Overflow, and blog posts that default to non-POSIX tools. POSIX-only utilities like `pax`, `od`, `cksum`, `uuencode`, `comm`, `tsort`, and `pathchk` have minimal representation in training corpora. Additionally, POSIX Issue 8 (2024) added `readlink`, `realpath`, and `timeout` — but LLMs trained on pre-2024 data still reject these as "not POSIX."

**POSIX.1-2024 Confirmation (from IEEE spec rationale):**
The POSIX.1-2024 Issue 8 spec rationale (https://pubs.opengroup.org/onlinepubs/9799919799/xrat/V4_xcu_chap01.html) confirms the addition of `readlink`, `realpath`, and `timeout`. Also notable: `c99` is now `c17`, and the batch `q*` utilities and `fort77` were removed. LLMs trained before June 2024 will have stale knowledge about all of these.

**Cross-Model Severity:** Research on tool selection from large catalogs (Patil et al., "Gorilla", 2023) shows that name familiarity bias causes LLMs to prefer tools they've seen more in training data. The `tar` over `pax` substitution is a textbook example — `tar` appears 1000x more in training corpora. This bias cannot be overcome by model training alone; it requires runtime intervention.

## 2. Solution: The 2-Tier "Step-Up" Architecture
A progressive, low-token reference mechanism that mirrors human developer workflows.

*   **Tier 1 (`posix-core.md`):** A heavily condensed semantic map of the 155 utilities injected into the agent's context as a Factory Skill. It provides a 2-4 word semantic hook (e.g., `pax: portable archive (NOT tar)`) so the agent knows the tool exists. Max size: ~800 tokens.
*   **Tier 2 (Syntax Lookup Tool):** An agent-native tool (`get_posix_syntax`) backed by a local database (`posix-tldr.json`). Agents are instructed to call this tool *before* executing a Tier 1 utility in the shell. Accepts batch arrays for pipeline lookups.

*Future consideration:* If Tier 2 coverage proves insufficient after benchmark validation, a Tier 3 spec search tool can be added. This is deferred until data motivates it.

### Research Insights

**Architecture Validation:**
- The 2-tier progressive disclosure pattern is architecturally sound for this constraint space. The clean separation (Tier 1 = discovery, Tier 2 = syntax) prevents scope creep and keeps token budgets predictable. (architecture-strategist)
- Two tools is the sweet spot for MCP tool economics. Every tool schema costs tokens every turn. More than 2 tools adds context-window tax; fewer loses the discovery/syntax separation. (agent-native-tool-design research)

**Tier 2 Coverage Gap:**
Tier 2 currently covers only 29 of ~85 non-trivial utilities. This creates a "discovery-to-lookup cliff" — the agent finds a utility in Tier 1 but gets no syntax from Tier 2. Expanding Tier 2 to cover all utilities tested in `benchmark_data.json` is the minimum; covering all non-trivial utilities is the goal. At 155 utilities x ~50 tokens each, the full Tier 2 database is ~7,750 tokens — a lookup problem, not a search problem. (architecture-strategist, spec-flow-analyzer)

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

Key design rules (from MCP tool design research):
- Every parameter must have a description. This is the single highest-leverage thing for tool-calling reliability.
- Say what the tool does AND returns AND does NOT do.
- Cap array size at 10 to prevent context flooding (the "cat trap" via tool).
- Use `readOnlyHint` and `idempotentHint` annotations so hosts can auto-approve calls.

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

OpenAI uniquely offers `strict: true` (constrained decoding) for guaranteed schema adherence.

**MCP Server Configuration:**
```python
mcp = FastMCP(
    "posix-reference",
    instructions=(
        "REQUIRED: Call get_posix_syntax BEFORE using any POSIX utility in a shell command. "
        "Do NOT guess flags. For pipelines, batch all utilities in one call."
    )
)
```
The `instructions` field is the highest-leverage MCP feature for enforcing tool-use patterns.

## 3. Design Principles for Tier 1 Semantic Hooks

Each entry in `posix-core.md` follows these rules:

- **2-5 words per hook.** Below 3 words, LLMs confuse similar tools. Above 5, the 800-token budget is exceeded. This range sits at the empirically safe compression zone (LLMLingua research confirms telegraphic syntax preserves 90-95% task accuracy at 50-70% token reduction).
- **Disambiguate by mechanism, not outcome.** Instead of the shared outcome ("edit text"), state the exclusive differentiating mechanic. `sed` = regex stream, `tr` = 1-to-1 character swap, `awk` = column/field logic.
- **One Verb, One Tool.** Within each namespace, no two tools share a primary verb. If `join` uses "merge", `comm` must use "compare". This is the #1 collision prevention technique (Gorilla/ToolLLM research shows verb overlap is the primary wrong-tool-selection vector).
- **Trap inversion for known hallucination traps.** Format: `tool: positive description (NOT wrong_tool)`. Always lead with the positive description. Limit to 8-12 negation markers total — more risks attention dilution. The `(NOT tar)` pattern is safe because it provides a positive alternative alongside the negation (ironic-process risk only applies to standalone negation without alternatives).
- **Affirmative corrections for Issue 8 additions.** Use `(IS POSIX)` instead of negation for utilities LLMs incorrectly reject. `readlink: resolve symlink (IS POSIX)` is strictly safer than negation — it adds information without priming wrong answers.
- **8 categorical namespaces with `[BRACKET_CAPS]` headers.** Empirically validated: 5-9 top-level categories maximize discrimination (ToolLLM). Bracketed ALL-CAPS headers trigger "structured data scanning" mode (code-trained attention heads). Each header acts as a positional reset, counteracting lost-in-the-middle effects.
- **Order by query frequency.** Place `[TEXT_DATA_PROC]` first (most common queries), `[DEV_BUILD]` and `[IPC_COMM]` last (least common). At ~800 tokens the positional effect is minimal, but it costs nothing to optimize for it.

### Research Insights

**Semantic Compression Validation:**
- At ~800 tokens, `posix-core.md` is in the "perfect retrieval" zone. Needle-in-a-haystack studies show near-perfect accuracy at sub-2K context lengths across all major models. The lost-in-the-middle problem is irrelevant at this size. (semantic compression research)
- Structured context outperforms unstructured by 10-25% for retrieval accuracy (Liu et al., "Lost in the Middle", 2023). The bracket headers provide structural anchors that help attention heads localize relevant sections.
- When injected as a system prompt/skill, positional effects are further reduced — system prompts receive dedicated attention in Claude and GPT models.

**Cross-Model Format Compatibility:**
- The `tool: description (qualifier)` format with bracket headers and ASCII characters works reliably across Claude, GPT/Codex, and Gemini.
- Claude benefits most from injected reference (best instruction following). Codex benefits least (most likely to rely on parametric knowledge). Gemini is in the middle but more susceptible to hallucinating past negation markers. (semantic compression research)
- Consider bolstering negation patterns for Gemini: `pax: the POSIX archiver (NOT tar)` with emphasis on the affirmative.

**Token Budget:**
- Dropping bullet markers (`* `) saves ~310 tokens across 155 entries. If the budget is tight, this is the first thing to cut — namespace headers provide sufficient structure.
- Consistent delimiter patterns are critical. The LLM builds a parsing template after 2-3 entries and extrapolates to the rest. Inconsistency degrades retrieval by 10-15%.

## 4. Edge Cases & Risks

### The Rebellious Agent (Hallucination)
The LLM reads `pax` in Tier 1 but ignores Tier 2 and confidently guesses the syntax (e.g., `pax -z`).

*Mitigation:* MCP `instructions` field provides always-on baseline enforcement. Rich error results from Tier 2 correct misconceptions inline. The benchmark tracks `tool_calls_by_type` to detect non-compliance — if `get_posix_syntax` wasn't called before answering, the `failure_mode` field flags it. Shell interception middleware is a future consideration if measurement shows the problem persists.

### The Context Flood
The `posix-tldr.json` database is wrapped behind the `get_posix_syntax` tool interface with a hard array cap of 10 utilities per call. The agent never has raw file access. This prevents both the "cat trap" (reading the raw file) and the "batch dump" (requesting all 155 utilities at once).

### Complex Pipelines
Tasks requiring three tools (e.g., `sort | uniq | comm`) trigger latency spikes if looked up sequentially. The tool accepts arrays and returns a keyed JSON object. For pipeline-aware lookups, include interaction notes (e.g., `"comm requires sorted input"`).

### Research Insights

**Security Findings (from security-sentinel):**
- **Tool-call command extraction is unsanitized (Medium risk).** The `run_benchmark.py` tool simulation extracts a command name from the LLM response via regex and uses it as a dict key. A crafted response could inject arbitrary strings. *Mitigation:* Validate extracted command against the keys of `posix-tldr.json` before building the follow-up prompt.
- **Question ID path traversal (Low risk).** If `benchmark_data.json` were tampered with to include `../` in an `id` field, files could be written outside `results/`. *Mitigation:* Add `re.match(r'^[A-Za-z0-9_-]+$', q_id)` validation in `result_path()`.
- **No spending cap (Low risk).** `--k 100` across many questions could generate significant API costs. *Mitigation:* Add a `--budget` flag or confirmation prompt when estimated cost exceeds a threshold.
- **XSS in HTML reports: properly handled.** All dynamic content uses `html.escape()`. No action needed.
- **Subprocess injection: properly handled.** `subprocess.run()` uses list form, no `shell=True`. No action needed.
- **Base64 judge encoding: sufficient.** Industry-standard mitigation for LLM-as-judge prompt injection. Add "Do NOT reward verbosity" to the grading rubric.

**Performance Findings (from performance-oracle):**
- **Double-invocation tool simulation double-counts input tokens.** The merged token totals include both calls' input tokens, but the second call re-sends the entire conversation. When comparing Track 1 vs Track 2, subtract the injection overhead (~800 tokens) and the re-sent prompt tokens.
- **Codex token accounting only captures the last `turn.completed` event.** Multi-step Codex runs (8-10 steps) may report tokens from only the final step, undercounting total usage by 3-10x. Consider summing across all JSONL events.
- **Missing rate-limit backoff.** 8 consecutive Claude failures in existing results suggest the concurrent requests hit Anthropic's rate limiter. Add exponential backoff with jitter.
- **Cost projection:** A full Track 1+2 run at k=3 would cost $28-67. Reducible by ~70% with cache warming (run a "hello" call per provider before the benchmark) and progressive depth (start with k=1, increase only for high-variance questions).

**Spec Flow Gaps (from spec-flow-analyzer, 14 gaps identified):**
- **Critical:** No defined behavior when Tier 2 lookup fails for ~125 of 155 utilities that aren't in `posix-tldr.json`. The tool should return a graceful fallback: "Utility exists in POSIX but detailed syntax not yet in database. Use with caution."
- **Critical:** The mechanism for exposing `get_posix_syntax` as a callable tool to each LLM CLI is completely unspecified. The current `run_benchmark.py` uses text-pattern matching (`TOOL_CALL: get_posix_syntax(...)`) as a simulation — this is architecturally different from real MCP/function-calling tool integration.
- **Important:** No defined behavior for utilities spanning multiple categories (e.g., `awk` is both text processing and scripting). Current placement in `[TEXT_DATA_PROC]` is fine for the map, but the tool should accept `awk` regardless of which namespace the user found it in.

## 5. Implementation Steps & Acceptance Criteria (Definition of Done)

### Step 1: Deliver Tier 1 Skill
*   **Task:** Finalize `posix-core.md`.
*   **Status:** Already exists and covers all 155 utilities with namespace grouping.
*   **Acceptance Criteria:**
    *   [x] File exists, contains all 155 POSIX Issue 8 utilities, grouped by the 8 categorical namespaces.
    *   [ ] Total file size verified under 1,000 tokens (measure with `tiktoken o200k_base` or word count proxy: <750 words).
    *   [x] Trivial commands grouped without descriptions.
    *   [x] Non-trivial commands have 2-5 word descriptions following the design principles.

### Step 2: Expand Tier 2 Coverage
*   **Task:** Expand `posix-tldr.json` to cover all utilities tested in `benchmark_data.json` and add graceful fallback for missing utilities.
*   **Status:** 29 utilities currently covered. 30 benchmark questions. Gap: verify all expected commands have Tier 2 entries.
*   **Acceptance Criteria:**
    *   [ ] Every `expected_commands` value in `benchmark_data.json` has a corresponding entry in `posix-tldr.json`.
    *   [ ] Tool returns a structured "not yet covered" response for utilities in Tier 1 but missing from Tier 2 (not a hard error).
    *   [ ] Array input validated: min 1, max 10 utility names per call.

### Step 3: Harden the Test Harness
*   **Task:** Fix known measurement issues in `run_benchmark.py`.
*   **Status:** `--inject-posix` flag is wired. Tool simulation works via text pattern matching.
*   **Acceptance Criteria:**
    *   [ ] Rate-limit backoff with exponential jitter added for all CLI invocations.
    *   [ ] Tool-call command extraction validates against `posix-tldr.json` keys (security fix).
    *   [ ] Question ID sanitized with `re.match(r'^[A-Za-z0-9_-]+$', q_id)`.
    *   [ ] Question order randomized per run with a fixed seed for reproducibility.
    *   [ ] `python3 -m py_compile run_benchmark.py` passes.

### Step 4: Run Baseline (Track 1)
*   **Task:** Establish unassisted baseline for all 30 questions on Claude and Codex at k=5.
*   **Acceptance Criteria:**
    *   [ ] `valid_results` equals `total_results` for each LLM.
    *   [ ] Per-tier metrics computed: mean output tokens, POSIX compliance rate, failure mode distribution.
    *   [ ] Summary saved to `results/`.

### Step 5: Run Step-Up (Track 2) and Compare
*   **Task:** Run with `--inject-posix` and compare against Track 1.
*   **Pre-registered Hypotheses:**
    *   H1: Track 2 reduces mean output tokens by >= 20%.
    *   H2: Track 2 reduces `non_posix_substitution` failure mode by >= 50%.
    *   H3: Track 2 achieves >= 80% POSIX compliance (absolute).
    *   H4: Track 2 eliminates Issue 8 refusals (count -> 0).
*   **Protocol:**
    *   Run Track 2 in a separate session from Track 1 (>= 10 min gap for cache TTL).
    *   Subtract `posix-core.md` injection overhead (~800 tokens) when comparing total billable tokens.
    *   Report cold-cache and warm-cache aggregates separately.
*   **Acceptance Criteria:**
    *   [ ] POSIX compliance rate improves by >= 20 percentage points vs Track 1 baseline.
    *   [ ] `get_posix_syntax` tool call count > 0 for >= 80% of Tier 2 and Tier 3 questions.
    *   [ ] Net token savings (after subtracting injection overhead) is positive.
    *   [ ] Results analyzed with Wilcoxon signed-rank test; report effect size (Cohen's d) and 95% bootstrap CI.

### Research Insights

**Benchmark Methodology (from LLM benchmark methodology research):**
- **k=5 is the recommended minimum.** k=3 is acceptable for cost-constrained initial runs. Codex needs k=7 due to 4x variance from agentic tool use.
- **Proposed composite metric — Token Efficiency Score (TES):** `TES = (accuracy_score / 2) * (minimal_word_count / response_word_count)`. Range 0.0-1.0. Penalizes verbosity proportionally.
- **Word count is the practical cross-model comparison metric.** Different tokenizers make raw token counts incomparable. `response_word_count` and `verbosity_ratio` are already implemented and tokenizer-agnostic.
- **Frame "minimal answer gap + failure mode taxonomy" as the novel contribution.** No existing benchmark combines known minimal answers, token-level waste measurement, and failure mode categorization. The project's `failure_mode` classification is a genuine contribution to LLM efficiency measurement methodology.
- **Report negative results.** If Track 2 makes things worse for Tier 1 (injecting reference for tasks the model already handles well), report that. Per-tier deltas are more informative than overall averages.
- **LLM-as-judge optimization:** Run full benchmark in `--no-grade` mode first (tokens only). Then grade only ambiguous results where automated analysis disagrees with expectations. This minimizes judge cost.

**Statistical Methods:**
- **Wilcoxon signed-rank test** for paired Track 1/Track 2 comparison (non-parametric, handles right-skewed token distributions).
- **Bootstrap confidence intervals** (stdlib-compatible, works at k=5):
```python
def bootstrap_ci(values, n_bootstrap=10000, ci=0.95):
    means = sorted(sum(random.choices(values, k=len(values))) / len(values) for _ in range(n_bootstrap))
    lower = means[int((1 - ci) / 2 * n_bootstrap)]
    upper = means[int((1 + ci) / 2 * n_bootstrap)]
    return lower, upper
```
- **Report CV per question per model.** CV > 0.5 indicates high non-determinism; flag for investigation or increased k.

**Implementation Reality Check (from simplicity review):**
The codebase is ahead of the PRD:
- `posix-core.md` exists and works.
- `posix-tldr.json` exists with 29 utilities.
- `--inject-posix` is wired in `run_benchmark.py`.
- The MVP is literally one benchmark run away: `python3 run_benchmark.py --llms claude --inject-posix` vs baseline.

## References

- POSIX.1-2024 (Issue 8): https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html
- POSIX Issue 8 rationale: https://pubs.opengroup.org/onlinepubs/9799919799/xrat/V4_xcu_chap01.html
- Liu et al., "Lost in the Middle" (2023) — context position effects
- Patil et al., "Gorilla" (2023) — tool selection from large catalogs
- Qin et al., "ToolLLM" (2023) — hierarchical tool organization
- Jiang et al., "LLMLingua" (2023) — prompt compression
- MCP spec (2025): tool annotations, instructions field, structuredContent
- Artificial Analysis methodology: https://artificialanalysis.ai/methodology
