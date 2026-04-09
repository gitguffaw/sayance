# POSIX Semantic Bridge

A lightweight skill file (~1,050 tokens) + companion binary that helps LLMs discover and correctly use POSIX CLI commands from the POSIX.1-2024 (Issue 8) spec.

## Start Here

Three canonical documents define the current state of the project:

1. **[synthesis-cross-stream-analysis.md](synthesis-cross-stream-analysis.md)** -- The architecture. Merged decisions from two independent research streams. Covers: token budget (1,050), format ([BRACKET_CAPS] + trigger phrases), binary-as-MCP-server pattern, unified 8-point eval rubric, enforcement layers, implementation sequence.

2. **[posix-skill-file-construction-guide.md](posix-skill-file-construction-guide.md)** -- The build spec. Line-by-line rules for constructing the actual skill file: tier budgets, format rules, trigger phrase writing, qualifier annotations, schema priming, namespace ordering, validation checklist. Every claim is tagged as Cited, Inferred, or Speculative with specific paper references.

3. **[posix-command-audit.md](posix-command-audit.md)** -- The command list. All ~155 POSIX.1-2024 utilities categorized by disposition (skip/bridge/obvious). ~48 bridge candidates identified across 8 categories.

## research/

The `research/` folder contains the source documents that informed the canonical docs. They are the audit trail, not the working spec. Some conclusions in these documents have been superseded by the synthesis and construction guide.

| Document | Date | Key contribution | Superseded by |
|----------|------|-----------------|---------------|
| semantic-compression-for-llms.md | 2026-03-29 | Empirical basis for format decisions: needle-in-haystack, LLMLingua, Gorilla, Lost-in-the-Middle, Clark et al. | Construction guide (entry format changed from command-first to trigger-first; bullets dropped) |
| agent-native-tool-design-best-practices.md | 2026-03-29 | MCP tool design: schema patterns, enforcement layers, Rebellious Agent problem, batch lookups | Synthesis (binary-as-MCP-server replaces pure MCP approach) |
| llm-benchmark-methodology.md | 2026-03-29 | Statistical framework: Wilcoxon, bootstrap CI, Cohen's d, TES metric, cache protocol, failure taxonomy | Synthesis (TES absorbed into unified 8-point rubric) |
| posix-semantic-bridge-architecture.md | 2026-04-04 | Three-tier design, companion binary, intent clusters, eval task categories, command audit | Synthesis + construction guide (token budget, format, enforcement all revised) |

## What Has Not Been Built Yet

- The actual skill file (posix-core.md)
- The companion binary (posix-ref)
- The eval harness and task set
- Bare-LLM baseline measurements

## Implementation Sequence

Per the synthesis doc, Phase 1 is: skill file v1 with ~10 bridge commands in the merged format + 30 eval tasks. See synthesis-cross-stream-analysis.md "Implementation Sequence" for the full 9-phase plan.
