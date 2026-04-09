---
title: "Agent-Native Tool Design Best Practices for Knowledge Retrieval"
date: 2026-03-29
status: complete
scope: Research for POSIX Step-Up 3-Tier Architecture (Tier 2 & Tier 3 tools)
sources:
  - "Skill: agent-native-architecture (Compound Engineering)"
  - "Skill: build-mcp-server (Claude Plugins Official)"
  - "Skill: agent-native-audit (Compound Engineering)"
  - "Reference: mcp-tool-design.md"
  - "Reference: tool-design.md"
  - "Reference: dynamic-context-injection.md"
  - "Reference: from-primitives-to-domain-tools.md"
  - "Reference: server-capabilities.md"
  - "Reference: elicitation.md"
  - "Anthropic tool_use docs, OpenAI function calling docs, Google tool declarations docs"
---

# Agent-Native Tool Design Best Practices

## Context

This research supports the POSIX Step-Up Architecture's Tier 2 (`get_posix_syntax`) tool. The goal: design tool interfaces that LLMs call reliably, return results that minimize token consumption, and structurally enforce lookup-before-execute behavior.

> **Note on Tier 3 (`search_posix_spec`):** This tool is currently **deferred**. No benchmark question required it, and no measured failure motivated it. All references to `search_posix_spec` in this document are retained as forward-looking design guidance only — it is not implemented and should not be built until Track 3 data shows Tier 2 is insufficient.

---

## 1. Tool Schema Design for Maximum LLM Tool-Calling Reliability

### 1.1 Parameter Naming

**Use descriptive, domain-vocabulary parameter names.**

| Weak | Strong | Why |
|------|--------|-----|
| `input` | `utilities` | Anchors the concept — LLM knows it's looking up utility names |
| `q` | `query` | Self-documenting; LLMs treat abbreviated names as ambiguous |
| `data` | `utility_names` | Type-as-name improves call accuracy |
| `args` | `flags` | Domain-specific name reduces wrong-parameter errors |

**Source:** `tool-design.md` (build-mcp-server skill): *"The `.describe()` text shows up in the schema Claude sees. Omitting it is leaving money on the table."*

### 1.2 Parameter Descriptions

Every parameter MUST have a `.describe()` (Zod) or `description` field. This is the single highest-leverage thing you can do for tool-calling reliability.

**Pattern for `get_posix_syntax`:**
```json
{
  "name": "get_posix_syntax",
  "description": "Look up exact POSIX.1-2024 syntax for one or more utilities. Returns pure-POSIX flags and usage patterns — no GNU extensions, no BSD variants. Call this BEFORE using any POSIX utility in a shell command.",
  "parameters": {
    "utilities": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Array of POSIX utility names to look up (e.g. [\"sed\", \"awk\", \"sort\"]). Use names exactly as listed in the POSIX semantic map."
    }
  }
}
```

**Key rules from skill-based research:**
- **Say what it does AND what it returns** — "Returns pure-POSIX syntax strings" not just "Looks up syntax"
- **Say what it does NOT do** — "no GNU extensions, no BSD variants" prevents wrong expectations
- **Disambiguate siblings** — If `search_posix_spec` exists alongside `get_posix_syntax`, each description should say when to use the other:
  - `get_posix_syntax`: "...For edge-case flags or interaction details not covered here, use search_posix_spec."
  - `search_posix_spec`: "...For standard syntax, use get_posix_syntax first — it's faster and cheaper."

### 1.3 Schema Constraints

**Tight schemas prevent bad calls.** Every constraint expressed in the schema is one fewer runtime failure.

| Instead of | Use |
|------------|-----|
| `z.string()` for utility names | `z.string().regex(/^[a-z][a-z0-9_]*$/)` — utility names are lowercase |
| `z.array(z.string())` unbounded | `z.array(z.string()).min(1).max(10)` — prevent context flooding |
| `z.string()` for query | `z.string().min(3).max(200).describe("Natural language query...")` |

**Source:** `tool-design.md`: *"Tight schemas prevent bad calls. Every constraint you express in the schema is one fewer thing that can go wrong at runtime."*

### 1.4 Tool Naming

Names should describe the **capability**, not the use case.

| Anti-pattern | Correct |
|-------------|---------|
| `check_if_posix_flag_exists` | `get_posix_syntax` |
| `help_user_with_command` | `search_posix_spec` |
| `validate_and_return_syntax` | `get_posix_syntax` |

**Source:** `mcp-tool-design.md`: *"Names should describe the capability, not the use case. The prompt tells the agent when to use primitives. The tool just provides capability."*

### 1.5 Tool Count Economics

Every tool schema is tokens the LLM spends **every turn**. For the POSIX system:

| Tool Count | Guidance |
|-----------|----------|
| 1–15 tools | One tool per action. Sweet spot. |
| 15–30 tools | Audit for duplicates. |
| 30+ tools | Switch to search + execute pattern. |

**Recommendation for POSIX:** Two tools is the sweet spot. `get_posix_syntax` (structured lookup) and `search_posix_spec` (free-text search). Do NOT create 155 individual tools per utility.

---

## 2. Result Formatting for Minimal Token Consumption

### 2.1 Core Principle: Return What the LLM Needs, Nothing More

**For `get_posix_syntax` specifically:**

```json
{
  "sed": {
    "synopsis": "sed [-n] script [file...]",
    "posix_flags": ["-n", "-e"],
    "traps": ["NO -i flag (GNU only)", "NO -r flag (GNU only)"],
    "portable_pattern": "sed 's/old/new/' file > tmp && mv tmp file"
  }
}
```

**Why this format works:**
- `synopsis` — the one line the LLM needs most (matches man page muscle memory in training data)
- `posix_flags` — explicit whitelist prevents hallucinating GNU flags
- `traps` — negative reinforcement is more token-efficient than listing everything that doesn't work
- `portable_pattern` — for the most common gotcha (in-place editing), give the answer directly

### 2.2 Truncation With Signposting

**Source:** `tool-design.md`: *"Truncate huge payloads and say so: 'Showing 10 of 847 results. Refine the query to narrow down.'"*

For `search_posix_spec`:
```
Found 3 sections matching "sed backreference extended":

1. sed(1p) §EXTENDED DESCRIPTION — BRE backreference syntax \1..\9
2. sed(1p) §ADDRESSES — Line and pattern address forms
3. re_format(7) §BASIC REGULAR EXPRESSIONS — Parenthesized subexpressions

Showing summaries. For full text of a section, call search_posix_spec with section ID.
```

### 2.3 Structured vs. Prose Results

| Format | Tokens | LLM Comprehension | Best For |
|--------|--------|--------------------|----------|
| JSON (compact) | Lowest | High for structured data | `get_posix_syntax` — utility lookups |
| JSON (pretty-printed) | Medium | High | Debug/inspection |
| Prose/Markdown | Highest | Highest for narrative | `search_posix_spec` — explanatory content |
| Key-value pairs | Low | High | Single-utility quick returns |

**Recommendation:** `get_posix_syntax` returns compact JSON. `search_posix_spec` returns Markdown with section headers.

### 2.4 Return IDs for Follow-Up Calls

**Source:** `tool-design.md`: *"Include IDs Claude will need for follow-up calls."*

Always include identifiers the LLM needs for chaining:
```json
{
  "pax": {
    "synopsis": "pax [-cdnv] [-f archive] ...",
    "spec_section_id": "pax_1p",
    "note": "For detailed flag interactions, call search_posix_spec(query='pax archive creation flags', section='pax_1p')"
  }
}
```

### 2.5 Rich Error Results

**Source:** `tool-design.md`: *"The hint ('use search_items…') turns a dead end into a next step."*

```json
{
  "isError": true,
  "content": "Unknown utility: 'xxd'. xxd is NOT a POSIX utility. For hex dump, use: od -A x -t x1z. Call get_posix_syntax(['od']) for full syntax."
}
```

This pattern:
1. Corrects the misconception (`xxd` is not POSIX)
2. Gives the immediate answer (`od -A x -t x1z`)
3. Offers the structured follow-up path (`get_posix_syntax(['od'])`)

---

## 3. Forced Tool Use Patterns ("Lookup Before Execute")

### 3.1 The Problem

The PRD identifies the "Rebellious Agent" failure mode: LLM reads `pax` in Tier 1, ignores Tier 2, and confidently writes `pax -z` (which doesn't exist). Prompt-level instructions ("DO NOT GUESS") are fragile.

### 3.2 Pattern A: MCP `instructions` Field (Weakest, Easiest)

```python
mcp = FastMCP(
    "posix-reference",
    instructions="ALWAYS call get_posix_syntax before using any utility listed in the POSIX semantic map in a shell command. IDs aren't guessable — syntax must be looked up."
)
```

**Source:** `server-capabilities.md`: *"This is the highest-leverage one-liner in the spec. If Claude keeps misusing your tools, put the fix here."*

**Strength:** Lands in system prompt automatically. Zero friction.
**Weakness:** Still prompt-level — a confident LLM can ignore it.

### 3.3 Pattern B: Structural Interception (Strongest, Most Complex)

The PRD already identifies the correct long-term pattern: **intercept the shell execution layer.**

```
IF agent calls bash/shell with a Tier 1 utility
AND agent did NOT call get_posix_syntax for that utility in this turn
THEN return structured error:
  "ERROR: You used 'pax' without looking up its syntax.
   Call get_posix_syntax(['pax']) first, then retry."
```

**Implementation approach:**
1. Wrap the shell execution tool with a middleware/proxy
2. Parse the command string for utility names (simple regex against the 155-name list)
3. Check the conversation/turn state for a preceding `get_posix_syntax` call
4. If missing, return an error with the corrective action

This is the "gate" pattern from `from-primitives-to-domain-tools.md`, applied correctly: *"Gating is appropriate for data integrity — operations that must maintain invariants."*

### 3.4 Pattern C: Two-Phase Tool Design

Design the tool to output a "must confirm" intermediate result:

```
Step 1: get_posix_syntax(["sed"]) → returns syntax + a "confirmation_token"
Step 2: execute_posix_command(command="sed ...", confirmation_token="tok_abc") → executes
```

Without the token, `execute_posix_command` refuses. This is similar to the elicitation pattern but machine-to-machine.

### 3.5 Pattern D: Context Injection with Tool-Call Tracking

Inject recent tool calls into the system prompt dynamically:

```
## Tool Call State
- get_posix_syntax called for: [sed, awk] ✓
- NOT yet looked up: [comm, sort] — MUST call get_posix_syntax before using these
```

**Source:** `dynamic-context-injection.md`: Dynamic context tells the agent what it can do RIGHT NOW.

### 3.6 Recommendation for POSIX System

**Layer the approaches:**
1. **MCP `instructions`** — always-on baseline (Pattern A)
2. **Shell interception** — structural enforcement (Pattern B) for production
3. **Rich error results** — when a utility is queried, include syntax AND the instruction to use it verbatim

The combination of structural enforcement + rich errors is far more reliable than any amount of prompt engineering.

---

## 4. Batch Tool Call Patterns

### 4.1 The Problem

Complex pipelines like `sort | uniq | comm` require 3 separate lookups. Sequential calls multiply latency. The PRD identifies this: *"The `get_posix_syntax` tool must accept an array of strings to batch pipeline lookups into a single call."*

### 4.2 Array Parameter Pattern (Recommended)

```json
{
  "name": "get_posix_syntax",
  "parameters": {
    "utilities": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1,
      "maxItems": 10,
      "description": "Array of utility names. For pipelines, include all tools (e.g. ['sort', 'uniq', 'comm'])."
    }
  }
}
```

**Return format for batches:**
```json
{
  "sort": { "synopsis": "sort [-bdfimru] [-t char] [-k keydef] [file...]", "posix_flags": [...] },
  "uniq": { "synopsis": "uniq [-c|-d|-u] [-f fields] [-s chars] [input [output]]", "posix_flags": [...] },
  "comm": { "synopsis": "comm [-123] file1 file2", "posix_flags": [...], "note": "Both files MUST be sorted" }
}
```

### 4.3 Cap the Batch Size

Hard cap at 10 utilities per call. Without a cap, an agent could call `get_posix_syntax(all_155_utilities)` and flood its context — the exact "cat trap" the architecture prevents.

**Source:** `tool-design.md`: *"z.number().int().min(1).max(100).default(20)"* — always set explicit bounds.

### 4.4 Cross-Provider Batch Behavior

| Provider | Parallel Tool Calls? | Batch-in-Single-Call? |
|----------|---------------------|-----------------------|
| Anthropic Claude | Yes (multiple `tool_use` blocks in one response) | Yes (array params) |
| OpenAI | Yes (`parallel_tool_calls` param) | Yes (array params) |
| Google Gemini | Yes (multiple `functionCall` blocks) | Yes (array params) |

All three providers support both approaches. The array-parameter approach is preferable because:
- 1 call vs. N calls = less latency
- 1 tool result vs. N tool results = less token overhead per-turn
- Simpler conversation history

### 4.5 Pipeline-Aware Return Enhancement

For pipeline lookups, include interaction notes:

```json
{
  "sort": { "synopsis": "sort [-bdfimru] ...", "pipeline_note": "Output is sorted lines on stdout" },
  "uniq": { "synopsis": "uniq [-cdu] ...", "pipeline_note": "Input MUST be sorted. Pipe from sort." },
  "comm": { "synopsis": "comm [-123] file1 file2", "pipeline_note": "Both files MUST be sorted. Use process substitution or temp files for piped input." }
}
```

---

## 5. MCP Best Practices (2025–2026)

### 5.1 Use `instructions` for Global Tool-Use Hints

```python
mcp = FastMCP("posix-ref", instructions="Call get_posix_syntax before executing any POSIX utility.")
```

This is the single highest-leverage feature in the MCP spec for enforcing tool-use patterns.

### 5.2 Use Tool Annotations

```python
@mcp.tool(annotations={
    "readOnlyHint": True,      # No side effects — host may auto-approve
    "idempotentHint": True,    # Safe to retry
    "openWorldHint": False     # No external network calls
})
def get_posix_syntax(utilities: list[str]) -> str:
    ...
```

For `get_posix_syntax`: `readOnlyHint=True`, `idempotentHint=True`, `openWorldHint=False`
For `search_posix_spec`: `readOnlyHint=True`, `idempotentHint=True`, `openWorldHint=True` (if querying external spec)

### 5.3 Return `structuredContent` + Text Fallback

```python
return {
    "content": [{"type": "text", "text": json.dumps(result)}],  # backward compat
    "structuredContent": result                                    # typed output
}
```

Always include the text fallback — not all hosts read `structuredContent` yet.

### 5.4 Error Handling: Guide, Don't Dead-End

```python
if utility not in posix_db:
    return {
        "isError": True,
        "content": [{
            "type": "text",
            "text": f"'{utility}' not found in POSIX database. "
                    f"Did you mean one of: {', '.join(close_matches)}? "
                    f"Or use search_posix_spec(query='{utility}') for a broader search."
        }]
    }
```

### 5.5 Progress Reporting for Tier 3 (Spec Search)

If `search_posix_spec` performs vector search that takes time:
```python
@mcp.tool
async def search_posix_spec(query: str, ctx: Context) -> str:
    await ctx.report_progress(progress=0, total=3, message="Parsing query")
    # ... search logic ...
    await ctx.report_progress(progress=2, total=3, message="Ranking results")
    # ... ranking ...
    await ctx.report_progress(progress=3, total=3, message="Done")
    return formatted_results
```

### 5.6 Keep Tool Surface Small

Two tools is ideal for this system. Do NOT create per-utility tools. The "search + execute" pattern from the MCP skill applies:

- `get_posix_syntax` = structured lookup (like "execute_action" but read-only)
- `search_posix_spec` = discovery (like "search_actions")

---

## 6. Cross-Provider Reliability Differences

### 6.1 Anthropic Claude (`tool_use`)

**Mechanism:** `tools` array in API request with JSON Schema. Model returns `tool_use` content blocks.

**Strengths:**
- Most reliable tool-calling in structured conversations
- Supports `tool_choice: {"type": "tool", "name": "..."}` to force specific tool calls
- Parallel tool calls supported
- `cache_control` on tool definitions to reduce input token costs on repeated calls

**Forced tool use:** `tool_choice: {"type": "tool", "name": "get_posix_syntax"}` forces the model to call this specific tool. `tool_choice: {"type": "any"}` forces the model to call at least one tool.

**Token note:** Tool schemas in system prompt are subject to prompt caching. Mark tool definitions with `cache_control: {"type": "ephemeral"}` to avoid re-tokenizing every turn.

### 6.2 OpenAI (`function_calling` / `tools`)

**Mechanism:** `tools` array with `type: "function"`. Model returns `tool_calls` in assistant message.

**Strengths:**
- `tool_choice: {"type": "function", "function": {"name": "..."}}` for forced calls
- `parallel_tool_calls: true/false` — explicit control
- `strict: true` mode enables guaranteed JSON Schema adherence (Structured Outputs)

**Key difference:** OpenAI's `strict: true` on `function.parameters` enforces exact schema compliance at the token-generation level (constrained decoding). This eliminates malformed arguments. Anthropic doesn't have an equivalent — it relies on the model following the schema.

**Forced tool use:** Same pattern as Claude — `tool_choice` forces specific or any tool call.

### 6.3 Google Gemini (`functionDeclarations`)

**Mechanism:** `tools` with `functionDeclarations` array. Model returns `functionCall` parts.

**Strengths:**
- Supports `toolConfig.functionCallingConfig.mode`: `AUTO`, `ANY`, `NONE`
- `allowedFunctionNames` to restrict which tools can be called
- Native grounding with Google Search

**Key difference:** Gemini's `mode: "ANY"` with `allowedFunctionNames: ["get_posix_syntax"]` is the equivalent of forced tool use.

**Reliability concern:** Gemini CLI prepends "MCP issues detected..." noise to output (documented in CLAUDE.md). Must strip before JSON parsing.

### 6.4 Provider Comparison Summary

| Feature | Claude | OpenAI | Gemini |
|---------|--------|--------|--------|
| Force specific tool | ✅ `tool_choice.name` | ✅ `tool_choice.function.name` | ✅ `allowedFunctionNames` |
| Force any tool | ✅ `tool_choice: any` | ✅ `tool_choice: required` | ✅ `mode: ANY` |
| Parallel calls | ✅ implicit | ✅ `parallel_tool_calls` | ✅ implicit |
| Strict schema | ❌ (model-level) | ✅ `strict: true` | ❌ (model-level) |
| Batch via array param | ✅ | ✅ | ✅ |
| Tool result caching | ✅ prompt cache | ❌ | ✅ context caching |

### 6.5 Cross-Provider Tool Definition

To maximize cross-provider compatibility, use this subset:
- JSON Schema draft-07 for parameters
- `type`, `description`, `properties`, `required` only
- Avoid `$ref`, `oneOf`, `anyOf` (inconsistent support)
- Keep descriptions under 500 characters
- Use `enum` for fixed choices, but prefer `string` with description for flexible inputs (per agent-native principle: *"Use `z.string()` inputs when the API validates, not `z.enum()`"*)

---

## Concrete Recommendations for the POSIX Step-Up System

### Tool 1: `get_posix_syntax`

```json
{
  "name": "get_posix_syntax",
  "description": "Look up exact POSIX.1-2024 (Issue 8) syntax for one or more utilities. Returns pure-POSIX synopsis, flags, and common traps. NO GNU/BSD extensions. Call this BEFORE using any utility from the POSIX semantic map in a shell command. For edge-case flags or spec-level details, use search_posix_spec instead.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "utilities": {
        "type": "array",
        "items": { "type": "string" },
        "minItems": 1,
        "maxItems": 10,
        "description": "POSIX utility names to look up. For pipelines, include all tools (e.g. ['sort', 'uniq', 'comm'])."
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

**Return format:**
```json
{
  "sed": {
    "synopsis": "sed [-n] script [file...]",
    "posix_flags": ["-n", "-e"],
    "traps": ["NO -i (GNU)", "NO -r (GNU)", "NO -E (varies)"],
    "example": "sed 's/old/new/g' input > output"
  }
}
```

### Tool 2: `search_posix_spec`

```json
{
  "name": "search_posix_spec",
  "description": "Search the POSIX.1-2024 spec for detailed information — edge-case flags, interaction behavior between utilities, or portability notes. Use get_posix_syntax first for standard syntax — this tool is for when that's not enough.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "minLength": 3,
        "maxLength": 200,
        "description": "Natural language query about POSIX behavior (e.g. 'sed backreference syntax in BRE mode')"
      }
    },
    "required": ["query"]
  },
  "annotations": {
    "readOnlyHint": true,
    "idempotentHint": true,
    "openWorldHint": true
  }
}
```

### MCP Server Configuration

```python
mcp = FastMCP(
    "posix-reference",
    instructions=(
        "REQUIRED: Call get_posix_syntax BEFORE using any POSIX utility in a shell command. "
        "Do NOT guess flags from training data — POSIX syntax must be verified via tool lookup. "
        "For pipelines, batch all utilities in a single call: get_posix_syntax(['sort', 'uniq', 'comm'])."
    )
)
```

### Enforcement Layers (Priority Order)

1. **MCP `instructions`** — always active, zero implementation cost
2. **Rich error results** — non-POSIX utilities return the correct POSIX alternative
3. **Shell interception middleware** — detect un-looked-up utilities in shell commands, return structured error forcing the step-up
4. **Provider-level `tool_choice`** — for critical turns, force `get_posix_syntax` call before shell execution

---

## Key Takeaways

1. **Tool descriptions are prompt engineering.** The description is the contract Claude reads before deciding to call the tool. Write it like a one-line manpage entry plus disambiguating hints.

2. **Tight schemas prevent bad calls.** Constrain array sizes, add regex patterns, set min/max bounds. Every constraint is one fewer runtime failure.

3. **Return format should minimize tokens while maximizing actionability.** Compact JSON for structured lookups, Markdown for narrative search results. Always include IDs for follow-up calls.

4. **Structural enforcement > prompt warnings.** "DO NOT GUESS" is fragile. Shell interception middleware that returns errors is reliable. Layer defenses: MCP instructions + rich errors + structural gates.

5. **Batch via array parameters, not parallel calls.** One call returning 3 utilities is cheaper (token-wise) than 3 separate call/response cycles.

6. **Two tools is the sweet spot** for this domain. More adds context-window tax. Fewer loses the Tier 2/3 separation.

7. **Cross-provider forced tool use works.** All three major providers (Claude, OpenAI, Gemini) support forcing specific tool calls — use it for the "lookup before execute" pattern.
