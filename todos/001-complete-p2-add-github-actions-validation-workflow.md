---
status: complete
priority: p2
issue_id: "001"
tags: [code-review, ci, testing, process]
dependencies: []
---

# Add GitHub Actions Validation Workflow

The repo has strong local validation, but no committed GitHub Actions workflow to run that validation automatically on pushes and pull requests. That makes the project look less complete than it is and leaves regression prevention dependent on manual discipline.

## Problem Statement

Our local testing story is now materially stronger than the comparable `caveman` repo, but that strength is not automated in the public repository surface. A reviewer can see the commands in docs, but cannot see that they are enforced anywhere.

This matters for both quality and professionalism:
- Quality: regressions can slip if someone forgets to run the full matrix locally.
- Professionalism: absence of CI makes the repo look less mature than its actual engineering rigor.
- Comparison: `caveman` ships GitHub workflow automation for artifact syncing, even though it does not appear to run its verification suite in CI. We should exceed that bar, not match it.

## Findings

- The current repo has no committed `.github/workflows/*` files.
- Local validation is explicit and executable:
  - `python3 -m py_compile run_benchmark.py benchmark_core/*.py`
  - `python3 -m unittest`
  - `make test-product`
  - `make test-product-negative`
- These commands passed during this review on 2026-04-14.
- The comparable repo has only a sync workflow at `caveman/.github/workflows/sync-skill.yml`; it does not appear to run `tests/test_hooks.py` or `tests/verify_repo.py` in CI.
- `caveman/tests/verify_repo.py` failed locally on 2026-04-14 with `activation output missing caveman banner`, which reinforces the need to actually exercise repository verification automatically rather than rely on a one-off local script.

## Proposed Solutions

### Option 1: Single CI Workflow For All Core Checks

**Approach:** Add one GitHub Actions workflow that runs syntax checks, unit tests, and Install Testing product-path checks on every push and pull request.

**Pros:**
- Simple public signal of repo health
- Minimal maintenance surface
- Makes current discipline visible and repeatable

**Cons:**
- Slower workflow if every job runs serially
- Install Testing shell checks may need careful runner assumptions

**Effort:** 2-4 hours

**Risk:** Low

---

### Option 2: Split Fast And Full Workflows

**Approach:** Add a fast workflow for `py_compile` + `unittest` and a second workflow for Install Testing product conformance.

**Pros:**
- Faster feedback for ordinary changes
- Clear separation between logic tests and shipped-product validation

**Cons:**
- More YAML and more workflow surface area
- Slightly more cognitive overhead for contributors

**Effort:** 3-5 hours

**Risk:** Low

---

### Option 3: Add A Single `make verify` Command First, Then CI

**Approach:** Create a unified local entrypoint first, then have GitHub Actions invoke that one command.

**Pros:**
- One canonical validation command for humans and CI
- Keeps workflow YAML simpler

**Cons:**
- Adds an extra indirection layer before CI exists
- Still requires the GitHub workflow as a second step

**Effort:** 3-4 hours

**Risk:** Low

## Recommended Action

**To be filled during triage.**

## Technical Details

**Affected files:**
- `.github/workflows/*.yml` (new)
- `Makefile` (optional, if adding `make verify`)
- `README.md`
- `docs/test-and-regression.md`

**Related components:**
- Simulation Testing benchmark validation
- Install Testing installed product-path conformance
- Future release/review workflow

**Database changes (if any):**
- No

## Resources

- Comparable repo workflow: `https://github.com/JuliusBrussee/caveman/blob/main/.github/workflows/sync-skill.yml`
- Comparable repo local verifier: `https://github.com/JuliusBrussee/caveman/blob/main/tests/verify_repo.py`
- Local regression guide: `docs/test-and-regression.md`
- Known pattern: `docs/solutions/workflow/ai-doc-lifecycle-drift.md`

## Acceptance Criteria

- [x] A GitHub Actions workflow exists for push and pull_request events
- [x] The workflow runs `python3 -m py_compile run_benchmark.py benchmark_core/*.py`
- [x] The workflow runs `python3 -m unittest`
- [x] The workflow runs `make test-product`
- [x] The workflow runs `make test-product-negative`
- [x] README or regression docs mention the workflow and its scope
- [x] Workflow passes on the default branch

## Work Log

### 2026-04-14 - Comparative Repo Review

**By:** Codex

**Actions:**
- Reviewed `caveman` packaging, tests, and workflow surface.
- Confirmed `caveman` has sync automation but no visible CI test execution workflow.
- Ran local `posix` validation commands successfully:
  - `python3 -m py_compile run_benchmark.py benchmark_core/*.py`
  - `python3 -m unittest`
  - `make test-product`
  - `make test-product-negative`
- Converted the gap into a tracked improvement item.

**Learnings:**
- Our test rigor is already stronger than the comparison repo’s public enforcement surface.
- The main weakness is visibility and automation, not missing local checks.

### 2026-04-14 - Implementation Complete

**By:** Claude + Codex

**Actions:**
- Created `.github/workflows/ci.yml` running `make verify` on push and PR to main
- `make verify` runs: py_compile, unittest, test-repo, test-product, test-product-negative
- Created `scripts/verify_repo.py` with 18 structural integrity checks (6 categories)
- Added `make test-repo` and `make verify` Makefile targets
- Updated `docs/test-and-regression.md` and `AGENTS.md` with new commands
- All checks pass locally (18/18 repo integrity, 37 unit tests, 33/33 product conformance, 4/4 failure injection)

**Learnings:**
- Single `make verify` entrypoint keeps CI and local validation identical — no drift risk.
- CI runs for visibility only on current GitHub plan (merge gating unavailable for private repos on free tier).

## Notes

- This is the highest-value professionalism improvement surfaced by the comparison.
