# Architecture: The POSIX Step-Up System

## What Problem This Solves

When you ask an LLM to do a CLI task, it typically does one of three bad things:

1. **Reaches for Python or Bash scripting** — burning hundreds of tokens writing code for something a single POSIX command handles in two words.
2. **Uses a GNU extension** — flags like `sed -i`, `grep -r`, or `find -mmin` that break on non-GNU systems.
3. **Ignores a native utility entirely** — using `tar` when `pax` is the correct POSIX archiver, or `md5sum` when `cksum` is the spec-compliant tool.

The root cause is not that the LLM "can't do it" — it's that it doesn't know the tool exists or doesn't trust itself to know the exact syntax. The Step-Up architecture fixes this by giving the LLM progressively more specific information, on demand, in the cheapest way possible.

---

## The Two Tiers

### Tier 1 — The Semantic Map (`posix-core.md`)

A single file injected into the agent's context at the start of every session. It lists all 155 POSIX Issue 8 utilities with a 2–5 word hook that tells the agent what the tool *does* and, crucially, what it is *not*.

Example entries:
```
pax: portable archive (NOT tar)
od: dump bytes as hex/octal
cksum: file integrity checksum (NOT md5sum)
comm: compare two sorted lists
```

This file is capped at ~800 tokens. Its only job is to make sure the agent knows the tool exists so it doesn't reach for a non-POSIX substitute. It does not contain full syntax.

### Tier 2 — The Syntax Lookup Tool (`get_posix_syntax`)

An agent-native tool the LLM can call before executing a Tier 1 utility. It accepts one or more utility names and returns the exact, pure-POSIX syntax strings — no GNU extensions, no BSD variants.

The agent is instructed to always call this tool before using any utility it found in Tier 1. This prevents the "Rebellious Agent" failure mode: the LLM sees `pax` in Tier 1, decides it already knows the syntax, and confidently writes `pax -z` (which doesn't exist).

The tool is backed by `posix-tldr.json`, a local structured file. The LLM never reads that file directly — it always goes through the tool interface, which prevents token flooding from a naive `cat posix-tldr.json`.

---

## How the Tiers Work Together

```
User prompt
    |
    v
[Tier 1] Does posix-core.md tell me a native tool exists for this?
    |-- YES --> Call get_posix_syntax(tool_name)
    |               |
    |           [Tier 2] Returns exact POSIX syntax
    |               |-- Use it, answer the question
    |
    |-- NO --> Use general knowledge (expected to be rare)
```

---

## Key Design Decisions

**Why a tool instead of a file?**  
If we expose `posix-tldr.json` directly to the shell, the agent will run `cat posix-tldr.json`, flooding its context with thousands of tokens. Wrapping it behind a tool forces single-utility lookups.

**Why not just inject the full POSIX man pages?**  
Context tax. A single `sed` man page is ~4,000 tokens. Injecting all 155 would consume the entire context window before the user's question is even answered.

**Why not rely on ALL CAPS warnings like "DO NOT GUESS SYNTAX"?**  
Prompt instructions are fragile. A confident LLM will ignore them. Structural enforcement — requiring a tool call before a shell call — is far more reliable than text warnings.

**Why is Tier 1 grouped by namespace?**  
The LLM processes the list hierarchically. Grouping under `[TEXT_DATA_PROC]`, `[FILE_DIR_OPS]`, etc. reduces the search space for intent-matching and prevents the LLM from pattern-matching on the wrong utility.

---

## The "One Verb, One Tool" Rule

Within each namespace, no two tools can share the same primary verb. If `join` uses "merge", `comm` must use "compare". This prevents semantic collisions where the LLM picks the wrong tool because the verb matched.

---

## What This Architecture Does NOT Do

- It does not guarantee POSIX compliance — it makes it dramatically more likely.
- It does not replace reading the spec for novel edge cases.
- It does not work if the agent bypasses the tool system entirely (e.g., answers from training data alone). The benchmark tracks tool call metrics specifically to detect this.

---

## Observed Results

Benchmark runs across Claude, Codex, and Gemini confirm the architecture works:

| Provider | Track 1 Compliance | Track 2 Compliance | Output Tokens T1 | Output Tokens T2 |
|----------|-------------------|--------------------|------------------|------------------|
| Claude | 63.3% | 76.7% | 228 | 374 |
| Codex | 58.6% | 86.7% | 930 | 1,289 |
| Gemini | 65.4% | 86.7% | 215 | 105 |

Notable: Gemini's output tokens dropped by more than half in Track 2 — the Step-Up architecture led it to answer more directly. Codex compliance improved the most (+28pp) but its agentic style means output tokens increased; `tool_heavy_detour` was its dominant Track 2 failure mode (25/30 questions).
