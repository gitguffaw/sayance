# POSIX Semantic Bridge: Architecture & Eval Design

## The Problem

LLMs have latent knowledge of POSIX commands but systematically under-utilize them. When a user says "find what's in file A but not file B," most LLMs reach for Python instead of `comm -23`. The semantic bridge corrects this retrieval bias without bloating the context window.

Three sub-problems:

1. **Skill file (discovery layer)**: A lightweight prompt that activates POSIX command recall and biases toward CLI composition, compatible with any LLM via system prompt injection.
2. **Companion binary (precision layer)**: A static CLI tool the LLM can invoke to get exact flags, syntax, and usage for a specific command once it knows which command to reach for.
3. **Eval design**: A testing framework that measures whether the bridge works using naturalistic queries, not direct command references.

The skill file answers "which command?" The binary answers "which flags, in what order?" This separation keeps the always-loaded context small while giving the LLM access to precise documentation on demand.

---

## Part 1: Semantic Bridge Architecture

### Core Design Insight

The bridge does not need to TEACH commands. LLMs already know what `comm`, `paste`, `tsort`, and `csplit` do. The bridge needs to:

1. **Activate recall** of commands the LLM "knows" but doesn't reach for
2. **Bias behavior** toward POSIX solutions over scripting languages
3. **Enable composition** by showing pipe idioms

This means the bridge is closer to a retrieval cue than a reference manual.

### Token Budget

For cross-LLM system prompt injection, the bridge must share context with other instructions. Target: **1,200-1,800 tokens** (~900-1,400 words). This is achievable because the bridge is a recall activator, not documentation.

### Three-Layer Architecture

```
Discovery Map: Behavioral Directive       (~150 tokens)
Syntax Lookup: Intent-to-Command Map      (~900 tokens)
Spec Search:   Composition Patterns       (~300 tokens)
```

#### Discovery Map: Behavioral Directive

A short preamble that shifts the LLM's default behavior. This is the highest-ROI section per token.

```
When the user describes a file, text, or process task on a Unix-like system,
prefer POSIX shell commands and pipelines over scripting languages. POSIX
utilities are already installed, require no dependencies, and compose via pipes.
Reach for Python/Node only when the task genuinely requires data structures,
network calls, or logic that pipes cannot express.
```

Why this works: LLMs are instruction-followers. A direct behavioral nudge changes the prior probability of reaching for `comm` vs. `pandas`. Without this, the bridge is just a reference the LLM may ignore.

#### Syntax Lookup: Intent-to-Command Map

This is the core of the bridge. Organized by **user intent**, not command name. Only includes commands where LLMs demonstrably under-retrieve; the top ~40 commands (grep, sed, awk, find, sort, etc.) are excluded because LLMs already reach for them reliably.

**Design principle**: Each entry maps a natural language trigger phrase to the command. The trigger phrase is the semantic bridge; the command name is just the anchor.

Proposed intent clusters:

**Comparing & Merging Files**
- Lines unique to file A vs. B, or common to both → `comm`
- Merge columns from multiple files side by side → `paste`
- Relational join on a shared field (like SQL JOIN) → `join`
- Show byte-level differences between binaries → `cmp`
- Apply a patch file to source → `patch`

**Splitting & Restructuring**
- Split a file into N-line or N-byte chunks → `split`
- Split a file at lines matching a pattern → `csplit`
- Select specific columns/fields from each line → `cut`
- Number every line in a file → `nl`
- Wrap long lines to a fixed width → `fold`
- Format text into simple paragraphs → `fmt`
- Paginate output with headers/footers → `pr`

**Character & Encoding**
- Transliterate or delete specific characters → `tr`
- Convert between character encodings (UTF-8 ↔ Latin-1) → `iconv`
- Convert tabs to spaces → `expand`
- Convert spaces to tabs → `unexpand`

**Computation & Logic**
- Arbitrary-precision calculator → `bc`
- Evaluate arithmetic expressions → `expr`
- Topological sort (dependency ordering) → `tsort`
- Macro processing / text generation → `m4`

**Binary & Low-Level Inspection**
- Hex/octal dump of binary data → `od`
- Extract printable strings from a binary → `strings`
- Identify file type by magic bytes → `file`
- Check if a pathname is valid/portable → `pathchk`
- Compute checksums → `cksum`

**Process & Job Control**
- Run a command immune to hangups → `nohup`
- Build command lines from stdin → `xargs`
- Duplicate output to both file and stdout → `tee`
- Run command at lower priority → `nice` / `renice`
- Schedule a one-time job → `at` / `batch`
- Manage recurring scheduled jobs → `crontab`
- Send signal to process by name → `kill` (with patterns)
- Wait for background processes → `wait`

**User & System Info**
- Current terminal name → `tty`
- Current login name → `logname` / `id`
- System name and version → `uname`
- Who is logged in → `who`
- Locale settings → `locale`
- Get system configuration values → `getconf`

**Development & Build**
- Compile C source → `c99`
- Archive object files → `ar`
- Strip symbols from binaries → `strip`
- Generate lexical analyzers → `lex`
- Generate parsers → `yacc`
- Build automation → `make`
- Preprocess with macros → `m4`

**New in Issue 8 (agent-relevant)**
- Run a command with a time limit; kill if exceeded → `timeout`
- Resolve symlinks to get canonical absolute path → `realpath`
- Read the target of a symbolic link → `readlink`

**Command count audit (POSIX.1-2024, Issue 8):**

Issue 8 (published 14 June 2024) added 7 utilities and removed 12 from Issue 7. Delta confirmed via [ShellCheck PR #3307](https://github.com/koalaman/shellcheck/pull/3307). See `posix-command-audit.md` for per-command detail.

| Category | Count | Disposition |
|----------|-------|-------------|
| Total Issue 8 utilities | ~155 | |
| Shell builtins (alias, cd, export, etc.) | 27 | Skip: not discoverable via bridge |
| SCCS family (admin, delta, get, etc.) | 10 | Skip: obsolete version control |
| Obsolete (compress, uucp, talk, etc.) | 12 | Skip: replaced or defunct |
| Interactive-only (vi, ex, ed, more) | 4 | Skip: don't compose in pipes |
| i18n tools (gettext, msgfmt, ngettext, xgettext) | 4 | Skip: narrow audience (optional variant) |
| Dev tools (ar, c99, lex, yacc, nm, strip, etc.) | 9 | Optional: dev-focused bridge variant |
| LLMs already retrieve reliably | ~43 | Skip (validate empirically per model) |
| **Bridge candidates** | **~48** | **Core Syntax Lookup content** |

The ~48 bridge candidates include 3 commands new in Issue 8 (`timeout`, `realpath`, `readlink`) that are high-value for agent contexts. The "LLMs already retrieve" count is a hypothesis for frontier models; validate empirically by running discovery tasks against the bare LLM and excluding commands with >80% retrieval accuracy.

#### Spec Search: Composition Patterns

Short pipe idioms that demonstrate how to chain commands. These teach composition by example rather than by rule.

```
# Find lines in A not in B (files must be sorted)
comm -23 <(sort a.txt) <(sort b.txt)

# Merge two files column-wise with a tab delimiter
paste -d'\t' names.txt scores.txt

# Top 10 most frequent words in a file
tr -s '[:space:]' '\n' < file | sort | uniq -c | sort -rn | head -10

# Process files in parallel with xargs
find . -name '*.log' -print0 | xargs -0 -P4 gzip

# Split CSV by a pattern, keeping headers
csplit --prefix=chunk data.csv '/^2024/' '{*}'

# Dependency-order a build graph
tsort dependencies.txt

# Convert encoding and normalize line endings
iconv -f ISO-8859-1 -t UTF-8 input.txt | tr -d '\r' > output.txt
```

### Compression Strategies

Several techniques keep the bridge within token budget:

1. **Omit the empirically obvious**: Run discovery tasks against the bare LLM (no bridge) and measure which commands it retrieves at >80% accuracy. Those are excluded from the Syntax Lookup layer. The hypothesis is that ~40 commands (grep, sed, awk, find, sort, cat, ls, chmod, cp, mv, head, tail, wc, diff, etc.) will pass this bar on frontier models, but smaller models may only reliably reach for ~25. The cutoff is per-model, not universal.

2. **Trigger phrases over man pages**: "Merge columns side by side → paste" is 7 tokens. A man-page description of paste is 50+ tokens. The trigger phrase is the semantic bridge; the LLM fills in the usage details from latent knowledge.

3. **Group by intent cluster**: Cluster headers ("Comparing & Merging Files") serve double duty as semantic context and organization.

4. **Composition patterns teach multiple commands**: Each pipe example activates recall of 3-5 commands simultaneously.

### What the Skill File Does NOT Include

- Flag-level documentation (that's the binary's job)
- Commands the LLM already retrieves reliably
- Non-POSIX GNU extensions (scope creep; save for a follow-up bridge)
- Interactive commands (vi, ed, mailx: don't compose in agent contexts)

---

## Part 1b: Companion Binary (Precision Layer)

### The Problem It Solves

The skill file gets the LLM to "I should use `csplit`." But `csplit` has tricky syntax: `csplit file '/pattern/' '{*}'`. The LLM's latent knowledge of flag combinations for under-used commands is unreliable. Rather than bloating the skill file with flag docs for 45 commands (~4,000+ tokens), give the LLM a tool it can call.

### Interface

```
posix-ref <command>                  # Full reference for one command
posix-ref <command> --task "<goal>"  # Flags for a specific task
posix-ref --suggest "<description>"  # Suggest command from description
posix-ref --compose "<pipeline>"     # Validate/improve a pipeline
posix-ref --list                     # List all indexed commands
posix-ref --list --cluster           # List grouped by intent cluster
```

### Example Interactions

```
$ posix-ref comm
comm - compare two sorted files line by line
Usage: comm [-123] file1 file2
Flags:
  -1  suppress lines unique to file1
  -2  suppress lines unique to file2
  -3  suppress lines common to both
Common patterns:
  comm -23 a b    # lines only in a
  comm -13 a b    # lines only in b
  comm -12 a b    # lines in both
Note: both files must be sorted. Use process substitution if not:
  comm -23 <(sort a) <(sort b)

$ posix-ref csplit --task "split file at each line matching ERROR"
csplit file '/ERROR/' '{*}'
  '/ERROR/'  split at lines matching this pattern
  '{*}'      repeat until end of file (without this, splits only at first match)
Output: files named xx00, xx01, xx02, ...
  Use --prefix=chunk to change prefix: chunk00, chunk01, ...

$ posix-ref --suggest "merge two files column by column"
Suggested: paste
  paste file1 file2          # tab-delimited by default
  paste -d',' file1 file2    # comma-delimited
  paste -s file1             # serial: join all lines of file1 into one line
```

### Implementation

**Data layer**: A single embedded JSON/TOML file containing structured records for all ~155 POSIX.1-2024 commands:

```json
{
  "comm": {
    "summary": "compare two sorted files line by line",
    "usage": "comm [-123] file1 file2",
    "flags": {
      "-1": "suppress lines unique to file1",
      "-2": "suppress lines unique to file2",
      "-3": "suppress lines common to both"
    },
    "patterns": [
      {"task": "lines only in A", "cmd": "comm -23 a b"},
      {"task": "lines only in B", "cmd": "comm -13 a b"},
      {"task": "lines in both", "cmd": "comm -12 a b"}
    ],
    "caveats": ["both files must be sorted"],
    "cluster": "comparing-merging",
    "triggers": ["unique lines", "common lines", "set difference", "set intersection"]
  }
}
```

**Language choice**: Go or Rust. Single static binary, zero dependencies, <2MB, sub-50ms startup. The data file compiles into the binary. No runtime file reads, no Python dependency.

**Why not just `man`?** Three reasons:

1. `man` output is verbose and unstructured. The LLM has to parse prose to find flag info. The binary returns structured, minimal output the LLM can act on immediately.
2. `man` doesn't include task-oriented patterns. "How do I get lines only in file A?" isn't in the man page.
3. `man` pages vary by OS. The binary provides a canonical POSIX reference regardless of what's installed.

### How Skill File and Binary Work Together

```
User: "I need to find which usernames are in our January list but not February"
                    │
                    ▼
        ┌─────────────────────┐
        │   SKILL FILE        │
        │   (in LLM context)  │
        │                     │
        │   Intent cluster:   │
        │   "lines unique to  │
        │   file A vs B"      │
        │   → comm            │
        └────────┬────────────┘
                 │ LLM thinks: "I should use comm"
                 ▼
        ┌─────────────────────┐
        │   COMPANION BINARY  │
        │   (tool call)       │
        │                     │
        │   $ posix-ref comm  │
        │   → exact flags,    │
        │     sort caveat,    │
        │     process sub     │
        └────────┬────────────┘
                 │ LLM now has precise syntax
                 ▼
        comm -23 <(sort jan.txt) <(sort feb.txt)
```

The skill file (Discovery Map) costs ~1,500 tokens always. The binary (Syntax Lookup) costs ~0 tokens until invoked, then ~50-100 tokens per call. This is dramatically more efficient than loading all flag documentation into context.

### Build Phases

**Phase 1**: Populate the data file for the ~48 bridge candidate commands. Source from POSIX.1-2024 (Issue 8) spec + man pages. Structured extraction, not creative writing.

**Phase 2**: Implement the `posix-ref <command>` and `posix-ref --list` subcommands. Minimal viable binary.

**Phase 3**: Add `--task` and `--suggest` subcommands. These require a lightweight search over the triggers and patterns fields.

**Phase 4**: Add `--compose` for pipeline validation. This is the hardest feature; it needs to parse pipe syntax and check flag compatibility. Could defer to v2.

---

## Part 2: Eval Framework

### The Needle-Threading Problem

You can't test a semantic bridge by asking "use the comm command." That tests the LLM's ability to follow instructions, not the bridge's ability to surface the right command from naturalistic input.

The eval must use queries that:
- Describe a TASK, not a command
- Are phrased the way a real user would phrase them
- Have a POSIX-optimal solution that the LLM would likely miss without the bridge
- Include distractors where POSIX is NOT the right answer

### Eval Architecture

```
┌─────────────────────────────────────────────┐
│              TASK SET (~400 items)           │
│                                             │
│  Discovery Tasks ─── Composition Tasks      │
│  Preference Tasks ── Distractor Tasks       │
└────────────────┬────────────────────────────┘
                 │
          ┌──────┴──────┐
          │  A/B Test    │
          │  With bridge │
          │  No bridge   │
          └──────┬──────┘
                 │
     ┌───────────┴───────────┐
     │   Scoring Rubric      │
     │                       │
     │  Command Selection    │
     │  POSIX Preference     │
     │  Pipeline Correctness │
     │  Functional Equiv.    │
     └───────────────────────┘
```

### Task Categories

**Category 1: Discovery (single command)**
Tests whether the bridge activates recall of a specific under-utilized command.

Example tasks:
- "I have two sorted text files of email addresses. I need to find which addresses appear in the first file but not the second." → `comm -23`
- "I need to merge two files so that line 1 of file A and line 1 of file B appear on the same row, separated by a tab." → `paste`
- "I have a dependency graph where each line is 'A B' meaning A depends on B. I need them in build order." → `tsort`
- "This text file has lines that are 300 characters wide. I need to wrap them to 80 characters." → `fold -w 80`
- "I need to convert this file from ISO-8859-1 encoding to UTF-8." → `iconv`

**Category 2: Composition (multi-command pipeline)**
Tests whether the bridge enables the LLM to chain POSIX commands into correct pipelines.

Example tasks:
- "Find all .log files modified in the last 7 days and compress them in parallel, using all available cores." → `find ... -print0 | xargs -0 -P$(nproc) gzip`
- "Count how many unique IP addresses appear in column 3 of a space-delimited log file." → `cut -d' ' -f3 logfile | sort -u | wc -l`
- "Split this CSV file into separate files every time the date column changes from one month to the next." → `csplit` with pattern
- "Take two files, join them on the first column like a SQL join, then sort the result by the third column." → `join file1 file2 | sort -k3`

**Category 3: Preference (POSIX one-liner vs. multi-line script)**
Tasks where the LLM defaults to a 5-15 line Python/Node script but a single POSIX pipeline solves it in one line. Scoped to three specific task clusters:

*Text transforms* (character replacement, line filtering, field extraction, dedup, line numbering, whitespace normalization):
- "Replace all tabs with 4 spaces in every .txt file in this directory." → `find . -name '*.txt' -exec expand -t 4 -i {} \;` vs. Python glob + open + replace
- "Delete all blank lines from a file." → `sed '/^$/d'` vs. Python readlines + filter
- "Number every line in a file, right-justified." → `nl` vs. Python enumerate

*File restructuring* (splitting, merging columns, reordering lines, encoding conversion):
- "Take the second column from each of three TSV files and put them side by side." → `cut` + `paste` vs. Python csv module
- "Split this 10GB log file into 100MB chunks." → `split -b 100m` vs. Python chunked read

*Counting and aggregation* (frequency counts, unique counts, line/word/byte counts across files):
- "How many unique values are in column 4 across all .csv files?" → `cut -d, -f4 *.csv | sort -u | wc -l` vs. Python pandas

The scoring question is binary: did the LLM produce a one-liner or a script? The bridge should shift the ratio toward one-liners for these three clusters specifically.

**Category 4: Distractor (POSIX is wrong answer)**
Tasks where the right answer is NOT a POSIX command. Tests precision: the bridge should not cause the LLM to force POSIX where it doesn't fit.

Example tasks:
- "Parse this JSON file and extract the 'name' field from each object in the array." → `jq` (not POSIX) or Python
- "Make an HTTP POST request with a JSON body and parse the response." → curl + jq, or Python
- "Read a CSV with quoted fields containing commas and compute column averages." → Python/pandas (POSIX tools choke on quoted CSV)

### Task Generation Methodology

For each of the ~48 bridge candidate commands in the Syntax Lookup layer:

1. Write 3 task descriptions at varying specificity levels:
   - **High specificity**: "I need to find lines common to both sorted files" (clearly `comm`)
   - **Medium specificity**: "I have two membership lists and want to know the overlap" (requires inference)
   - **Low specificity**: "Which customers are in both our Q1 and Q2 lists?" (requires domain mapping)

2. Have 2-3 humans rate each task on a 1-5 "naturalness" scale. Discard anything below 3.

3. Add 30-40 composition tasks that require 2+ commands piped together.

4. Add 20-30 distractor tasks where POSIX is not optimal.

Target: ~250-350 scored eval items after filtering.

### Scoring Rubric

Each response is scored on four dimensions:

**1. Command Selection (0-2 points)**
- 2: Chose the optimal POSIX command
- 1: Chose a valid but suboptimal POSIX command (e.g., `awk` where `comm` is cleaner)
- 0: Chose a non-POSIX solution or the wrong command

**2. POSIX Preference (0-1 point)**
- 1: Reached for POSIX first (even if also offering alternatives)
- 0: Defaulted to a scripting language

**3. Pipeline Correctness (0-2 points)**
- 2: Pipeline runs correctly and produces expected output
- 1: Pipeline has minor errors (wrong flag, missing quote) but correct structure
- 0: Pipeline is fundamentally broken or incomplete

**4. Functional Equivalence (0-1 point)**
- 1: Output is functionally equivalent to the reference solution
- 0: Output differs in a meaningful way

Maximum score per task: 6 points. Distractor tasks are scored inversely on POSIX Preference (1 point for NOT forcing POSIX).

### Baseline Methodology

**A/B Design:**
- **Condition A (control)**: Same LLM, same system prompt, NO bridge
- **Condition B (treatment)**: Same LLM, same system prompt, WITH bridge

**Procedure:**
1. Run all tasks through both conditions
2. Score each response using the rubric above
3. Compare aggregate scores per category and per command

**Key Metrics:**
- **Lift**: Mean score(B) - Mean score(A) per category
- **Coverage**: % of bridge commands that show measurable lift
- **Precision**: Distractor task accuracy (bridge should not degrade these)
- **Token efficiency**: Lift per token of bridge content

**Functional Equivalence Testing:**
Following the NL2SH approach (Aclanthology, NAACL 2025), combine execution-based testing with LLM-as-judge:
1. Execute both the reference solution and the model's solution on test inputs
2. Compare outputs programmatically
3. For edge cases, use a separate LLM call to judge functional equivalence
4. This hybrid approach achieved 95% confidence in the NL2SH paper, 16% above pure heuristics

### Eval Automation

```
eval-harness/
├── tasks/
│   ├── discovery/       # Single-command tasks, grouped by target command
│   ├── composition/     # Multi-command pipeline tasks
│   ├── preference/      # POSIX-vs-script tasks
│   └── distractor/      # Non-POSIX tasks
├── fixtures/            # Test input files for each task
├── reference/           # Expected outputs per task
├── runner.py            # Sends tasks to LLM, captures responses
├── scorer.py            # Applies rubric, computes metrics
├── equiv.py             # Functional equivalence checker (exec + LLM judge)
└── report.py            # Generates comparison dashboard
```

Each task is a JSON object:

```json
{
  "id": "discovery-comm-001",
  "category": "discovery",
  "target_command": "comm",
  "query": "I have two sorted text files of usernames. Show me the names that appear in users_jan.txt but not in users_feb.txt.",
  "reference_solution": "comm -23 users_jan.txt users_feb.txt",
  "fixtures": ["users_jan.txt", "users_feb.txt"],
  "expected_output": "users_jan_only.txt",
  "specificity": "high",
  "naturalness_score": 4.2
}
```

---

## Part 3: Open Questions & Next Steps

### Bridge Design Questions

1. **How aggressively to prune the "obvious" list?** The top 40 commands are excluded, but the boundary is fuzzy. `xargs` and `tee` are well-known to engineers but not to casual users. The right cutoff depends on the target audience. Recommend: start aggressive (exclude top 40), measure coverage, add back commands that show zero lift.

2. **Should the bridge include "anti-patterns"?** E.g., "Don't use Python to count lines in a file; use `wc -l`." Negative examples consume tokens but may be more effective than positive examples for preference tasks. Recommend: test both in eval.

3. **GNU extensions**: Commands like `parallel`, `jq`, `fd`, `ripgrep` are not POSIX but are ubiquitous. A second bridge layer for "modern CLI" could follow the same architecture. Keep POSIX-pure for v1.

4. **Dynamic loading**: For agent frameworks that support it, the bridge could be split into the Discovery Map (always loaded) + Syntax Lookup (loaded on demand when the task looks CLI-relevant). This halves the base token cost. Not viable for generic system prompt injection, but worth noting.

### Eval Design Questions

1. **How many LLMs to test?** Recommend: 3 minimum (Claude Sonnet, GPT-4o, Llama 3.1 70B) to validate cross-model generality.

2. **Temperature sensitivity**: Run each task 3x at temperature 0.3 to measure variance. If high variance, increase to 5x.

3. **Human baseline**: Have 2-3 experienced Unix users solve the same tasks to establish a ceiling score. If the bridge gets the LLM within 80% of human performance, that's strong.

4. **Ablation studies**: Test each layer independently (Discovery Map only, Syntax Lookup only, Discovery Map + Syntax Lookup, full bridge) to measure marginal contribution per layer.

---

## Summary of Recommendations

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Deliverable shape | Skill file + companion binary | Discovery in context, precision on demand |
| Skill file organization | Intent-first, not command-first | Matches how users think, not how man pages are organized |
| Skill file token budget | 1,200-1,800 tokens | Leaves room for other system prompt content |
| "Obvious" cutoff | Empirical: >80% retrieval rate on bare LLM | Per-model, not assumed; hypothesis is ~40 commands for frontier models |
| Bridge candidate count | ~48 commands | Audited against Issue 8: 155 total minus builtins, obsolete, interactive, obvious, narrow-audience; includes 3 new Issue 8 commands |
| Compression method | Trigger phrases, not descriptions | 7 tokens vs. 50+ per command; binary handles the details |
| Binary language | Go or Rust | Zero deps, static binary, <2MB, sub-50ms |
| Preference eval scope | 3 clusters: text transforms, file restructuring, counting/aggregation | Bounded, measurable, not "everything" |
| Eval task count | 200-280 items (3 per bridge command + composition + distractor) | Statistical power for per-command analysis |
| Eval design | A/B with functional equivalence | NL2SH methodology, 95% confidence |
| First milestone | Skill file + 10-command binary + 30 eval tasks | Validates architecture before scaling |
