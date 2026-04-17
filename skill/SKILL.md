---
name: sayance
version: 1.0.0
description: POSIX Issue 8 utility bridge — fixes LLM blindness to the 142 POSIX.1-2024 utilities available on macOS. Auto-activates when tasks involve file manipulation, text processing, archiving, process management, or shell scripting. Injects semantic map + provides CLI lookup for exact syntax.
---

# Sayance

You are operating in an environment with access to POSIX.1-2024 (Issue 8) utilities. Before writing Python/Bash scripts for file or data manipulation, check whether a native POSIX utility handles it.

## Discovery Map — What Exists

### [CORE_TRIVIAL] (Assumed known, no lookup needed)
cd, ls, cat, echo, rm, mkdir, rmdir, pwd, grep, find, mv, cp, ln, kill, chmod, chown, chgrp, date, sleep, tail, head, touch, wc, who, env, true, false, sh, test, expr, printf, read, more, man

### [TEXT_DATA_PROC]
*   awk: process via column/field logic
*   sed: replace via regex stream (NO -i flag)
*   comm: compare sorted lines
*   join: merge on shared key
*   cut: extract fixed columns
*   tr: translate 1-to-1 characters
*   sort: order lines
*   uniq: filter adjacent duplicates
*   paste: combine side-by-side
*   split: divide by line/byte size
*   csplit: divide by regex context
*   nl: prepend line numbers
*   fold: wrap width
*   pr: paginate output
*   cmp: compare raw bytes
*   diff: compare text blocks
*   patch: apply diff block
*   iconv: convert character encoding
*   od: dump octal/hex (NO xxd)
*   expand: convert tabs to spaces
*   unexpand: convert spaces to tabs
*   strings: extract printable characters
*   tsort: topological sort (dependency order)
*   xargs: build commands from stdin
*   ed: scriptable line editor
*   ex: text editor

### [FILE_DIR_OPS]
*   pax: portable archive (NO tar)
*   readlink: resolve symlink (IS POSIX)
*   realpath: absolute path (IS POSIX)
*   pathchk: verify portable name
*   dd: copy/convert raw blocks
*   file: guess data type
*   fuser: identify locking processes
*   tee: split stdout and file
*   cksum: crc32 verify (NO md5sum)
*   uuencode: encode binary to text
*   uudecode: decode binary to text
*   compress: LZW compression (NO gzip)
*   uncompress: LZW decompression
*   zcat: expand compressed file
*   basename: strip directory path
*   dirname: strip file name
*   link: hard link
*   unlink: remove directory entry

### [PROCESS_MGMT]
*   nohup: run detached background
*   ps: list process state
*   jobs: list background tasks
*   bg: resume in background
*   fg: bring to foreground
*   wait: await process completion
*   nice: lower scheduling priority
*   renice: alter running priority
*   time: measure execution duration

### [IPC_COMM]
*   mkfifo: create named pipe
*   ipcrm: remove message queue
*   ipcs: list IPC facilities
*   mailx: send/receive email
*   mesg: permit terminal write
*   write: message another user
*   lp: send to print queue
*   talk: interactive chat
uucp, uustat, uux

### [SYS_ENV_INFO]
*   df: report filesystem space
*   du: estimate file space usage
*   id: return user identity
*   uname: system name/info
*   tty: return terminal name
*   logger: write to syslog
*   logname: return login name
*   getconf: query configuration values
*   locale: get localization info
*   localedef: define localization

### [DEV_BUILD] (Development)
*   m4: general macro processor
*   make: build automation
*   lex: lexical analyzer
*   yacc: parser generator
*   ar: maintain library archives
*   nm: list object symbols
*   strip: remove symbol tables
*   ctags: generate tag files
*   what: extract identification strings

### [SHELL_BUILTINS_MISC]
alias, unalias, at, batch, bc, cal, command, crontab, fc, hash, tput, type, ulimit, umask, vi, getopts, gettext, xgettext, ngettext, msgfmt, gencat, tabs, stty, newgrp, asa

## Syntax Lookup — How To Use It

When you identify a utility above that fits the task, get exact syntax BEFORE executing:

```bash
sayance-lookup <utility>
```

This returns POSIX-correct syntax, canonical examples, and critical anti-patterns (e.g., "DO NOT USE -i"). Do not guess flags — look them up.

If `sayance-lookup` is not available on this machine, the data file is usually at one of:
- `~/.claude/skills/sayance/sayance-tldr.json`
- `~/.codex/skills/sayance/sayance-tldr.json`
