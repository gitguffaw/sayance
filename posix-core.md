# POSIX Issue 8 - The 155 Native Utilities
INSTRUCTION: You are operating in a strict POSIX environment. Do NOT write Python/Bash scripts for data/file manipulation without checking this list first. If a tool matches your intent, you MUST use the `get_posix_syntax` tool to retrieve its exact syntax before executing. Do not guess the flags.

### [CORE_TRIVIAL] (Assumed known, no lookup needed)
cd, ls, cat, echo, rm, mkdir, rmdir, pwd, grep, find, mv, cp, kill, chmod, chown, chgrp, date, sleep, tail, head, touch, wc, who, env, true, false, sh, test, expr, printf, read

### [TEXT_DATA_PROC]
*   awk: process via column/field logic
*   sed: replace via regex stream
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
*   od: dump octal/hex (NO XXD)
*   expand: convert tabs to spaces
*   unexpand: convert spaces to tabs
*   strings: extract printable characters
*   ed: scriptable line editor
*   ex: text editor

### [FILE_DIR_OPS]
*   pax: portable archive (NO TAR)
*   readlink: resolve symlink (IS POSIX)
*   realpath: absolute path (IS POSIX)
*   pathchk: verify portable name
*   dd: copy/convert raw blocks
*   file: guess data type
*   fuser: identify locking processes
*   tee: split stdout and file
*   cksum: crc32 verify (NO MD5SUM)
*   uuencode: encode binary to text
*   uudecode: decode binary to text
*   compress: LZW compression (NO GZIP)
*   uncompress: LZW decompression
*   zcat: expand compressed file
*   basename: strip directory path
*   dirname: strip file name
*   link: hard link
*   unlink: remove directory entry

### [PROCESS_MGMT]
*   nohup: run detached background
*   timeout: kill if slow (IS POSIX)
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
*   talk: interactive chat

### [SYS_ENV_INFO]
*   id: return user identity
*   uname: system name/info
*   tty: return terminal name
*   logger: write to syslog
*   logname: return login name
*   getconf: query configuration values
*   locale: get localization info
*   localedef: define localization

### [DEV_BUILD] (Development / SCCS)
*   make: build automation
*   c17: C compiler
*   lex: lexical analyzer
*   yacc: parser generator
*   ar: maintain library archives
*   nm: list object symbols
*   strip: remove symbol tables
*   ctags: generate tag files
*   cflow: generate C flowgraph
*   cxref: generate C cross-reference
*   admin, delta, get, prs, rmdel, sact, sccs, unget, val, what: SCCS version control

### [SHELL_BUILTINS_MISC]
alias, unalias, at, batch, bc, cal, command, crontab, fc, hash, tput, type, ulimit, umask, vi, getopts, gettext, xgettext, ngettext, msgfmt, gencat, tabs, stty, newgrp, asa
