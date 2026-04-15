# macOS-Excluded POSIX Utilities

POSIX.1-2024 (Issue 8) defines 155 utilities. The bridge ships 142 — the subset that Apple ships on macOS. This document explains the 13 exclusions.

## Why exclude them?

The bridge's target audience is developers using Claude Code, Codex, and similar LLM agents on macOS. Recommending a utility that doesn't exist on the user's system is worse than not recommending it at all — the user gets `command not found`, loses trust in the bridge, and wastes time debugging a tool problem instead of solving their actual task.

## The 13 excluded utilities

### SCCS version control (9 utilities)

`admin`, `delta`, `get`, `prs`, `rmdel`, `sact`, `sccs`, `unget`, `val`

SCCS (Source Code Control System) is AT&T System V heritage. macOS derives from BSD, which never included SCCS in its base system. Apple has never shipped these utilities on any version of Mac OS X or macOS. No Homebrew formula exists; the closest alternative is CSSC (GNU SCCS clone) via MacPorts.

Nobody is asking an LLM for SCCS commands in 2026. Risk of omission: effectively zero.

### C analysis tools (2 utilities)

`cflow`, `cxref`

Static analysis tools for C source code. Apple does not ship them and never has. `cflow` is available via Homebrew (`brew install cflow`); `cxref` is MacPorts-only. Developers use Xcode's built-in analysis or standalone tools like `clang-tidy`.

### C compiler — POSIX Issue 8 name (1 utility)

`c17`

POSIX Issue 8 renamed the C compiler command from `c99` (Issue 7) to `c17` to reflect the C17 standard. Apple ships `c89` and `c99` wrappers around clang but has never created a `c17` wrapper. No package manager provides one either. Developers invoke `clang -std=c17` directly.

### timeout (1 utility)

`timeout`

Runs a command with a time limit. Added to POSIX in Issue 8 (2024), but originates from GNU coreutils. Apple has never shipped it. Available via `brew install coreutils` as `gtimeout` (prefixed to avoid BSD conflicts).

This is the highest-risk exclusion — `timeout` is a common use case. Including it would cause `command not found` on every Mac. The bridge omits it rather than recommend a broken command.

## Future: Ubuntu/Linux support

These 13 utilities are available on Ubuntu and other Linux distributions. A future release will add platform-aware bridge support to include them on Linux systems. Tracked in Linear as a project milestone.

## Also fixed

`od` (octal dump): The TLDR entry previously recommended `-t x1z`. The `z` suffix (ASCII sidebar) is a GNU extension, not part of the POSIX specification, and macOS `od` rejects it with `unrecognised format character`. Corrected to `-t x1`.
