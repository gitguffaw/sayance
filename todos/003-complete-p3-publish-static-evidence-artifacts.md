---
status: complete
priority: p3
issue_id: "003"
tags: [code-review, docs, benchmarks, presentation]
dependencies: []
---

# Publish Static Evidence Artifacts

The repo’s methodology is more rigorous than the comparison repo’s eval design, but that rigor is not as immediately inspectable from a cold read. We should expose a stable, curated evidence surface that lets a reviewer see proof artifacts quickly without committing raw benchmark result directories.

## Problem Statement

`caveman` presents itself very well to a casual reviewer:
- polished README
- committed eval snapshot
- static `docs/index.html`
- obvious install surfaces and packaging artifacts

Our repo is methodologically stronger, but a new reviewer has to read prose and trust that the benchmark evidence exists. We should shorten that trust gap with checked-in, intentionally curated evidence artifacts.

## Findings

- `caveman` ships committed public evidence artifacts such as `evals/snapshots/results.json` and `docs/index.html`.
- `caveman` also documents important evaluation limitations in `evals/README.md`, including lack of fidelity measurement, lack of cross-model testing, approximate tokenization, and no statistical significance.
- Our repo already has better benchmark methodology and stronger product-path validation, but `results/` is gitignored and there is no committed evidence bundle beyond README tables and reference docs.
- This means our rigor is real, but not surfaced as quickly for an external evaluator.
- Known pattern: documentation drift is a project risk, so any checked-in evidence artifact needs an explicit update policy.

## Proposed Solutions

### Option 1: Curated Evidence Markdown In `docs/`

**Approach:** Add a hand-maintained or generated `docs/evidence.md` that links a canonical run date, model versions, summary tables, and selected screenshots/HTML artifacts.

**Pros:**
- Simple and readable in GitHub
- Easier to keep aligned with doc lifecycle rules
- No binary artifact pressure

**Cons:**
- More manual upkeep unless partially generated
- Less visually immediate than committed HTML

**Effort:** 2-4 hours

**Risk:** Low

---

### Option 2: Export A Stable Public Evidence Bundle

**Approach:** Add a script that produces a curated `docs/evidence/` bundle from a chosen run: summary JSON excerpt, comparison HTML, and a concise index page.

**Pros:**
- Strongest presentation
- Makes the repo feel more complete to outside reviewers
- Can be refreshed intentionally at milestone points

**Cons:**
- Higher maintenance surface
- Must guard against doc/result drift

**Effort:** 4-6 hours

**Risk:** Medium

---

### Option 3: README-Only Upgrade

**Approach:** Keep artifacts gitignored, but improve README with a clearly labeled “Evidence Pack” section containing dated run IDs, commands used, and exact sample outputs.

**Pros:**
- Lowest maintenance
- Keeps repo simpler

**Cons:**
- Weakest discoverability after the README
- Less reusable than a dedicated docs surface

**Effort:** 1-2 hours

**Risk:** Low

## Recommended Action

**To be filled during triage.**

## Technical Details

**Affected files:**
- `docs/evidence.md` or `docs/evidence/*` (new)
- `README.md`
- Optional export script under `scripts/`
- `docs/solutions/workflow/ai-doc-lifecycle-drift.md` may need cross-reference in process docs

**Related components:**
- Benchmark publication
- Reviewer onboarding
- Release-quality presentation

**Database changes (if any):**
- No

## Resources

- Comparable repo evidence surfaces:
  - `https://github.com/JuliusBrussee/caveman/tree/main/evals`
  - `https://github.com/JuliusBrussee/caveman/blob/main/evals/snapshots/results.json`
  - `https://github.com/JuliusBrussee/caveman/blob/main/docs/index.html`
- Local README: `README.md`
- Known pattern: `docs/solutions/workflow/ai-doc-lifecycle-drift.md`

## Acceptance Criteria

- [x] A committed, reviewer-friendly evidence surface exists outside `results/`
- [x] It identifies the exact run date and model versions behind the published numbers
- [x] It clearly distinguishes curated evidence from live/generated result directories
- [x] It links back to the commands or process used to produce the artifact
- [x] It includes a drift-prevention note or update policy
- [x] README links to the evidence surface

## Work Log

### 2026-04-14 - Comparative Repo Review

**By:** Codex

**Actions:**
- Compared the cold-read reviewer experience of `caveman` and `posix`.
- Identified that `caveman` exposes more immediately inspectable evidence artifacts despite weaker underlying methodology.
- Mapped that gap into a presentation-focused improvement for `posix`.

**Learnings:**
- External credibility is partly determined by how quickly a reviewer can inspect evidence, not only by how rigorous that evidence is.
- Any committed evidence layer must be designed with explicit anti-drift rules.

### 2026-04-14 - Implementation

**By:** Claude

**Actions:**
- Created `docs/evidence.md` with canonical run date, model versions, compliance/token tables, exact commands, reproduction steps, limitations, and update policy.
- Updated README Further Reading section with link to evidence page.
- Chose Option 1 (curated markdown) — simplest to maintain, readable on GitHub, no binary artifacts.

## Notes

- Do not solve this by committing raw `results/` directories. Keep the artifact intentionally curated.
