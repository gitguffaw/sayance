---
status: complete
priority: p3
issue_id: "002"
tags: [code-review, docs, contributor-experience, process]
dependencies: []
---

# Add Contributing Guide And Issue Templates

The repository has detailed internal guidance in `AGENTS.md`, `CLAUDE.md`, and the docs set, but it does not yet expose a concise contributor contract or structured issue intake at the GitHub surface. That makes the project feel less finished than comparable repositories that package those entry points cleanly.

## Problem Statement

External contributors and evaluators should be able to answer three questions quickly:
- How do I contribute safely?
- What evidence do you expect with a bug report or feature request?
- Which validation commands are mandatory before proposing changes?

Right now that information exists, but it is distributed across project-specific docs rather than surfaced in the conventional places contributors look first.

## Findings

- The current repo does not have a `CONTRIBUTING.md`.
- The current repo does not have `.github/ISSUE_TEMPLATE/*`.
- The comparable `caveman` repo includes:
  - `CONTRIBUTING.md`
  - `bug_report.md`
  - `feature_request.md`
- Those files are not technically deep, but they improve professionalism and reduce ambiguity for drive-by contributors.
- Our repo already has stronger validation and documentation rules than `caveman`; the gap is discoverability, not substance.

## Proposed Solutions

### Option 1: Minimal Conventional Contributor Surface

**Approach:** Add a short `CONTRIBUTING.md` and two issue templates: bug report and feature request.

**Pros:**
- Fastest path to a more professional public surface
- Aligns with common GitHub expectations
- Reduces repeated clarification in issues

**Cons:**
- Adds docs to maintain
- Risk of duplicating guidance already captured elsewhere

**Effort:** 1-2 hours

**Risk:** Low

---

### Option 2: Contributor Guide Plus PR Template

**Approach:** Add `CONTRIBUTING.md`, issue templates, and a PR template that requires commands run and benchmark/evidence notes.

**Pros:**
- Stronger discipline for incoming changes
- Makes benchmark expectations explicit at review time

**Cons:**
- Slightly higher friction for casual contributors
- More repo metadata to maintain

**Effort:** 2-3 hours

**Risk:** Low

---

### Option 3: Keep GitHub Metadata Minimal, Improve README Instead

**Approach:** Expand README sections for contribution and reporting instead of adding GitHub-specific files.

**Pros:**
- Fewer files
- Keeps all public guidance centralized

**Cons:**
- Weaker conventional UX on GitHub
- Harder to enforce structured issue intake

**Effort:** 1-2 hours

**Risk:** Low

## Recommended Action

**To be filled during triage.**

## Technical Details

**Affected files:**
- `CONTRIBUTING.md` (new)
- `.github/ISSUE_TEMPLATE/bug_report.md` (new)
- `.github/ISSUE_TEMPLATE/feature_request.md` (new)
- `.github/pull_request_template.md` (optional)
- `README.md`

**Related components:**
- Public contributor onboarding
- Benchmark evidence requirements
- Validation workflow expectations

**Database changes (if any):**
- No

## Resources

- Comparable repo contributing guide: `https://github.com/JuliusBrussee/caveman/blob/main/CONTRIBUTING.md`
- Comparable repo issue templates:
  - `https://github.com/JuliusBrussee/caveman/blob/main/.github/ISSUE_TEMPLATE/bug_report.md`
  - `https://github.com/JuliusBrussee/caveman/blob/main/.github/ISSUE_TEMPLATE/feature_request.md`
- Local README: `README.md`
- Local process guidance: `AGENTS.md`

## Acceptance Criteria

- [x] A concise `CONTRIBUTING.md` exists in the repo root
- [x] The guide points contributors to the required validation commands
- [x] A bug-report template asks for reproduction, environment, and observed/expected behavior
- [x] A feature-request template asks for concrete use case and evaluation criteria
- [x] Optional: PR template asks for commands run and whether API-backed or live tests were executed
- [x] README links to the contributor guide

## Work Log

### 2026-04-14 - Comparative Repo Review

**By:** Codex

**Actions:**
- Reviewed the public repo surface for `caveman`.
- Compared GitHub metadata and contributor affordances against the current `posix` repo.
- Confirmed that our repo has stronger substantive docs but weaker conventional GitHub entry points.
- Captured the gap as a tracked improvement item.

**Learnings:**
- Public polish is partly about using expected repository conventions, not just having the right information somewhere in the tree.
- This is a low-effort improvement with outsized signaling value.

### 2026-04-14 - Implementation

**By:** Claude

**Actions:**
- Created `CONTRIBUTING.md` with quick start, validation requirements, contribution scope, PR process, and code style.
- Created `.github/ISSUE_TEMPLATE/bug_report.md` with reproduction steps, environment, and `make verify` output fields.
- Created `.github/ISSUE_TEMPLATE/feature_request.md` with use case and evaluation criteria fields.
- Created `.github/pull_request_template.md` with validation checklist and test details.
- Updated README with Contributing section and link.
- `make verify` passes all stages.

## Notes

- Keep this lightweight; the goal is discoverability, not duplicating `AGENTS.md` in full.
