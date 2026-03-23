# POSIX LLM Benchmark v0 — Questions Only

Answer each question. Be specific about POSIX compliance vs GNU/BSD extensions.

---

## Tier 1: Common Commands

**Q1:** What exactly does `sort -k 2,2` do? How does it differ from `sort -k 2`?

**Q2:** Is `sed -i` POSIX-compliant?

**Q3:** Write a POSIX-compliant command to find all `.conf` files modified in the last 24 hours.

**Q4:** Which of these grep flags are POSIX-compliant: -i, -r, -P, -E, -o, -w, -c, -l, -n?

**Q5:** Why does POSIX recommend `printf` over `echo` for portable scripts?

---

## Tier 2: Uncommon Commands

**Q6:** What is `pax` and why does POSIX specify it instead of `tar`?

**Q7:** What does `tsort` do? Give a concrete use case.

**Q8:** Write a POSIX-compliant command to display a file as hexadecimal bytes.

**Q9:** What does `pathchk` do and when would you use it?

**Q10:** What is `m4` and why is it in the POSIX spec?

---

## Tier 3: Obscure Commands

**Q11:** What is SCCS? Name 3 SCCS-related POSIX utilities and what they do.

**Q12:** What is `fort77`?

**Q13:** What does `qsub` do in POSIX? Name 3 other `q*` utilities.

**Q14:** What does `cxref` do?

**Q15:** What does `asa` do and what problem does it solve?

---

## Meta: POSIX Awareness

**Q16:** Is `tar` a POSIX utility?

**Q17:** Which of these are NOT POSIX utilities: ls, wget, curl, top, less, vim, ssh, awk, sudo, which?

**Q18:** What exit codes does `test` (aka `[`) return according to POSIX?

**Q19:** How many utilities does the POSIX spec define?

**Q20:** Write a POSIX-compliant script (no bashisms, no GNU extensions) that reads a CSV file, extracts the 3rd column, sorts it uniquely, and counts the results.
