---
status: complete
priority: p2
issue_id: "004"
tags: [code-review, testing, integrity, packaging]
dependencies: []
---

# Add Repo Structural Integrity Checks

The repo has strong product-path checks, but it does not yet have one canonical structural integrity check that validates source-of-truth artifacts, packaging metadata, and shipped executable surfaces together.

## Problem Statement

`caveman` ships a repo-level verifier pattern in `tests/verify_repo.py` that, despite currently failing locally, points at a useful category of protection: structural integrity across copied artifacts, manifests, syntax, and install surfaces.

We already verify the installed product well. What we do not yet verify in one place is that the repository itself remains internally coherent before installation.

This matters because:
- source files can drift silently
- packaging metadata can rot independently of core product logic
- public repo completeness is partly judged by whether structural checks exist and run

## Findings

- Existing coverage in `posix` is strong for installed-path behavior:
  - `scripts/test_product.sh`
  - `scripts/test_product_negative.sh`
- Existing coverage is weaker for repo-level integrity before installation.
- The merged comparative review identified `make test-repo` / `scripts/verify_repo.py` as a missing work item.
- Candidate checks include:
  - source artifact consistency
  - JSON parse validity
  - CLI executable sanity
  - installer path expectations
  - 155-utility completeness at the repo level

## Proposed Solutions

### Option 1: `scripts/verify_repo.py`

**Approach:** Add a Python verifier that performs repo-level checks and exits nonzero on drift or malformed metadata.

**Pros:**
- Easy to compose and extend
- Strong failure messages
- Good fit for structured checks and future CI use

**Cons:**
- Additional script surface to maintain
- Some checks may duplicate Install Testing logic if not scoped carefully

**Effort:** 2-4 hours

**Risk:** Low

---

### Option 2: `make test-repo` Backed By Small Shell/Python Helpers

**Approach:** Add a Make target that coordinates smaller existing or new helpers.

**Pros:**
- Simple UX
- Easy to integrate into `make verify`

**Cons:**
- Logic may become scattered
- Harder to keep error reporting consistent

**Effort:** 2-3 hours

**Risk:** Low

---

### Option 3: Fold Checks Into Existing Product Scripts

**Approach:** Expand `test_product.sh` and related scripts to include repo-level checks before install.

**Pros:**
- Fewer top-level commands
- Reuses existing shell test framework

**Cons:**
- Conflates repo integrity with installed-path conformance
- Makes failure intent less clear

**Effort:** 2-3 hours

**Risk:** Medium

## Recommended Action

**To be filled during triage.**

## Technical Details

**Affected files:**
- `scripts/verify_repo.py` or `scripts/test_repo.sh` (new)
- `Makefile`
- `README.md`
- `docs/test-and-regression.md`

**Related components:**
- `posix-core.md`
- `skill/SKILL.md`
- `skill/posix-tldr.json`
- installer entrypoints
- future CI workflow

**Database changes (if any):**
- No

## Resources

- Comparative synthesis: `docs/archive/comparisonReview/synthesis.md`
- Existing product-path checks:
  - `scripts/test_product.sh`
  - `scripts/test_product_negative.sh`
- Comparable pattern:
  - `https://github.com/JuliusBrussee/caveman/blob/main/tests/verify_repo.py`

## Acceptance Criteria

- [x] A dedicated repo-integrity command exists
- [x] It validates core artifact consistency at the source level
- [x] It validates JSON/metadata parseability
- [x] It validates shipped CLI executable assumptions
- [x] It validates 155-utility completeness from source artifacts
- [x] It is documented in README or regression docs
- [x] It is wired into the canonical verification command

## Work Log

### 2026-04-14 - Comparative Repo Review Synthesis

**By:** Codex

**Actions:**
- Merged Codex and Claude review outputs into a single synthesis document.
- Identified repo structural integrity checks as a missing tracked item.
- Recorded this gap as follow-up work.

**Learnings:**
- Product-path validation and repo-integrity validation are related but distinct.
- This is one of the clearest places to match `caveman`’s repo surface without inheriting its weaker maintenance story.

### 2026-04-14 - Implementation Complete

**By:** Claude + Codex

**Actions:**
- Created `scripts/verify_repo.py` with 6 check categories, 18 total assertions
- Checks: source artifact presence, JSON validity, 155-utility consistency (4 cross-checks), CLI executable sanity, installer sanity, fixture directory coverage
- Wired into `make test-repo` and `make verify`
- All 18/18 checks pass on current repo

**Learnings:**
- Utility extraction regex from test_product.sh (lines 53-80) was reused for consistency — same three patterns (bullet, comma-separated, SCCS-style).
- Repo integrity and installed-product integrity are cleanly separated: verify_repo.py checks source coherence, test_product.sh checks installed behavior.

## Notes

- This should be added before broadening distribution surfaces.
