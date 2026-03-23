# POSIX LLM Benchmark v0 (Scrappy Edition)

**Date:** 2026-03-22
**Purpose:** Measure how badly LLMs understand POSIX shell utilities
**Source of truth:** https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html
**Total POSIX utilities:** 160 (not 243 — common miscount)

---

## How to Use

1. Ask each question to 2+ LLMs (Claude, Gemini, GPT, etc.)
2. Grade each answer: **Correct** (2pts), **Partial** (1pt), **Wrong** (0pts)
3. Track which tiers and categories cause the most failures

---

## Tier 1: Common Commands (Should Be Easy)

### Q1 — sort: Field selection [Knowledge]
**Question:** "What exactly does `sort -k 2,2` do? How does it differ from `sort -k 2`?"

**Expected answer:** `-k 2,2` sorts by ONLY the second field. `-k 2` sorts by everything from the second field to end of line. The `,2` sets the end position of the key.

---

### Q2 — sed: POSIX compliance [POSIX vs GNU]
**Question:** "Is `sed -i` POSIX-compliant?"

**Expected answer:** No. In-place editing (`-i`) is a GNU extension. POSIX `sed` has no `-i` flag. The portable approach is: `sed 'expr' file > tmp && mv tmp file`.

---

### Q3 — find: Time-based search [Generation]
**Question:** "Write a POSIX-compliant command to find all `.conf` files modified in the last 24 hours."

**Expected answer:** `find / -name '*.conf' -mtime -1` (or with `-newer` using a reference file). NOT `-newermt` (GNU extension). NOT `-mmin` (GNU extension).

---

### Q4 — grep: Flag discrimination [POSIX vs GNU]
**Question:** "Which of these grep flags are POSIX-compliant: -i, -r, -P, -E, -o, -w, -c, -l, -n?"

**Expected answer:**
- POSIX: -i, -E, -c, -l, -n
- NOT POSIX: -r (GNU), -P (GNU/PCRE), -o (GNU), -w (GNU)

---

### Q5 — printf vs echo [Knowledge]
**Question:** "Why does POSIX recommend `printf` over `echo` for portable scripts?"

**Expected answer:** `echo` behavior varies across implementations (some interpret backslash escapes by default, some don't; `-n` flag not portable). `printf` has well-defined, consistent behavior in the POSIX spec. Portable scripts should use `printf '%s\n' "$var"` instead of `echo "$var"`.

---

## Tier 2: Uncommon Commands

### Q6 — pax [Knowledge]
**Question:** "What is `pax` and why does POSIX specify it instead of `tar`?"

**Expected answer:** `pax` (Portable Archive Interchange) is the POSIX-specified archiver. `tar` is NOT a POSIX utility. POSIX chose `pax` because it supports both `tar` and `cpio` formats and has a cleaner interface. It can read/write/list archives and copy file hierarchies.

---

### Q7 — tsort [Knowledge]
**Question:** "What does `tsort` do? Give a concrete use case."

**Expected answer:** `tsort` performs topological sorting — reads pairs of items (partial ordering) from stdin and outputs a total ordering. Use case: resolving build dependencies, library link ordering (used by `ld`), or any DAG ordering problem.

---

### Q8 — od: Hex dump [Generation]
**Question:** "Write a POSIX-compliant command to display a file as hexadecimal bytes."

**Expected answer:** `od -A x -t x1z file` or `od -t x1 file`. NOT `xxd` (not POSIX), NOT `hexdump` (not POSIX).

---

### Q9 — pathchk [Knowledge]
**Question:** "What does `pathchk` do and when would you use it?"

**Expected answer:** `pathchk` checks whether pathnames are valid and portable. With `-p`, checks against POSIX portable filename rules (length limits, allowed characters). Useful in scripts that create files on unknown target systems to ensure names won't cause problems.

---

### Q10 — m4 [Knowledge]
**Question:** "What is `m4` and why is it in the POSIX spec?"

**Expected answer:** `m4` is a general-purpose macro processor. It reads input, expands macros, and produces output. It's in POSIX because it's the standard macro language used by `autoconf` and historically for generating configuration files, `sendmail.cf`, etc. Supports define, conditionals, includes, diversions, arithmetic.

---

## Tier 3: Obscure Commands

### Q11 — sccs [Knowledge]
**Question:** "What is SCCS? Name 3 SCCS-related POSIX utilities and what they do."

**Expected answer:** SCCS = Source Code Control System, an early version control system (predates RCS/CVS/Git). POSIX SCCS utilities include:
- `admin` — create/modify SCCS files (s-files)
- `get` — retrieve versions from SCCS files
- `delta` — record changes (like a commit)
- `prs` — print SCCS file history
- `unget` — undo a `get`
- `sact` — show current editing activity
- `val` — validate SCCS files
- `what` — identify SCCS keywords in files
- `rmdel` — remove a delta (version)

---

### Q12 — fort77 [Knowledge]
**Question:** "What is `fort77`?"

**Expected answer:** `fort77` is the POSIX-specified FORTRAN 77 compiler interface. Similar to how `c99` is the C compiler interface. It compiles FORTRAN source files. Almost no modern system actually provides it — it's a legacy spec entry.

---

### Q13 — qsub [Knowledge]
**Question:** "What does `qsub` do in POSIX? Name 3 other `q*` utilities."

**Expected answer:** `qsub` submits a batch job to a queue. The `q*` utilities are the POSIX Batch Environment:
- `qalter` — alter batch job attributes
- `qdel` — delete batch jobs
- `qhold` — hold batch jobs
- `qmove` — move batch jobs to another queue
- `qmsg` — send message to batch jobs
- `qrerun` — rerun batch jobs
- `qrls` — release held batch jobs
- `qselect` — select batch jobs
- `qsig` — signal batch jobs
- `qstat` — show batch job status

---

### Q14 — cxref [Knowledge]
**Question:** "What does `cxref` do?"

**Expected answer:** `cxref` generates a C language cross-reference listing. It analyzes C source files and produces a listing showing where each identifier is defined and used. Similar to `ctags` but produces human-readable cross-reference output rather than editor tags.

---

### Q15 — asa [Knowledge]
**Question:** "What does `asa` do and what problem does it solve?"

**Expected answer:** `asa` interprets ASA/FORTRAN carriage control characters. FORTRAN programs use the first character of each output line to control printer behavior (space = single space, 0 = double space, 1 = new page, + = overprint). `asa` converts these to line-printer control sequences. A relic of mainframe printing.

---

## Meta Questions: POSIX Awareness

### Q16 — tar [Discrimination]
**Question:** "Is `tar` a POSIX utility?"

**Expected answer:** No. `tar` is NOT in the POSIX spec. The POSIX archiver is `pax`.

---

### Q17 — Common non-POSIX [Discrimination]
**Question:** "Which of these are NOT POSIX utilities: ls, wget, curl, top, less, vim, ssh, awk, sudo, which?"

**Expected answer:** NOT POSIX: wget, curl, top, less, vim, ssh, sudo, which. POSIX: ls, awk. (Note: `vi` is POSIX, but `vim` is not. `more` is POSIX, but `less` is not.)

---

### Q18 — Exit codes [Knowledge]
**Question:** "What exit codes does `test` (aka `[`) return according to POSIX?"

**Expected answer:** 0 = expression is true, 1 = expression is false, >1 = an error occurred. This is critical — many scripts depend on the distinction between "false" (1) and "error" (>1).

---

### Q19 — Complete count [Knowledge]
**Question:** "How many utilities does the POSIX spec define?"

**Expected answer:** 160 (per the current POSIX.1-2017/SUSv4 utility index). Common misconceptions include 243, which may count optional/deprecated entries or shell built-ins separately.

---

### Q20 — Generation challenge [Composition]
**Question:** "Write a POSIX-compliant script (no bashisms, no GNU extensions) that: reads a CSV file, extracts the 3rd column, sorts it uniquely, and counts the results."

**Expected answer (one possibility):**
```sh
cut -d',' -f3 file.csv | sort -u | wc -l
```
All of `cut`, `sort` (-u is POSIX), and `wc` are POSIX. Must NOT use: `awk '{print $3}'` with comma delimiter without specifying `-F,`, bash arrays, process substitution, etc.

---

## Scoring

| Tier | Questions | Max Points |
|------|-----------|------------|
| Tier 1 (Common) | Q1-Q5 | 10 |
| Tier 2 (Uncommon) | Q6-Q10 | 10 |
| Tier 3 (Obscure) | Q11-Q15 | 10 |
| Meta/Discrimination | Q16-Q20 | 10 |
| **Total** | **20** | **40** |

### Grading Guide
- **Correct (2):** Factually accurate, identifies POSIX compliance correctly
- **Partial (1):** Mostly right but misses POSIX-specific details or includes non-POSIX info without flagging it
- **Wrong (0):** Incorrect, hallucinates flags/behavior, confuses POSIX with GNU

### Result Thresholds
- **35-40:** LLM has strong POSIX knowledge (project may have limited value)
- **25-34:** Moderate gaps (project is useful for accuracy)
- **15-24:** Significant gaps (project is clearly needed)
- **0-14:** LLM is essentially guessing on POSIX (massive opportunity)
