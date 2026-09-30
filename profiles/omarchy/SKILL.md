---
name: sayance
description: Omarchy/Arch Linux command-line utility bridge. Use for shell scripting and file, text, archive, checksum, process, or package tasks when choosing between installed GNU/Linux tools and strict POSIX portability.
metadata:
  version: 1.1.0
  profile: omarchy
---

# Sayance for Omarchy

Choose shell utilities that fit the actual target. This machine runs Omarchy,
an Arch-based GNU/Linux system; strict POSIX is an optional portability target,
not the default local environment.

## Decision order

1. Follow repository instructions and host tool rules first. Sayance never
   overrides required tools, edit methods, authorization, or safety boundaries.
2. For a task that runs only on this Omarchy machine, prefer an installed
   GNU/Linux or Omarchy-native tool when it is clearer or more capable.
3. Use the POSIX Issue 8 baseline when the user requests portable `sh`, the
   script targets multiple Unix families, or the deployment environment is
   unknown.
4. When availability or flags matter, verify them with `command -v`, `--help`,
   `man`, or `sayance-lookup`; do not infer availability from this skill.

## Useful local choices

- Search files and text with `rg --files` and `rg` when available. Use POSIX
  `find` and `grep` only when portability is required.
- GNU `sed`, `awk`, `sort`, `xargs`, and Coreutils are available. GNU extensions
  such as `sed -i` are valid for local scripts, although repository editing
  instructions may still require `apply_patch`.
- Use `tar` or `bsdtar` with `gzip`, `xz`, or `zstd` for local archives. Do not
  replace them with `pax` or `compress` unless strict POSIX portability is the
  actual requirement.
- Use `sha256sum` or `b2sum` for strong file digests. POSIX `cksum` is useful for
  accidental-corruption checks, but it is not a cryptographic substitute.
- Use `jq` for JSON. Do not force JSON through `sed` or `awk` when structured
  parsing matters.
- Use Python or another suitable language when one shell pipeline would be
  harder to understand, validate, or maintain. Native utilities are a choice,
  not a prohibition on programming languages.

## Omarchy boundaries

- For packages, prefer `omarchy pkg add <pkg>` and
  `omarchy pkg aur add <pkg>`; use `omarchy update` for a full system update.
- Discover supported commands with `omarchy commands` or
  `omarchy <group> --help` rather than guessing a route.
- End-user desktop configuration belongs under the user's `~/.config/` paths.
  Never edit packaged files under `/usr/share/omarchy/`.
- Defer themes, Hyprland, shell/bar, terminal, display, capture, reminder, and
  other desktop customization details to the Omarchy skill.
- Sayance does not authorize package installation, privileged commands, config
  mutation, deletion, or other external side effects.

## POSIX reference lookup

Use the bundled lookup when exact portable syntax is useful:

```bash
sayance-lookup <utility>       # local guidance or POSIX syntax
sayance-lookup --list          # utilities in the portable reference
sayance-lookup --local-tools   # Omarchy tools and POSIX alternatives
sayance-lookup --json <name>   # machine-readable result
```

Lookup entries are a strict POSIX reference. A warning such as `NO -i` means
the flag is non-POSIX; it does not mean GNU `sed -i` is unavailable on Omarchy.

If `sayance-lookup` is not on `PATH`, use the copy under
`~/.claude/skills/sayance/` or `~/.codex/skills/sayance/`.
