## Enhancement Summary

**Deepened on:** 2026-03-26
**Sections enhanced:** 4 (Architecture, Methodology, Edge Cases, Implementation)
**Research agents used:** `architecture-strategist`, `agent-native-reviewer`, `spec-flow-analyzer`

### Key Improvements
1. **Removed the `jq` dependency:** The original plan relied on `jq` to parse the Tier 2 JSON file, which is a massive contradiction since `jq` is not a POSIX utility. Replaced the JSON approach with an agent-native tool primitive `get_posix_syntax()` to prevent shell parsing errors.
2. **Formalized Tier 3 Fallback:** The IEEE spec fallback was undefined, leading to potential token bloat. It has been scoped to a specific search tool mechanism rather than raw web access.
3. **Protected the Context Window:** Added structural mitigations to prevent the "Rebellious Agent" from simply running `cat posix-tldr.json` and flooding its context window.

### New Considerations Discovered
- Using ALL CAPS prompt warnings ("DO NOT GUESS") is a fragile anti-pattern. Structural tool requirements (forcing the agent to call the syntax lookup tool before a shell execution tool) are far more reliable.
- Complex pipelines (e.g., `sort | uniq | comm`) require the syntax lookup tool to accept batch arrays to prevent latency multiplication.

---

# Product Requirements Document (PRD): POSIX "Step-Up" Architecture

## 1. Problem Statement
LLMs lack working knowledge of the 155 native POSIX Issue 8 utilities. When asked to perform CLI tasks, they fail to realize native tools exist, hallucinate non-POSIX GNU flags, and write complex Python/Bash scripts as workarounds. This results in massive compute waste (e.g., Codex burning 80,000 tokens on a simple data task) and fragile, non-portable code. We cannot inject full man pages into the prompt (context tax), nor can we rely on the LLM to proactively look up commands it doesn't know exist.

## 2. Solution: The 3-Tier "Step-Up" Architecture
A progressive, low-token reference mechanism that perfectly mirrors human developer workflows.

*   **Tier 1 (`posix-core.md`):** A heavily condensed semantic map of the 155 utilities injected into the agent's context as a Factory Skill. It provides a 2-4 word semantic hook (e.g., `pax: portable archive`) so the agent knows the tool exists. Max size: ~800 tokens.
*   **Tier 2 (Syntax Lookup Tool):** An agent-native tool (`get_posix_syntax`) backed by a local database. Agents are instructed to call this tool *before* executing a Tier 1 utility in the shell.
*   **Tier 3 (IEEE Fallback Tool):** A scoped search tool (`search_posix_spec`) that queries a vectorized version of the POSIX.1-2024 spec, used only if Tier 2 lacks the required edge-case flags.

### Research Insights
**Architecture & Agent Patterns:**
- **Avoid Leaky Abstractions:** Forcing the LLM to write bash commands to query its own knowledge base (e.g., parsing a JSON file via CLI) couples knowledge retrieval to the OS layer. Using native agent tools (like `get_posix_syntax(utilities: List[str])`) is the correct architectural pattern.
- **Top-Tier Promotion:** For the absolute most common commands (e.g., `sed`, `grep`), embed their minimal correct syntax directly within Tier 1 to save the round-trip latency of Tier 2 lookups.

## 3. Methodology: Engineering the Tier 1 Semantic Hooks
To ensure the LLM's attention mechanism can successfully map user intent to the correct POSIX tool without "Semantic Collisions", we use a strict 5-part methodology:

1.  **Intent Extraction:** We mine the exact verbs/nouns from human questions in `benchmark_data.json` to minimize the semantic gap.
2.  **Trap Inversion:** We explicitly invert known hallucination traps documented in the benchmark (e.g., `pax: archive (NO TAR)`).
3.  **Disambiguation (The "How"):** Instead of describing the shared outcome ("edit text"), the hook states the exclusive differentiating mechanic. (`sed` = regex, `tr` = 1-to-1 char swap, `awk` = column/field logic).
4.  **Categorical Namespacing:** Commands are grouped under 8 strict headers so the LLM processes the list hierarchically:
    *   `[CORE_TRIVIAL]`, `[TEXT_DATA_PROC]`, `[FILE_DIR_OPS]`, `[PROCESS_MGMT]`, `[SYS_ENV_INFO]`, `[PERM_OWNER]`, `[DEV_BUILD]`, `[IPC_COMM]`
5.  **"One Verb, One Tool" Taxonomy:** We enforce a strict rule where the primary verb cannot be reused within a namespace. (If `join` uses "merge", `comm` must use "compare").

## 4. Edge Cases & Risks
*   **The Rebellious Agent (Hallucination):** The LLM reads `pax` in Tier 1, but ignores Tier 2 and confidently guesses the syntax (e.g., `pax -z`).
    *   *Mitigation:* Prompt coercion is weak. The long-term mitigation is intercepting the shell execution layer: if the agent runs a tool listed in Tier 1 without calling `get_posix_syntax` first, the system returns a structured error forcing the step-up.
*   **The `cat` Trap (Context Starvation):** If a local file like `posix-tldr.json` is exposed to the shell, the agent might just run `cat` on it, flooding its context window and defeating the architecture.
    *   *Mitigation:* Do not expose the raw reference file to the agent's shell environment. Wrap it entirely behind the `get_posix_syntax` tool primitive.
*   **Complex Pipelines:** Tasks requiring three tools (e.g., `sort | uniq | comm`) trigger latency spikes if looked up sequentially.
    *   *Mitigation:* The `get_posix_syntax` tool must accept an array of strings (e.g., `["sort", "uniq", "comm"]`) to batch pipeline lookups into a single call.

### Research Insights
**Edge Case Handling:**
- **The Non-POSIX Parsing Trap:** If we require the agent to parse JSON using CLI tools in a strict POSIX environment, it will fail because tools like `jq` are NOT POSIX utilities. This necessitates the shift to native agent tools.

## 5. Implementation Steps & Acceptance Criteria (Definition of Done)

### Step 1: Deliver Tier 1 Skill
*   **Task:** Create `posix-core.md`.
*   **Acceptance Criteria:**
    *   [ ] File exists, contains all 155 POSIX Issue 8 utilities, grouped by the 8 Categorical Namespaces.
    *   [ ] Total file size is under 1,000 tokens.
    *   [ ] Trivial commands (`cd`, `ls`) are grouped without descriptions.
    *   [ ] Non-trivial commands have a 2-5 word description following the Disambiguation & One-Verb methodologies.

### Step 2: Deliver Tier 2 Reference & Tool
*   **Task:** Create the data store and the `get_posix_syntax` tool interface.
*   **Acceptance Criteria:**
    *   [ ] Data store covers at least the ~30 highest-value utilities tested in `benchmark_data.json`.
    *   [ ] Tool successfully accepts an array of utility names and returns pure-POSIX syntax strings.

### Step 3: Wire the Test Harness
*   **Task:** Update `run_benchmark.py` to support testing the architecture.
*   **Acceptance Criteria:**
    *   [ ] Script accepts an `--inject-posix` argument to prepend `posix-core.md` to the prompt.
    *   [ ] The framework exposes the `get_posix_syntax` dummy tool to the LLM during the run.

### Step 4: Validate via Behavioral A/B Testing
*   **Task:** Run the benchmark and prove the *Step-Up* behavior works, not just the token count.
*   **Acceptance Criteria:**
    *   [ ] **Tier 1 Success (The Intercept):** Zero agentic detours into Python/Bash scripting.
    *   [ ] **Tier 2 Success (The Lookup):** The `execution.tool_calls_by_type` metrics must mathematically prove the agent executed `get_posix_syntax` before answering.
    *   [ ] **Final Success:** The `trap_hits` metric drops to 0, and the `minimal_answer_gap_words` metric closes.
