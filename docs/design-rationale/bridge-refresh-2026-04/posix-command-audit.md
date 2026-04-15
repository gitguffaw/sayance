# POSIX.1-2024 (Issue 8) Utility Audit

**Standard**: IEEE Std 1003.1-2024 / The Open Group Base Specifications, Issue 8
**Published**: 14 June 2024
**Source for delta**: [ShellCheck PR #3307](https://github.com/koalaman/shellcheck/pull/3307)

## Issue 8 Changes from Issue 7

**Added (7)**: gettext, msgfmt, ngettext, readlink, realpath, timeout, xgettext
**Removed (12)**: fort77, qalter, qdel, qhold, qmove, qmsg, qrerun, qrls, qselect, qsig, qstat, qsub
**Significant new options on existing utilities**: xargs -0, read -d, various UTF-8 handling improvements

## Full Categorization (~155 utilities)

### Shell Builtins (27): not candidates for bridge
alias, bg, cd, command, eval, exec, exit, export, fc, fg, getopts, hash, jobs, kill, newgrp, read, readonly, return, set, shift, trap, type, ulimit, umask, unalias, unset, wait

### SCCS Family (10): obsolete version control, skip
admin, delta, get, prs, rmdel, sact, sccs, unget, val, what

### Obsolete/Specialized (12): skip
compress, uncompress, zcat, uucp, uustat, uux, uudecode, uuencode, talk, write, mesg, asa

### Interactive-Only (4): don't compose in pipes, skip
vi, ex, ed, more

### i18n Tools (4): narrow audience, optional bridge variant
gettext, ngettext, msgfmt, xgettext

### Dev Tools (9): narrow audience, optional bridge variant
ar, c99, cflow, ctags, cxref, lex, yacc, strip, nm

### LLMs Already Retrieve Reliably (~43): exclude from bridge (validate empirically per model)
awk, basename, bat/cat, chmod, chown, chgrp, cmp, cp, cut, date, dd, df, diff, dirname, du, echo, env, file, find, grep, head, id, ln, locale, ls, mailx, make, man, mkdir, mv, patch, printf, ps, pwd, rm, rmdir, sed, sleep, sort, tail, test, touch, tr, true, false, uname, uniq, wc

Note: This list is a hypothesis for frontier models. The "obvious" boundary must be validated empirically by running discovery tasks against the bare LLM and measuring >80% retrieval accuracy. Smaller models may only reliably retrieve ~25-30 of these.

### Bridge Candidates (~48): Core Syntax Lookup content

**Text Processing (12)**
| Command | Intent trigger | Notes |
|---------|---------------|-------|
| comm | lines unique to A vs B, set difference/intersection | requires sorted input |
| csplit | split file at lines matching a pattern | tricky '{*}' syntax |
| expand | convert tabs to spaces | |
| fold | wrap long lines to fixed width | |
| fmt | format text into simple paragraphs | |
| iconv | convert between character encodings | |
| join | relational join on shared field (like SQL JOIN) | requires sorted input |
| nl | number every line in a file | |
| paste | merge columns from files side by side | |
| pr | paginate output with headers/footers | |
| split | split file into N-line or N-byte chunks | |
| unexpand | convert spaces to tabs | |

**Binary/Inspection (5)**
| Command | Intent trigger | Notes |
|---------|---------------|-------|
| cksum | compute checksums | |
| od | hex/octal dump of binary data | |
| pathchk | check pathname validity/portability | |
| strings | extract printable strings from binary | |
| tput | terminal capability queries and control | |

**Computation/Logic (4)**
| Command | Intent trigger | Notes |
|---------|---------------|-------|
| bc | arbitrary-precision calculator | |
| expr | evaluate arithmetic/string expressions | |
| m4 | macro processing / text generation | |
| tsort | topological sort (dependency ordering) | |

**Process/Job Control (8)**
| Command | Intent trigger | Notes |
|---------|---------------|-------|
| at | schedule a one-time job | |
| batch | execute when load permits | |
| crontab | manage recurring scheduled jobs | |
| nice | run command at lower priority | |
| nohup | run command immune to hangups | |
| renice | change priority of running process | |
| tee | duplicate output to file and stdout | |
| xargs | build command lines from stdin | xargs -0 now POSIX in Issue 8 |

**File Operations (5)**
| Command | Intent trigger | Notes |
|---------|---------------|-------|
| link | create hard link (low-level) | |
| mkfifo | create named pipe | |
| pax | portable archive exchange (read/write tar/cpio) | |
| stty | set/get terminal attributes | |
| unlink | remove directory entry (low-level) | |

**System/User Info (5)**
| Command | Intent trigger | Notes |
|---------|---------------|-------|
| getconf | get system configuration values | |
| logger | log messages to system log | |
| logname | get login name | |
| tty | current terminal name | |
| who | who is logged in | |

**New in Issue 8 (3)**
| Command | Intent trigger | Notes |
|---------|---------------|-------|
| timeout | run command with time limit, kill if exceeded | New in Issue 8 |
| realpath | resolve symlinks, get canonical path | New in Issue 8 |
| readlink | read target of symbolic link | New in Issue 8 |

**Boundary cases: could go either way**
| Command | Issue | Notes |
|---------|-------|-------|
| xargs | May be "obvious" for engineers, not for casual users | Keep in bridge, measure lift |
| tee | Same as xargs | Keep in bridge, measure lift |
| cut | Well-known but frequently forgotten for field extraction | In "obvious" list but test |
| time | Shell builtin AND external utility | |
| lp | Printing; rare in modern contexts | Skip unless targeting sysadmin audience |
| tabs | Terminal tab stops; very rare | Skip |

## Summary

| Category | Count |
|----------|-------|
| Total Issue 8 utilities | ~155 |
| Shell builtins | 27 |
| SCCS (obsolete VCS) | 10 |
| Obsolete/specialized | 12 |
| Interactive-only | 4 |
| i18n tools (narrow) | 4 |
| Dev tools (narrow) | 9 |
| LLMs already retrieve | ~43 (hypothesis) |
| **Bridge candidates** | **~48** |
| Boundary cases | 6 |
