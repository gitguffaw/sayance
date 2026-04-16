# POSIX Skill File Construction Guide

How to build the ~1,050-token SKILL.md file, line by line.

---

## File Structure

The file has exactly three sections, in this order. No frontmatter, no preamble, no trailing commentary.

```
DISCOVERY MAP:  Behavioral Directive         ~150 tokens
SYNTAX LOOKUP:  Intent-to-Command Map        ~800 tokens
SPEC SEARCH:    Composition Idioms           ~100 tokens
```

Total budget: 1,050 tokens. Hard ceiling: 2,000. Needle-in-haystack studies (Anthropic, 2024; Google, 2024) show near-perfect retrieval for context under 2K tokens across all major models. The 1,050 target keeps the Syntax Lookup layer in the sub-1K "perfect retrieval" zone (<5% positional degradation) while leaving headroom for other system prompt content sharing the context window.

---

## Discovery Map: Behavioral Directive

**Budget:** 150 tokens (roughly 3-5 sentences)
**Purpose:** Shift the LLM's default from "write a Python script" to "reach for a POSIX command"
**Why it works:** LLMs are instruction-followers. A direct behavioral nudge changes the prior probability of selecting POSIX commands before the LLM even reads the intent map. Without this, the map is a reference the LLM may browse past. [Speculative: no direct citation for "behavioral directive increases map utilization." Inferred from Anthropic's tool-use documentation showing system prompt instructions bias tool selection, and from the general instruction-following literature (Wei et al., 2023).]

**What to include:**
1. A clear instruction to prefer POSIX commands over scripting languages for file/text/process tasks
2. The reason (no dependencies, already installed, compose via pipes)
3. An explicit boundary for when scripting IS appropriate (data structures, network calls, logic pipes can't express)
4. A directive to call `posix-ref` before executing any command listed below (if the companion binary is deployed)

**What to avoid:**
- Do not list specific commands here. That is the Syntax Lookup layer's job.
- Do not use imperative negation ("NEVER use Python"). Use conditional framing ("Reach for Python/Node only when...") [Inferred from Tang et al. (2024) and Wegner ironic process: imperative negation activates the negated token. Parenthetical/conditional framing avoids this. See Q6 in semantic-compression-for-llms.md.]
- Do not explain what POSIX is. The LLM knows.

**Format rules:**
- Plain prose. No headers, no bullets, no structural markup.
- This section is intentionally different from the Syntax Lookup layer's structured format. The prose-to-structure transition signals to the LLM that the mode is shifting from "behavioral instruction" to "reference lookup." [Cited as "Anthropic system prompt research" in the synthesis doc, but no specific paper. Speculative: inferred from Clark et al. (2019) showing attention heads specialize by structural mode, and from the observation that format shifts reset parsing expectations.]

---

## Syntax Lookup: Intent-to-Command Map

**Budget:** 800 tokens (roughly 48 entries across 6-8 namespaces)
**Purpose:** When a user describes a task, the LLM scans this section and finds the right POSIX command. This is the core of the bridge.

### Namespace Headers

Use `[BRACKET_CAPS]` format. Not markdown headers. Not title case.

```
[COMPARING_MERGING]        YES
[TEXT_DATA_PROC]           YES
## Comparing & Merging     NO - triggers "document reading" mode
**Comparing & Merging**    NO - markdown bold is not a structural marker
```

**Why brackets:** LLMs trained on code parse `[ALL_CAPS]` as INI/config section headers. This activates structural attention heads (Clark et al., "What Does BERT Look At?", 2019) that narrow the search space before semantic matching begins. ToolLLM (Qin et al., 2023) measured 15-30% higher selection accuracy with categorical headers vs. flat lists. [The specific claim that brackets trigger "structured data scanning" vs. markdown's "document reading" is an inference from Clark et al.'s attention head specialization findings applied to decoder-only models. Speculative extrapolation; not directly tested on bracket format vs. markdown headers.]

**Namespace count:** 6-8. Not fewer than 5 (groups too large, losing the narrowing benefit). Not more than 10 (too many headers burn tokens and create processing overhead). 8 is the validated sweet spot. [Miller's "Magical Number Seven, Plus or Minus Two" (1956) established 5-9 as the human chunking optimum. ToolLLM (Qin et al., 2023) showed the same range maximizes LLM discrimination across tool categories. The phrase "confirmed in LLM testing" in earlier drafts referred to ToolLLM's results, not a separate LLM-specific replication of Miller.]

**Namespace ordering:** Highest-traffic first, lowest-traffic last. Primacy effect is slightly stronger than recency for factual retrieval (Liu et al., "Lost in the Middle: How Language Models Use Long Contexts", 2023). Each header partially resets positional attention, so the lost-in-the-middle effect is minimal at this file size, but still optimize. [The "headers reset position counter" claim is from semantic-compression-for-llms.md Q7; it is inferred from the observation that section headers create sub-contexts, not from a direct measurement in Liu et al. Speculative but mechanistically plausible.]

Recommended order (adjust after eval data):
1. `[TEXT_PROCESSING]` (most common user queries)
2. `[COMPARING_MERGING]`
3. `[SPLITTING_RESTRUCTURING]`
4. `[ENCODING_CHARACTERS]`
5. `[COMPUTATION_LOGIC]`
6. `[PROCESS_JOB_CONTROL]`
7. `[FILE_SYSTEM_INFO]`
8. `[BINARY_INSPECTION]` (least common)

### Entry Format

Each entry is one line. The format is:

```
trigger phrase describing user goal -> command_name
```

Use ASCII `->` not the Unicode arrow `→`. Cross-model reliability: Claude and GPT handle Unicode reliably; Gemini is less consistent in structured contexts. ASCII is the safe default. [Practical finding from cross-model testing documented in semantic-compression-for-llms.md Q8. No formal paper; based on observed behavior across Claude, GPT-4, and Gemini.]

**Do not use bullet prefixes.** No `*`, no `-`, no numbers. The namespace header provides sufficient structure. Dropping bullets saves ~2 tokens per entry, ~96 tokens across 48 entries. Sui et al., "Table Meets LLM: Can Large Language Models Understand Structured Table Data?" (2024) confirms that for lookup/retrieval tasks, bullet lists match table accuracy at 30-40% fewer tokens; under categorical headers, the bullets themselves add tokens without improving retrieval accuracy.

**Do not put the command name first.** The entry is a semantic bridge FROM the user's language TO the command. The user's language comes first. [Speculative: no direct A/B study comparing command-first vs. trigger-first entry order for LLM retrieval. Inferred from Schick et al. (Toolformer, 2023) showing verb-forward descriptions improve selection, and from the design principle that the bridge should match user query vocabulary, not man-page vocabulary.]

```
lines unique to file A vs B, set difference -> comm       YES
comm: compare sorted files, find unique lines             NO (command-first)
```

### Writing Trigger Phrases

Each trigger phrase is 2-5 words describing what the user wants to DO. This is the most important part of the entire file. Every word must earn its place.

**Rules:**

1. **Verb-forward.** Start with the action: "merge," "split," "convert," "wrap," "number." Schick et al., "Toolformer: Language Models Can Teach Themselves to Use Tools" (2023, Meta) showed verb-forward tool descriptions yield higher selection accuracy. Anthropic's tool-use documentation corroborates: LLMs parse tool descriptions with a bias toward matching user intent verbs to tool description verbs (semantic-compression-for-llms.md Q1).

2. **User vocabulary, not man-page vocabulary.** Write the phrase a user would type, not the phrase a man page would use. "merge columns side by side" not "concatenate corresponding lines." Run the Intent Extraction test: if you asked 5 people to describe this task, would they use these words? [Attention is query-driven: tokens semantically close to the user's query receive higher attention weights (semantic-compression-for-llms.md Q1, grounded in RAG retrieval literature). The "Intent Extraction test" is a design heuristic, not a cited method.]

3. **2-5 words per trigger.** Below 3 words, semantic collisions spike: Patil et al., "Gorilla: Large Language Model Connected with Massive APIs" (2023, UC Berkeley) found tools with >0.85 cosine similarity in description embeddings have 3-5x higher confusion rates. Above 5 words, diminishing retrieval benefit per additional token. [The "compression cliff below ~3 words" is from Jiang et al., LLMLingua (2023): aggressive compression below ~3 descriptive words per concept causes confusion between similar items.]

4. **One verb, one tool.** The single most impactful collision prevention technique. Patil et al. (Gorilla, 2023) found verb overlap is the #1 cause of wrong tool selection in function-calling benchmarks: shared verbs cause the model to pick based on superficial features (position, name familiarity) rather than semantic distinction. If two entries share a primary verb, rewrite one. "compare" for comm means "diff" cannot also say "compare." Use "show byte-level differences" for cmp instead.

5. **Differentiate high-collision pairs explicitly.** Within the same namespace, similar commands need extra disambiguation. Gorilla (Patil et al., 2023) showed collisions cluster almost exclusively within semantic categories, not across them. Known collision risks:
   - comm vs diff: "unique lines per sorted file" vs "line-by-line file differences"
   - cut vs awk: "extract fields by delimiter" vs "pattern-scan and transform"
   - split vs csplit: "split by size/line count" vs "split at pattern match"

### Qualifier Annotations

Append parenthetical qualifiers ONLY when needed. Three valid uses:

**1. Negation (NOT x):** Use when there's a strong LLM prior toward the wrong command. Positive description MUST come first. Tang et al. (2024) found explicit negation with a positive alternative reduces wrong-tool selection by 40-60%; without the positive alternative, negation alone reduces errors by only 10-20% and occasionally increases them (the "ironic process" effect; Wegner, 1994; Shi et al., "Large Language Models Can Be Easily Distracted by Irrelevant Context", 2023). Limit to 6-8 total across the ~48 bridge entries. [The original 8-12 range (from semantic-compression-for-llms.md Q6) was calibrated against all 155 POSIX utilities (5-8% negation density). With the bridge scoped to ~48 commands, 8-12 negations would be 17-25% density, which is too high. 6-8 maintains roughly the same density (~12-17%). This adjusted range is speculative; validate by testing whether negation counts above 8 degrade retrieval for non-negated entries.]

```
portable archive interchange -> pax (NOT tar)              CORRECT
resolve symlink to canonical path -> realpath (NOT readlink -f which is GNU)
                                                           TOO LONG, burns tokens
```

Known candidates for negation: pax/tar, od/xxd, cksum/md5sum, expand/sed, bc/expr vs python.

**2. Affirmation (IS POSIX):** Use for Issue 8 additions (timeout, realpath, readlink) where the LLM may believe the command is non-standard. Strictly safer than negation because it does not activate any wrong-answer tokens (Shi et al., 2023: mentioning irrelevant information, even negated, increases probability of the model using it; affirmation avoids this entirely).

```
run command with time limit, kill if exceeded -> timeout (IS POSIX)
resolve symlink to canonical path -> realpath (IS POSIX)
read target of symbolic link -> readlink (IS POSIX)
```

**3. Disambiguation (like X):** Use sparingly when a database/programming analogy helps. Only when the analogy is precise.

```
relational join on shared field -> join (like SQL JOIN)
```

**Do not add qualifiers to entries that don't need them.** An entry without a qualifier is fine. Unnecessary qualifiers add tokens and cognitive noise.

### Schema Priming

The first 2-3 entries in each namespace set the parsing template. The LLM extrapolates the pattern to all remaining entries. Jiang et al., "LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models" (2023, Microsoft) showed that aggressive compression preserves 90-95% accuracy when structural cues remain intact; the first entries provide those cues. [The specific claim "2-3 entries set the template" is inferred from LLMLingua's finding that consistent format patterns survive compression. The exact number "2-3" is a design heuristic, not a measured threshold. Speculative.]

Make the first entries in each namespace exemplary: perfectly formatted, clear trigger phrase, representative of the namespace's content. Lead with the commands users are most likely to ask about within that category.

**Exception for rare-command namespaces:** If a namespace contains mostly sub-40% retrieval commands and no bridge candidate above ~60%, one "obvious" command (>80% baseline retrieval) is permitted as the schema primer. The LLM's high confidence in recognizing the obvious command reinforces the format parse, which lifts retrieval for the obscure entries that follow. Cost: ~15 tokens. Expected benefit: improved parsing accuracy across the remaining namespace entries. Prefer a moderately-known bridge candidate (40-60% retrieval) as primer when one exists; fall back to an obvious command only when the entire namespace is deep sub-40% territory. [Speculative: no direct study on "obvious anchors improve parsing of rare entries." Inferred from LLMLingua's schema priming finding plus the observation that confident recognition of a known command strengthens format extrapolation. Testable: run the namespace with and without the anchor, compare retrieval on remaining entries across 3 models.]

### What NOT to Include in the Syntax Lookup Layer

**Commands the LLM already retrieves at >80%.** The bridge's value is activating recall of under-utilized commands. grep, sed, awk, find, sort, cat, ls, chmod, cp, mv, head, tail, wc, diff are already well-served by the LLM's training data. Including them wastes tokens and dilutes attention from the commands that actually need bridging. [Name familiarity bias: Gorilla (Patil et al., 2023) documents that LLMs are biased toward tools seen more frequently in training data. Including already-known commands burns tokens without overcoming any bias.]

The "obvious" list must be validated empirically per target model. Run discovery tasks against the bare LLM (no bridge). Exclude any command retrieved at >80% accuracy. The hypothesis is ~43 commands are obvious on frontier models; smaller models may only reliably retrieve ~25-30. [The ~43 number comes from the POSIX command audit (posix-command-audit.md). The 80% threshold and the "~25-30 for smaller models" estimate are speculative design targets, not empirically measured. Phase 3 of the implementation sequence exists to validate these numbers.]

**Shell builtins.** alias, cd, export, set, etc. These are not discoverable via a semantic map because they are part of the shell, not standalone utilities.

**Obsolete commands.** compress, uucp, fort77, SCCS family. Dead weight.

**Interactive-only commands.** vi, ed, more. These do not compose in pipes and are not useful in agent contexts.

**Flag-level documentation.** That is the companion binary's job. The skill file says WHICH command; the binary says WHICH FLAGS.

---

## Spec Search: Composition Idioms

**Budget:** 100 tokens (4-6 one-line pipe examples)
**Purpose:** Teach multi-command composition by example. Knowing individual commands does not guarantee the LLM can chain them. [NL2SH: LLM-Supported NL to Bash Translation (NAACL 2025) provides a 600-pair NL-to-Bash benchmark with functional equivalence testing, demonstrating that pipeline composition is a distinct capability from single-command selection.]

**Format:** Comment line + command. No prose explanation.

```
# lines in A not in B (sorted)
comm -23 <(sort a.txt) <(sort b.txt)
# top 10 most frequent words
tr -s '[:space:]' '\n' < file | sort | uniq -c | sort -rn | head -10
# compress logs in parallel
find . -name '*.log' -print0 | xargs -0 -P4 gzip
# merge columns tab-delimited
paste -d'\t' names.txt scores.txt
```

**Selection criteria:** Each idiom should use 2-5 commands, at least one of which is a Syntax Lookup bridge candidate. Prefer idioms that demonstrate patterns (process substitution, xargs parallelism, sort|uniq counting) over one-off recipes. [Speculative: the "must include a bridge candidate" constraint is a design heuristic. No study directly compares all-obvious-command idioms vs. bridge-candidate idioms for compositional learning. Rationale: the idiom section's budget is too small to waste on patterns the LLM can already construct.]

**What to avoid:** Do not include idioms that only use well-known commands (grep | wc -l). The idiom must bridge at least one under-retrieved command.

---

## Global Format Rules

These apply to the entire file.

1. **ASCII only.** No Unicode arrows, no em dashes, no smart quotes. Use `->` not `→`. Claude and GPT handle Unicode fine; Gemini is inconsistent in structured injection contexts. ASCII is the cross-model safe default.

2. **No markdown formatting.** No bold, no italic, no headers (except the Discovery Map layer can use plain prose). The file is a structured reference, not a document. Markdown triggers "document reading" mode; the file needs "structured data scanning" mode. [Inferred from Clark et al. (2019) attention head specialization. The specific "document reading" vs. "structured data scanning" framing is a descriptive model, not a cited result. Speculative but consistent with observed LLM behavior on code vs. prose inputs.]

3. **Perfect consistency.** Every Syntax Lookup entry follows the identical pattern: `trigger phrase -> command` or `trigger phrase -> command (qualifier)`. Zero exceptions. Inconsistency (mixing formats, omitting the arrow on some lines, using different delimiters) degrades retrieval by 10-15%. [The 10-15% degradation figure is from semantic-compression-for-llms.md Q5, attributed to format comparison studies (Sui et al., 2024 and related work). The exact percentage is an estimate across multiple studies, not a single measurement.]

4. **No blank lines between entries within a namespace.** Blank lines between entries waste tokens and can be misinterpreted as section breaks. One blank line between namespace headers is fine.

5. **One trailing newline at end of file.** Standard POSIX text file convention.

---

## Token Counting

Before finalizing, count tokens with tiktoken `o200k_base` (the cross-model reference tokenizer; Artificial Analysis methodology uses o200k_base as the normalization standard). If your final file exceeds 2,000 tokens, cut entries from the Syntax Lookup layer starting with the commands closest to the "obvious" boundary, or trim the Spec Search layer to 3 idioms. Target remains 1,050; anything under 2,000 is within the validated near-perfect retrieval zone.

```python
import tiktoken
enc = tiktoken.get_encoding("o200k_base")
with open("sayance-core.md") as f:
    tokens = enc.encode(f.read())
print(f"Token count: {len(tokens)}")
```

If tiktoken is not available, word count * 1.3 is a reasonable proxy for English text with code-like formatting. [The 1.3 ratio is from llm-benchmark-methodology.md section 2: "typical ratio is ~1.3 tokens per word for English text."]

---

## Validation Checklist

Before shipping the skill file, verify:

- [ ] Discovery Map is plain prose, not structured
- [ ] Syntax Lookup uses [BRACKET_CAPS] headers
- [ ] Syntax Lookup entries are trigger-phrase-first, not command-first
- [ ] Every trigger phrase is 2-5 words, verb-forward
- [ ] No two entries in the same namespace share a primary verb
- [ ] Negations (NOT x) are limited to 6-8 total, each with positive description first
- [ ] Issue 8 commands use (IS POSIX) not negation
- [ ] No bullet prefixes on entries
- [ ] ASCII only throughout
- [ ] No commands the LLM already retrieves at >80%
- [ ] No flag-level documentation (binary's job)
- [ ] First 2-3 entries per namespace are exemplary (schema priming)
- [ ] Rare-command namespaces (all entries sub-40%) use an obvious anchor as schema primer if no 40-60% candidate exists
- [ ] Namespaces ordered by query frequency (highest first)
- [ ] Total token count is under 2,000 (target 1,050)
- [ ] File ends with single newline

---

## Research Backing

Rules are tagged: **Cited** (directly supported by named research), **Inferred** (logically derived from cited findings but not directly tested), or **Speculative** (design heuristic without direct evidence).

| Rule | Source | Finding | Status |
|------|--------|---------|--------|
| Sub-2K token ceiling | Needle-in-haystack (Anthropic, 2024; Google, 2024) | Context under 2K tokens = near-perfect retrieval across all major models | Cited |
| ~800 tokens for Syntax Lookup | Same needle-in-haystack studies | Sub-1K = <5% positional degradation; the "perfect retrieval" zone | Cited |
| [BRACKET_CAPS] headers | Clark et al., "What Does BERT Look At?" (2019); Qin et al., ToolLLM (2023) | Attention heads specialize by structure; grouped tools with categorical headers show 15-30% higher selection accuracy | Cited (Clark on attention heads; ToolLLM on grouped accuracy). The "scanning mode" framing is inferred |
| 6-8 namespaces | Miller, "Magical Number Seven" (1956); Qin et al., ToolLLM (2023) | 5-9 categories maximizes discrimination in both human cognition and LLM tool selection | Cited |
| Verb-forward triggers | Schick et al., "Toolformer" (2023, Meta) | Verb-forward tool descriptions yield higher selection accuracy | Cited |
| 2-5 words per hook | Jiang et al., "LLMLingua" (2023, Microsoft); Patil et al., "Gorilla" (2023, UC Berkeley) | Below ~3 words = semantic collisions (Gorilla: >0.85 cosine similarity = 3-5x confusion). LLMLingua: compression cliff below ~3 descriptive words | Cited |
| One verb, one tool | Patil et al., "Gorilla" (2023) | Verb overlap is #1 cause of wrong tool selection in function-calling benchmarks | Cited |
| (NOT x) with positive first | Tang et al. (2024); Wegner ironic process (1994); Shi et al. (2023) | 40-60% confusion reduction with positive alternative; without it, 10-20% or worse | Cited |
| (IS POSIX) for Issue 8 | Shi et al., "LLMs Can Be Easily Distracted by Irrelevant Context" (2023, Google) | Mentioning irrelevant information even negated increases its probability; affirmation avoids this | Cited |
| 6-8 negation limit (for ~48 entries) | Shi et al. (2023) | Excess irrelevant mentions dilute attention. Original 8-12 was for 155 commands; adjusted to ~12-17% density for 48-entry scope | Inferred (dilution effect is cited; density-adjusted count is a heuristic) |
| No bullet prefixes | Sui et al., "Table Meets LLM" (2024) | Bullet lists match table accuracy at 30-40% fewer tokens; under headers, bullets add no retrieval gain | Cited |
| ASCII only | Cross-model testing (semantic-compression-for-llms.md Q8) | Gemini inconsistent with Unicode in structured injection contexts | Practical observation, not a formal paper |
| Schema priming (2-3 entries) | Jiang et al., "LLMLingua" (2023) | Consistent format patterns survive compression; LLM extrapolates from early entries. Exact "2-3" threshold is a design heuristic | Inferred |
| Obvious anchor for rare namespaces | None | One obvious command as schema primer may lift parsing for obscure entries in the same namespace | Speculative (testable) |
| Trigger-first entry order | Schick et al. (Toolformer, 2023) | Verb-forward improves selection; inferred that user-language-first entry order follows the same principle | Inferred |
| Namespace ordering | Liu et al., "Lost in the Middle" (2023, Stanford/UC Berkeley) | Primacy > recency for factual retrieval; items at positions 1-3 retrieved ~90% vs. ~60% at mid-positions (at 4K+ token context) | Cited (but effect is attenuated at sub-2K context) |
| Headers reset position counter | Inferred from Liu et al. (2023) + Clark et al. (2019) | Section headers create sub-contexts that partially counteract lost-in-the-middle | Speculative (mechanistically plausible, not directly measured) |
| Prose Discovery Map before structured Syntax Lookup | Clark et al. (2019) attention head specialization | Format shift may signal attention mode transition | Speculative (no direct study on prose-to-structure transitions) |
| Behavioral directive efficacy | Wei et al. (2023); Anthropic tool-use docs | Instruction-following and system prompt instructions bias tool selection | Inferred (no direct study on "behavioral directive increases map utilization") |
| Composition idioms | NL2SH (NAACL 2025) | 600-pair NL-to-Bash benchmark shows pipeline composition is distinct from single-command knowledge | Cited |
| Consistency degrades retrieval 10-15% | Sui et al. (2024) and related format comparison work | Inconsistent formatting in structured references degrades retrieval | Cited (aggregate estimate across multiple studies, not a single measurement) |
| Word count * 1.3 token proxy | llm-benchmark-methodology.md §2 | Typical ratio for English text; Artificial Analysis uses o200k_base as normalization standard | Practical reference |
