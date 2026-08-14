# Sayance

*Semantic AnalYsis And Natural Command Engine*

In 1986, Jon Bentley challenged Donald Knuth — the legendary author of *The Art of Computer Programming* — to demonstrate his new literate-programming system (WEB) in the "Programming Pearls" column of *Communications of the ACM*. The task was simple: read a text file and output the N most frequently occurring words along with their counts, sorted by frequency.

Knuth delivered a meticulously engineered Pascal program that ran more than ten pages and hundreds of lines long. It was a masterpiece of custom data structures, thoughtful algorithms, and interwoven documentation — exactly the kind of beautiful, over-engineered solution a brilliant mind would build from scratch.

Doug McIlroy (Unix pioneer and inventor of the pipe) reviewed it. After polite praise, he demolished the entire effort by replacing Knuth's multi-page program with a six-line POSIX shell pipeline:

```sh
tr -cs A-Za-z '\n' |
tr A-Z a-z |
sort |
uniq -c |
sort -rn |
sed ${1}q
```

McIlroy didn't just solve the problem — he showed that the right combination of tiny, battle-tested command-line tools could outperform a hand-crafted masterpiece in elegance, speed, and maintainability.

That was 1986. Today, LLMs have the same blind spot Knuth had — they reach for bespoke solutions instead of the tools that are already there.

**LLMs don't know the shell tools that already exist.** They reach for `tar` when `pax` is right there. They write Python scripts to hex-dump a file instead of calling `od`. They reject `readlink` as "not POSIX" even though it's been standard since 2024. Every wrong tool is wasted tokens, wasted time, and a fragile non-portable script you now have to maintain.

**Sayance** fixes that with a two-layer reference injection system — and proves it works across Claude, Codex, and Gemini.
*Semantic AnalYsis And Natural Command Engine*

Sayance is an intentionally small skill plus lookup tool that helps coding agents choose
portable POSIX utilities instead of reaching for non-portable commands or
writing custom scripts.

LLMs often know that tools such as `comm`, `paste`, `pax`, `od`, `readlink`,
and `realpath` exist, but they do not reliably retrieve them at the moment they
would be useful. Sayance fixes that with two product artifacts:

- `skill/SKILL.md`: a compact Discovery Map of the 142 macOS-available
  POSIX.1-2024 utilities.
- `skill/sayance-lookup`: a zero-dependency Python CLI backed by
  `skill/sayance-tldr.json` for exact syntax and anti-pattern reminders.

## How It Works

### Discovery Map

The skill injects a semantic map into the agent context:

```text
awk: process via column/field logic
comm: compare sorted lines
pax: portable archive (NO tar)
od: dump octal/hex (NO xxd)
readlink: resolve symlink (IS POSIX)
```

This tells the agent what exists without loading full manual pages into the
context window.

### Syntax Lookup

When the agent identifies a utility that fits the task, it can call:

```bash
sayance-lookup <utility>
```

Examples:

```bash
$ sayance-lookup pax
  Create portable archive: pax -w -f archive.pax directory/
  Copy directory tree: pax -rw src/ dest/
  DO NOT USE tar (not guaranteed POSIX).

$ sayance-lookup sed
  Replace all occurrences: sed 's/foo/bar/g' file > tmp && mv tmp file
  DO NOT USE -i (not POSIX). Always use redirect and mv.
```

## Install

No virtualenv is required. Sayance uses Python 3 from the standard library.

The installer places `sayance-lookup` under `~/.local/bin`. Make sure that
directory is on your `PATH` before restarting your agent:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Install for both Claude Code and Codex:

```bash
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/v1.0.2/install.sh | bash
```

Install for one agent:

```bash
# Claude Code only
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/v1.0.2/install.sh | bash -s claude

# Codex only
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/v1.0.2/install.sh | bash -s codex
```

Track the current `main` branch instead of a release tag:

```bash
curl -fsSL https://raw.githubusercontent.com/gitguffaw/sayance/main/install.sh | SAYANCE_REF=main bash
```

## Source Install

```bash
git clone https://github.com/gitguffaw/sayance.git
cd sayance
make install         # both Claude Code and Codex
make install-claude  # Claude Code only
make install-codex   # Codex only
```

## Use

```bash
sayance-lookup pax
sayance-lookup --list
sayance-lookup --aliases
sayance-lookup --json od
sayance-lookup --version
```

After install, restart Claude Code or Codex so the skill file is loaded.

## Validate

```bash
make verify
```

This validates the public product surface: Python syntax, JSON syntax, utility
coverage, install/uninstall behavior, lookup behavior, and failure-injection
sensitivity.

Individual targets:

```bash
make test
make test-product
make test-product-negative
```

## Repository Map

| File | Purpose |
|------|---------|
| `skill/SKILL.md` | Agent skill with the Discovery Map and lookup instructions |
| `skill/sayance-lookup` | Syntax Lookup CLI |
| `skill/sayance-tldr.json` | Lookup examples and anti-patterns |
| `skill/VERSION` | Version shipped with the skill |
| `sayance-core.md` | Discovery Map source |
| `macOS-posix-utilities.txt` | 142-utility macOS POSIX scope |
| `install.sh` | Public installer |
| `scripts/test_product.sh` | Product install/uninstall validation |
| `scripts/test_product_negative.sh` | Product failure-injection validation |
| `scripts/uninstall-old-brand.sh` | Cleanup helper for old `posix` installs |

## Notes

- POSIX.1-2024 Issue 8 is the external standard.
- Sayance intentionally targets the 142 POSIX.1-2024 utilities available on
  macOS.
- `readlink`, `realpath`, and `timeout` are POSIX in Issue 8. Models trained on
  older material may incorrectly reject them.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
