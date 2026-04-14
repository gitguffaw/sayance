---
status: complete
priority: p1
issue_id: "006"
tags: [code-review, legal, open-source, release]
dependencies: []
---

# Add Open-Source License

The repository now has a root `LICENSE` file using Apache License 2.0. This closed the last purely legal blocker for publishing the repo as open source.

## Problem Statement

Publishing source without a license does not create a usable open-source project. It creates a visible codebase with unclear legal reuse terms.

This mattered because:
- contributors need to know the legal terms for participation
- adopters need explicit permission to use, modify, and redistribute the project
- launch messaging is undermined if the repo is public but not actually licensed for open-source use

## Findings

- The repo previously had no root `LICENSE` file.
- Apache-2.0 was selected as the project license.
- The root `LICENSE` file has been added.
- README now includes a short license section for discoverability.

## Proposed Solutions

### Option 1: MIT

**Approach:** Add a standard MIT license.

**Pros:**
- Simple and widely understood
- Minimal adoption friction
- Common for tooling and benchmark repositories

**Cons:**
- Very permissive
- Offers little control over downstream commercial reuse

**Effort:** 5-10 minutes

**Risk:** Low

---

### Option 2: Apache-2.0

**Approach:** Add a standard Apache 2.0 license.

**Pros:**
- Widely accepted
- Includes explicit patent grant
- Good default for infrastructure/tooling projects

**Cons:**
- Longer and slightly heavier than MIT
- More text for casual contributors to parse

**Effort:** 5-10 minutes

**Risk:** Low

---

### Option 3: Defer Decision Pending Maintainer Preference

**Approach:** Decide license family explicitly before launch and commit the chosen file in the same change.

**Pros:**
- Avoids accidental defaulting
- Gives maintainers a deliberate legal choice

**Cons:**
- Delays launch if not resolved quickly
- Provides no value until completed

**Effort:** 10-30 minutes

**Risk:** Medium

## Recommended Action

Add a root `LICENSE` file with Apache License 2.0 and mention the choice in the README.

## Technical Details

**Affected files:**
- `LICENSE`
- `README.md`

**Related components:**
- open-source launch checklist
- contributor onboarding
- package/repo metadata

**Database changes (if any):**
- No

## Resources

- Launch synthesis: `docs/archive/comparisonReview/synthesis.md`
- Root `LICENSE`

## Acceptance Criteria

- [x] A root `LICENSE` file exists
- [x] The chosen license is intentional and maintainer-approved
- [x] README and future contributor docs do not conflict with the chosen license
- [x] The repo can be published publicly with clear reuse terms

## Work Log

### 2026-04-14 - Launch Readiness Review

**By:** Codex

**Actions:**
- Reviewed launch-readiness requirements after the comparative repo analysis.
- Identified absence of a root `LICENSE` file as a hard open-source blocker.
- Added this tracked item so the pre-launch checklist was explicit.

**Learnings:**
- This is the smallest task on the launch checklist, but one of the few absolute blockers.

### 2026-04-14 - Completion

**By:** Codex

**Actions:**
- Added Apache License 2.0 as the root project license.
- Added a short README license note.
- Marked this todo complete.

**Learnings:**
- Apache-2.0 is a strong default for a tooling project where the goal is permissive use with slightly stronger legal protection than MIT.

## Notes

- Completed before the larger CI/integrity workstream.
