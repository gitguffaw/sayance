---
status: pending
priority: p3
issue_id: "005"
tags: [code-review, distribution, packaging, docs]
dependencies: ["001", "004"]
---

# Add Multi-Agent Distribution Surfaces

The current project is strong on Claude Code and Codex, but it does not yet expose lightweight packaging for adjacent agent environments where the core bridge concept could still be useful.

## Problem Statement

`caveman` looks broader and more finished because it ships packaging and rules for multiple agent surfaces. That is a real distribution advantage, even if it is not the core reason their repo feels polished.

For `posix`, multi-agent distribution should be treated as a third-order improvement:
- useful for reach
- useful for perceived completeness
- not a substitute for verification

## Findings

- Current install surface focuses on Claude Code and Codex.
- Comparative synthesis identified Gemini CLI packaging and Cursor/Windsurf rules as the lowest-effort, highest-visibility distribution additions.
- Multi-agent support is a distribution gap, not a methodological gap.
- This work should come after CI and repo-integrity checks so new surfaces do not outpace verification.

## Proposed Solutions

### Option 1: Minimal Expansion

**Approach:** Add Gemini CLI extension metadata plus Cursor and Windsurf rule files only.

**Pros:**
- Lowest maintenance expansion
- Closes the most visible packaging gap
- Enough to demonstrate broader applicability

**Cons:**
- Still leaves many agent surfaces unsupported
- Requires decisions about auto-activation behavior and scope

**Effort:** 2-4 hours

**Risk:** Low

---

### Option 2: Add A Small Packaging Matrix

**Approach:** Add Gemini, Cursor, Windsurf, and one generic `npx skills` or equivalent distribution path if applicable.

**Pros:**
- Stronger parity with comparison repo’s public surface
- Better README install matrix

**Cons:**
- Higher maintenance cost
- More packaging metadata to keep in sync

**Effort:** 4-6 hours

**Risk:** Medium

---

### Option 3: Defer Packaging, Improve Docs Only

**Approach:** Document how the skill could be adapted to other agents without shipping maintained packaging.

**Pros:**
- Minimal maintenance
- Avoids premature support promises

**Cons:**
- Weakest external signal
- Does not materially close the visible gap

**Effort:** 1-2 hours

**Risk:** Low

## Recommended Action

**To be filled during triage.**

## Technical Details

**Affected files:**
- packaging metadata files (new)
- agent-specific rule/config files (new)
- `README.md`
- possibly installer or docs scripts

**Related components:**
- current `install.sh`
- current `Makefile` install targets
- future CI and repo-integrity checks

**Database changes (if any):**
- No

## Resources

- Comparative synthesis: `docs/archive/comparisonReview/synthesis.md`
- Comparable packaging examples:
  - `.claude-plugin/plugin.json`
  - `plugins/caveman/.codex-plugin/plugin.json`
  - `gemini-extension.json`
  - Cursor/Windsurf rule files in the `caveman` repo

## Acceptance Criteria

- [ ] Scope is explicitly limited to a small, maintainable set of agent surfaces
- [ ] At least one additional agent packaging surface is added beyond Claude/Codex
- [ ] README documents install/use for the newly supported surface(s)
- [ ] New surfaces are covered by verification or at minimum structural checks
- [ ] Distribution claims remain narrower than actual tested support

## Work Log

### 2026-04-14 - Comparative Repo Review Synthesis

**By:** Codex

**Actions:**
- Compared `caveman`’s distribution breadth with `posix`’s current install surface.
- Recorded multi-agent expansion as a follow-up item, intentionally sequenced after verification work.

**Learnings:**
- Packaging breadth changes how complete a repo feels to outsiders.
- It should follow verification maturity, not precede it.

## Notes

- Do not start this until CI and repo-integrity work are in place.
