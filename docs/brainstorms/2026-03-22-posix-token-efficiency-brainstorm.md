---
topic: POSIX Token Efficiency for LLMs
date: 2026-03-22
status: complete
---

# POSIX Token Efficiency for LLMs

## What We're Building

A benchmark and measurement tool that quantifies how many tokens LLMs actually burn when working with POSIX shell commands. The goal is to determine whether a hyper-efficient POSIX command reference is worth building — and what the token savings would be.

## Why This Matters

- LLMs don't "look up" POSIX commands — they generate from training data
- When wrong, users burn tokens on retries, debugging, back-and-forth
- When documentation is injected (RAG, system prompts), it's expensive: man pages cost 3,000-8,000 tokens per command
- No one has measured the actual token cost of POSIX command usage across LLMs
- The POSIX spec defines exactly **155 utilities** (POSIX.1-2024 / Issue 8) (commonly miscounted as 243)

## Key Decisions

1. **Measure token cost first, accuracy second.** The original benchmark measured only accuracy — but the core question is token efficiency. Accuracy feeds into "waste cost" (tokens burned on wrong answers), but input cost is the other half.

2. **Use CLI JSON output for measurement.** All three target CLIs (Claude, Gemini, Codex) report token usage in JSON output mode:
   - Claude: `--output-format json` → `usage.input_tokens`, `usage.output_tokens`, `cache_creation_input_tokens`
   - Gemini: `-o json` → `stats.models.*.tokens.input`, `.prompt`, `.candidates`, `.cached`, `.thoughts`
   - Codex: `--json` → JSONL with `turn.completed` → `usage.input_tokens`, `usage.output_tokens`, `cached_input_tokens`

3. **Baseline-then-delta approach.** Measure baseline context cost (just "hello"), then per-POSIX-question cost, calculate the delta. This isolates the POSIX-specific token consumption from system prompt overhead.

4. **Three LLMs tested.** Claude, Gemini, Codex — all via CLI.

## What "Token Efficiency" Means

- **Input cost:** Tokens to give the LLM enough info to get it right
- **Waste cost:** Tokens burned on wrong answers, retries, corrections
- **Total cost** = input + waste
- Target: if a compact POSIX spec could fit all 155 commands in ~8,000-16,000 tokens (vs 500k for man pages), that's 30x improvement

## Existing Landscape

| Project | Tokens/cmd | LLM-optimized? | Actionable? |
|---------|-----------|----------------|-------------|
| tldr-pages (61.8k stars) | ~150 | No | No — example-only, no flag semantics |
| man pages | ~3,000-8,000 | No | Yes — but prohibitively expensive |
| POSIX spec (HTML) | ~3,000-10,000 | No | Unparseable |
| Hypothetical compact spec | ~50-100 | Yes | TBD |

## Open Questions

- ~~How to measure tokens?~~ → Resolved: CLI JSON output modes
- What's the actual per-command token delta? → Benchmark will answer
- Can a compact spec (~50-100 tokens/cmd) still produce correct answers? → Needs prototype testing after benchmark

## Approach: Scrappy Then Scale

1. Build token-measuring benchmark (immediate next step)
2. Run across all 155 POSIX utilities on 3 LLMs
3. Analyze results to determine if project is worth building
4. If yes, prototype compressed command specs and compare token cost with/without
