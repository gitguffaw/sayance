# Architecture: The POSIX Step-Up System

## What Problem This Solves

When you ask an LLM to do a CLI task, it typically does one of three bad things:

1. **Reaches for Python or Bash scripting** — burning hundreds of tokens writing code for something a single POSIX command handles in two words.
2. **Uses a GNU extension** — flags like `sed -i`, `grep -r`, or `find -mmin` that break on non-GNU systems.
3. **Ignores a native utility entirely** — using `tar` when `pax` is the correct POSIX archiver, or `md5sum` when `cksum` is the spec-compliant tool.

The root cause is not that the LLM "can't do it" — it's that it doesn't know the tool exists or doesn't trust itself to know the exact syntax. The Step-Up architecture fixes this by giving the LLM progressively more specific information, on demand, in the cheapest way possible.

---

## The Two Layers

### The Discovery Map (`posix-core.md`)

A single file injected into the agent's context at the start of every session. It lists all 142 macOS-available POSIX Issue 8 utilities with a 2–5 word hook that tells the agent what the tool *does* and, crucially, what it is *not*.

Example entries:
```
pax: portable archive (NOT tar)
od: dump bytes as hex/octal
cksum: file integrity checksum (NOT md5sum)
comm: compare two sorted lists
```

This file is capped at ~800 tokens. Its only job is to make sure the agent knows the tool exists so it doesn't reach for a non-POSIX substitute. It does not contain full syntax.

### The Syntax Lookup CLI (`posix-lookup`)

An executable Python 3 CLI the LLM calls via bash before executing a utility from the Discovery Map. It accepts a utility name and returns the exact, pure-POSIX syntax strings — no GNU extensions, no BSD variants.

```bash
$ posix-lookup pax
  Create portable archive: pax -w -f archive.pax directory/
  Copy directory tree: pax -rw src/ dest/
  DO NOT USE tar (not guaranteed POSIX).
```

The agent is instructed to always call `posix-lookup <utility>` before using any utility it found in the Discovery Map. This prevents the "Rebellious Agent" failure mode: the LLM sees `pax` in the Discovery Map, decides it already knows the syntax, and confidently writes `pax -z` (which doesn't exist).

The CLI is backed by `posix-tldr.json`, a local structured file. The LLM never reads that file directly — it always goes through the CLI, which prevents token flooding from a naive `cat posix-tldr.json`.

**Why a CLI instead of an MCP tool?** The LLM's bash tool is always registered in its schema — zero additional context tokens. An MCP tool would add ~79-120 tokens of schema overhead per session for a capability bash already provides. The CLI also works in any agent environment with shell access, not just MCP-compatible clients.

---

## How the Layers Work Together

```
User prompt
    |
    v
[Discovery Map] Does posix-core.md tell me a native tool exists for this?
    |-- YES --> Run: posix-lookup <utility>
    |               |
    |           [Syntax Lookup] Returns exact POSIX syntax via bash
    |               |-- Use it, answer the question
    |
    |-- NO --> Use general knowledge (expected to be rare)
```

---

## Key Design Decisions

**Why an executable CLI instead of an MCP server?**  
The LLM's bash tool is always registered in its schema — zero additional context tokens. An MCP tool would add ~79-120 tokens of permanent schema overhead. The CLI also works in any agent environment with shell access (Claude Code, Cursor, Codex, Gemini CLI), not just MCP-compatible clients. MCP remains a future option if multi-client structured tool access becomes a priority.

**Why a CLI instead of a raw file?**  
If we expose `posix-tldr.json` directly to the shell, the agent will run `cat posix-tldr.json`, flooding its context with thousands of tokens. Wrapping it behind a CLI forces single-utility lookups.

**Why not just inject the full POSIX man pages?**  
Context tax. A single `sed` man page is ~4,000 tokens. Injecting even our 142 macOS-available utilities as man pages would consume the entire context window before the user's question is even answered.

**Why not rely on ALL CAPS warnings like "DO NOT GUESS SYNTAX"?**  
Prompt instructions are fragile. A confident LLM will ignore them. Structural enforcement — requiring a CLI call before a shell call — is far more reliable than text warnings.

**Why is the Discovery Map grouped by namespace?**  
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

| Provider | Unaided Compliance | Bridge-Aided Compliance | Output Tokens Unaided | Output Tokens Bridge-Aided |
|----------|-------------------|--------------------|------------------|------------------|
| Claude | 63.3% | 76.7% | 228 | 374 |
| Codex | 58.6% | 86.7% | 930 | 1,289 |
| Gemini | 65.4% | 86.7% | 215 | 105 |

Unaided and Bridge-Aided prove that injection improves compliance. What they do not yet prove is the real-world token cost difference — because in both modes the model never actually executes anything. In a real environment, an Unaided model that reaches for the wrong tool will retry, debug, and potentially write its own script, burning orders of magnitude more tokens. A Bridge-Aided model that reaches the correct command on the first attempt incurs none of that retry cost. Command Verification will measure this delta. The working hypothesis is that Bridge-Aided's real-world total cost is substantially lower than Unaided's, even accounting for the injection overhead.
