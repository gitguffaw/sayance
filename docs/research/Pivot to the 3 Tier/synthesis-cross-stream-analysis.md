# Cross-Stream Synthesis: POSIX Semantic Bridge

**Date:** 2026-04-04
**Purpose:** Reconcile two independent research streams into a unified architecture

---

## The Two Streams

**Stream A (Jerome's prior research):** Three documents totaling ~25K words. Empirically grounded in ToolLLM, Gorilla, Lost-in-the-Middle, LLMLingua, and other cited work. Proposes a ~800 token semantic map with [BRACKET_CAPS] headers, an MCP-based `get_posix_syntax` tool with structural enforcement layers, and a statistical benchmark framework with TES composite metric.

**Stream B (Claude's architecture doc):** ~10K words. Proposes a three-tier skill file (behavioral directive + intent map + composition patterns) at 1,200-1,800 tokens, a companion binary (`posix-ref`) in Go/Rust, and an A/B eval framework with 4 task categories.

---

## Where the Streams Agree

These points are settled. No further debate needed.

1. **Intent-first organization** beats command-first. Both streams group by what users want to do.
2. **~48 bridge candidates** is the right scope after the POSIX.1-2024 audit. Covering all 155 wastes tokens on commands LLMs already retrieve.
3. **A/B design** (with bridge vs. without) is the correct eval structure.
4. **Cross-model testing** (Claude, GPT, Gemini/Llama) is required; the bridge must be model-agnostic.
5. **Batch lookups** for pipelines (one call returning multiple commands) beat sequential calls.
6. **The "obvious" cutoff must be empirical**, not assumed. Run bare-LLM discovery tasks, exclude commands retrieved >80%.

---

## Critical Tensions and Resolutions

### 1. Token Budget: ~800 vs. 1,200-1,800

**Stream A says 800.** Validated by needle-in-haystack studies as the "perfect retrieval zone." Sub-1K context shows near-perfect retrieval across all major models with under 5% positional degradation.

**Stream B says 1,200-1,800.** Includes a behavioral directive (150 tokens) and composition patterns (300 tokens) that Stream A doesn't have.

**Resolution:** Stream A's 800-token budget is the right constraint for Tier 2 (the intent map). Stream B's Tier 1 (behavioral directive, ~150 tokens) and Tier 3 (composition idioms, ~100 tokens streamlined) are additive layers worth their cost. Total: **~1,050 tokens**, splitting the difference. The behavioral directive is high-ROI per token (changes the LLM's prior toward POSIX). Composition idioms teach multi-command patterns at ~25 tokens each.

**Decision:** ~1,050 tokens. Tier 1 (150) + Tier 2 (800) + Tier 3 (100).

---

### 2. Format: [BRACKET_CAPS] + Verb-Forward vs. Markdown + Trigger Phrases

**Stream A's format:**
```
[COMPARING_MERGING]
comm: compare sorted files, lines unique per file (NOT diff)
paste: merge columns side-by-side
join: relational join on shared key (like SQL JOIN)
```

**Stream B's format:**
```
**Comparing & Merging Files**
- Lines unique to file A vs. B → comm
- Merge columns side by side → paste
- Relational join on shared field → join
```

**Stream A's research advantage:** [BRACKET_CAPS] headers trigger "structured data scanning mode" in code-trained LLMs (Clark et al., ToolLLM). 15-30% higher selection accuracy over flat lists. The `tool: description` format mirrors YAML, which is heavily represented in all training corpora.

**Stream B's efficiency advantage:** Trigger phrases ("goal → command") are ~30% more token-efficient per entry. Intent-first phrasing matches how users think.

**Resolution: Hybrid.** Use [BRACKET_CAPS] headers (Stream A's proven structural format) with trigger-phrase entries (Stream B's token efficiency). Drop the bullet prefix to save tokens (Stream A's own research recommends this).

```
[COMPARING_MERGING]
lines unique to file A vs B, set difference/intersection → comm
merge columns from files side by side → paste
relational join on shared field (like SQL JOIN) → join
```

**Decision:** [BRACKET_CAPS] headers + trigger phrases without bullet prefixes.

---

### 3. Negation Patterns

**Stream A:** Validated. `pax: portable archive (NOT tar)` works because positive description comes first. Limit to 8-12 negations. Use `(IS POSIX)` for Issue 8 additions (safer; no ironic process risk). Research-backed by Gorilla, Tang et al.

**Stream B:** Listed as open question.

**Resolution:** Adopt Stream A's findings wholesale. This is settled science within the cited research.

**Decision:** 6-8 negations max (density-adjusted from the original 8-12/155 to ~48-entry scope), positive-first framing, `(IS POSIX)` for Issue 8 commands.

---

### 4. The Tool: MCP Server vs. CLI Binary

**Stream A:** MCP tool (`get_posix_syntax`) with structural enforcement. Returns compact JSON. Addresses the "Rebellious Agent" problem with 4 enforcement layers. Cross-provider tool_choice forcing.

**Stream B:** CLI binary (`posix-ref`) in Go/Rust. Zero dependencies, offline-capable, sub-50ms. Returns human-readable text. No enforcement mechanism.

**Critical gap in Stream B:** No answer to the Rebellious Agent problem. The LLM reads `comm` in the skill file, skips the binary, and confidently writes `comm -z` (which doesn't exist).

**Critical gap in Stream A:** MCP server requires a runtime, network protocol overhead, and provider-specific integration. Not portable to LLMs that don't support MCP.

**Resolution: The binary IS the MCP server.** One Go/Rust artifact that serves two interfaces:

1. **CLI mode** (`posix-ref comm`): For any LLM with shell access. Human-readable output. Zero-dependency portability.
2. **MCP mode** (`posix-ref --mcp`): Starts an MCP server exposing `get_posix_syntax` and (optionally) `search_posix_spec`. Returns structured JSON. Enables enforcement layers.

Both modes read from the same embedded data file. One codebase, two interfaces, no duplication. The MCP mode gets Stream A's enforcement layers (instructions field, rich errors, shell interception). The CLI mode gets Stream B's portability.

**Decision:** Single binary, dual interface (CLI + MCP). Build CLI mode first (Phase 1), add MCP mode second (Phase 2).

---

### 5. Enforcement Against the "Rebellious Agent"

**Stream A proposes 4 layers:**
1. MCP `instructions` field (weakest, always-on)
2. Rich error results ("xxd is NOT POSIX, use od")
3. Shell interception middleware (strongest: blocks un-looked-up commands)
4. Provider-level `tool_choice` forcing

**Stream B proposes nothing.**

**Resolution:** Stream A's layered enforcement is correct. For the CLI-only mode (no MCP), the skill file itself can include a behavioral directive: "Before executing any POSIX utility listed below, call `posix-ref <command>` to verify syntax." This is weaker than structural enforcement but better than nothing.

For the MCP mode, implement layers 1-3. Layer 4 (tool_choice forcing) is a deployment-time decision that depends on the host framework.

**Decision:** Adopt Stream A's enforcement architecture. Layer 1-2 in Phase 1, Layer 3 in Phase 2.

---

### 6. Eval Methodology

**Stream A's strengths:**
- TES composite metric (accuracy × conciseness)
- Rigorous statistics (Wilcoxon, Mann-Whitney, bootstrap CI, Cohen's d)
- Cache management protocol (cold/warm separation, 10min cooling)
- Failure mode taxonomy (5 categories explaining WHY the LLM failed)
- Pre-registration of hypotheses (H1-H4)
- k=5 runs minimum with CV monitoring

**Stream B's strengths:**
- 4 task categories (discovery, composition, preference, distractor)
- 3 specificity levels per command (high/medium/low naturalness)
- Functional equivalence testing (execution + LLM judge)
- Ablation studies (test each tier independently)
- Distractor tasks (POSIX is wrong answer; tests precision)

**Resolution: Merge.** Use Stream B's task architecture with Stream A's statistical framework.

**Unified scoring (8-point rubric):**

| Dimension | Points | Source |
|-----------|--------|--------|
| Command Selection | 0-2 | Stream B |
| Pipeline Correctness | 0-2 | Stream B |
| POSIX Preference | 0-1 | Stream B |
| Functional Equivalence | 0-1 | Stream B |
| Verbosity Efficiency | 0-2 | Stream A (adapted from TES) |
| Failure Mode Code | (tag, not scored) | Stream A |
| **Total** | **0-8** | |

Verbosity Efficiency replaces a simple binary: 2 = minimal answer (within 20% of reference token count), 1 = moderate verbosity (20-200%), 0 = excessive (>200%).

Every response also gets tagged with a failure mode code from Stream A's taxonomy: `correct`, `non_posix_substitution`, `workaround_instead_of_native`, `over_explaining`, `tool_heavy_detour`, `issue8_stale_knowledge`.

**Statistical framework:** Adopt Stream A wholesale. Wilcoxon signed-rank for paired A/B, bootstrap CI at 95%, Cohen's d for effect size, k=5 runs minimum, CV monitoring, cache cold/warm separation.

**Pre-register:**
- H1: Bridge reduces `non_posix_substitution` failures by ≥50%
- H2: Bridge improves command selection score by ≥30% on discovery tasks
- H3: Bridge does not degrade distractor task precision
- H4: Bridge achieves ≥80% POSIX compliance across all 3 models

**Decision:** Stream B's 4-category task design + Stream A's statistical rigor + unified 8-point rubric + pre-registered hypotheses.

---

## The Merged Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    SKILL FILE (~1,050 tokens)            │
│                                                         │
│  Tier 1: Behavioral Directive              (~150 tokens) │
│  Tier 2: Intent Map in [BRACKET_CAPS]      (~800 tokens) │
│  Tier 3: Composition Idioms (4-6 examples) (~100 tokens) │
│                                                         │
│  Format: [BRACKET_CAPS] headers                         │
│          trigger phrase → command                        │
│          6-8 negations (NOT x), (IS POSIX)              │
│          ~48 bridge candidates (Issue 8 audited)        │
│          ASCII only, no bullet prefixes                 │
└──────────────────────┬──────────────────────────────────┘
                       │
                       │ LLM identifies candidate command
                       │
┌──────────────────────▼──────────────────────────────────┐
│              COMPANION BINARY (single artifact)          │
│                                                         │
│  CLI mode:  posix-ref comm                              │
│             posix-ref comm --task "lines only in A"     │
│             posix-ref --suggest "merge columns"         │
│                                                         │
│  MCP mode:  posix-ref --mcp                             │
│             Exposes get_posix_syntax tool                │
│             Enforcement: instructions + rich errors      │
│                         + shell interception (Phase 2)  │
│                                                         │
│  Implementation: Go or Rust, <2MB, zero deps            │
│  Data: embedded JSON, ~155 POSIX.1-2024 commands        │
│  Output: JSON (MCP) or human-readable (CLI)             │
└─────────────────────────────────────────────────────────┘
```

---

## What's Genuinely New (Not in Either Stream)

1. **The binary-as-MCP-server pattern.** Neither stream proposed this. It eliminates the portability vs. enforcement tradeoff entirely.

2. **Unified 9-point rubric with failure mode tagging.** Stream A had TES, Stream B had a 6-point rubric. The merged 9-point rubric plus failure mode codes captures accuracy, correctness, preference, equivalence, AND verbosity in one framework.

3. **Tier budget allocation.** Neither stream computed the optimal token split across tiers. The 150/800/100 allocation gives the behavioral directive and composition patterns just enough budget without exceeding Stream A's validated retrieval zone.

4. **The hybrid format.** [BRACKET_CAPS] structural headers (Stream A's research) combined with trigger-phrase entries (Stream B's efficiency) is not something either stream proposed. It takes the best format choice from each.

---

## Implementation Sequence

| Phase | Deliverable | Effort | Dependencies |
|-------|------------|--------|--------------|
| 1 | Skill file v1 (merged format, ~1,050 tokens, 10 commands) | 2 days | None |
| 2 | 30 eval tasks (discovery + composition + distractor) | 2 days | None |
| 3 | Bare-LLM baseline (no bridge, 3 models, k=3) | 1 day | Phase 2 |
| 4 | Determine empirical "obvious" cutoff per model | 1 day | Phase 3 |
| 5 | Skill file v2 (full ~48 commands, tuned cutoff) | 2 days | Phase 4 |
| 6 | Binary v1: CLI mode, 48 commands, posix-ref <cmd> | 1 week | Phase 1 data |
| 7 | Full eval: A/B, 3 models, k=5, statistical analysis | 3 days | Phases 5-6 |
| 8 | Binary v2: MCP mode + enforcement layers | 1 week | Phase 6 |
| 9 | Ablation studies (per-tier contribution) | 2 days | Phase 7 |

---

## Sources

### Stream A (Jerome's Research)
- Liu et al., "Lost in the Middle" (2023)
- Patil et al., "Gorilla: LLM Connected with Massive APIs" (2023)
- Qin et al., "ToolLLM" (2023)
- Schick et al., "Toolformer" (2023)
- Jiang et al., "LLMLingua" (2023)
- Tang et al., "ToolAlpaca" (2024)
- Shi et al., "LLMs Can Be Easily Distracted" (2023)
- Sui et al., "Table Meets LLM" (2024)
- Anthropic tool_use docs, OpenAI function-calling docs, Google tool declarations docs
- MCP tool-design.md, agent-native-architecture skill, dynamic-context-injection.md

### Stream B (Claude's Research)
- NL2SH: LLM-Supported NL to Bash Translation (NAACL 2025)
- IEEE Std 1003.1-2024 (POSIX Issue 8)
- ShellCheck PR #3307 (Issue 8 command delta)
- ToolSandbox (Apple ML Research)
- Artificial Analysis methodology
- HELM (Stanford CRFM)
- AlpacaEval 2.0 (length-controlled)
