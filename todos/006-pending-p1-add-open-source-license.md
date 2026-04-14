---
status: pending
priority: p1
issue_id: "006"
tags: [code-review, legal, open-source, release]
dependencies: []
---

# Add Open-Source License

The repository does not currently have a root `LICENSE` file. That blocks an open-source launch even if the code is made public, because reuse rights are not granted by default.

## Problem Statement

Publishing source without a license does not create a usable open-source project. It creates a visible codebase with unclear legal reuse terms.

This matters because:
- contributors need to know the legal terms for participation
- adopters need explicit permission to use, modify, and redistribute the project
- launch messaging is undermined if the repo is public but not actually licensed for open-source use

## Findings

- No root `LICENSE` file is present in the repo at the time of this review.
- The pre-launch synthesis and comparative review both identify this as a hard blocker for open-source launch.
- This is low effort but high consequence work.

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

**To be filled during triage.**

## Technical Details

**Affected files:**
- `LICENSE` (new)
- `README.md` (optional reference)
- `CONTRIBUTING.md` (optional reference after added)

**Related components:**
- open-source launch checklist
- contributor onboarding
- package/repo metadata

**Database changes (if any):**
- No

## Resources

- Launch synthesis: `docs/archive/cavemanReview/synthesis.md`
- Existing repo root contents

## Acceptance Criteria

- [ ] A root `LICENSE` file exists
- [ ] The chosen license is intentional and maintainer-approved
- [ ] README and future contributor docs do not conflict with the chosen license
- [ ] The repo can be published publicly with clear reuse terms

## Work Log

### 2026-04-14 - Launch Readiness Review

**By:** Codex

**Actions:**
- Reviewed launch-readiness requirements after the comparative repo analysis.
- Identified absence of a root `LICENSE` file as a hard open-source blocker.
- Added this tracked item so the pre-launch checklist is explicit.

**Learnings:**
- This is the smallest task on the launch checklist, but one of the few absolute blockers.

## Notes

- This should be completed before the larger CI/integrity workstream is considered "launch ready."
