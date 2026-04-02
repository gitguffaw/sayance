---
title: "AI-Generated Documentation Drift: Lifecycle Policy for Planning vs. Reference Docs"
category: workflow
date: 2026-04-02
tags:
  - documentation
  - ai-agents
  - lifecycle
  - drift
  - planning-docs
  - hygiene
symptom: "Docs describe a future state that never happened, a past state that no longer exists, or features that were cut — and nobody noticed until a human audited manually"
root_cause: "No convention distinguished provisional AI-authored planning content from ground-truth reference content. Reconciliation was never triggered after the speculative phase ended and real data became available."
---

# AI-Generated Documentation Drift

## Problem

When AI agents write documentation during a planning phase, they write confidently in the indicative mood. "Expected result: high token cost." "Gemini is temporarily excluded." "The MVP is one benchmark run away." This is not bad writing — it is accurate planning language. The problem is what happens next: the benchmark runs, results land, features get cut, and the docs don't change. The planning language calcifies into false reference content.

In this project, a ~1 hour audit was required to clean up docs that had drifted across two complete benchmark runs (Track 1 and Track 2, all three providers). The cleanup included:

- Replacing "expected result" tables with actual observed data
- Removing a Gemini exclusion notice that was no longer true
- Grounding a Codex step count claim that was speculative (8-10 steps, written pre-run — it turned out to be accurate, but it was stated as a known fact, not a hypothesis)
- Removing Tier 3 architecture from the architecture doc (Tier 3 was cut as YAGNI)
- Archiving a brainstorm and Phase 1 plan that were historical artifacts
- Deleting a patch script that had already been applied
- Rewriting a PRD whose implementation steps had unchecked boxes for work that was done

## Root Cause

AI agents operate in planning mode but produce output that gets filed in reference positions. Planning mode is inherently speculative — it describes a desired future. Reference docs must be empirical — they describe observed present state.

There was no structural separation between these two modes. Both lived in `docs/` with identical formatting and no lifecycle markers. A reader had no way to know whether a given sentence described something real or something hoped for.

Five specific contributing failures:

1. **No planning doc expiry.** Plans and brainstorms had no "this doc is done when..." condition. They lingered indefinitely.

2. **No post-run update step.** The benchmark workflow ended at `results/`. No checklist item triggered doc updates.

3. **Future tense in reference positions.** "Expected result:", "will produce", "is expected to" — planning language committed to files treated as architecture or reference documentation.

4. **Cut scope unrecorded.** Tier 3 was cut as YAGNI but there was no canonical "what was cut and why" record. The architecture doc described it as if it existed.

5. **One-shot scripts committed without deletion.** `patch_benchmark.py` served a single moment. Once applied, it became dead code with a misleading name.

## The Fix: Two Categories, Two Lifecycles

Every file in `docs/` belongs to exactly one category:

| Category | Examples | Rule |
|---|---|---|
| **REFERENCE** | architecture.md, benchmarks.md, CLAUDE.md, README | Updated in the same commit as the code/result that makes it false. Never speculative. |
| **PLANNING** | PRDs, brainstorms, implementation plans | Speculative by design. Archived or deleted when the work they describe is complete. |

These categories live in separate directories. Archive is gitignored.

```
docs/
  archive/          ← gitignored, planning artifacts that have served their purpose
  plans/            ← PLANNING: active plans only
  brainstorms/      ← PLANNING: active exploration only
  research/         ← REFERENCE: cited research backing design decisions
  solutions/        ← REFERENCE: observed problems and fixes
  architecture.md   ← REFERENCE
  benchmarks.md     ← REFERENCE
  test-and-regression.md ← REFERENCE
```

## Post-Run Checklist

Run this after every benchmark run that produces results.

**Immediate (before closing the terminal):**
- [ ] Did any result contradict a Known Issues entry? Update it with observed behavior and run date.
- [ ] Did any result confirm or refute a speculative claim? Replace it with observed fact.
- [ ] Did a planning doc's expiry condition get met? Fill in Outcome, move to `docs/archive/`.

**In the same commit as the results:**
- [ ] Does CLAUDE.md Known Issues still match reality? Each bullet should cite an observation.
- [ ] Are there one-shot scripts in the repo root that were run to produce this result? Delete them now.

**Before the next planning session:**
- [ ] Pull `docs/plans/`. Any plan whose work is complete needs to be archived before a new plan is created.

## Rules for AI-Generated Docs

AI agents write speculatively by default. Flag these patterns as unvalidated at review time:

| Pattern | Risk |
|---|---|
| "should produce", "will return", "is expected to" | Prediction, not observation |
| "likely", "probably", "may" | Hedging, not measurement |
| Numbers cited without a source run ID | Untracked provenance |
| "Based on the plan..." | Refers to planning doc, not reality |
| "Known Issues" entry without an observation date | Hypothesis, not a confirmed bug |

**Rule:** Every AI-generated doc must be reviewed before commit. Flagged phrases must either be replaced with observed facts, or explicitly labeled `[SPECULATIVE — verify after run]` inline.

**Known Issues entries specifically** require an observation tag:
```
- [OBSERVED 2026-04-01] Gemini CLI prepends "MCP issues detected..." — strip before JSON parsing.
```

An entry without a tag is a hypothesis. Treat it as planning content.

## Status Header for Planning Docs

Every file in `docs/plans/` and `docs/brainstorms/` should have this header:

```
Status: ACTIVE | SUPERSEDED
Expiry condition: [e.g., "when Track 2 benchmark run completes"]
Outcome: [blank while active — fill in when condition is met]
```

When the expiry condition is met: fill in Outcome, set Status to SUPERSEDED, move to `docs/archive/`.

## One-Shot Script Rule

Any script named `patch_*`, `migrate_*`, or `fix_once_*` is:
- Committed when created
- Deleted in the same commit or the next one after first successful run

The git history serves as the record. The working tree should not contain applied one-shot scripts.

```bash
python3 patch_benchmark.py       # run once, confirm result
git rm patch_benchmark.py        # delete immediately
git commit -m "chore: delete patch script after successful application"
```

## The Most Impactful Single Action

**Add a `Status:` header to every file in `docs/plans/` before the next work session.**

Not a new policy, not a new directory, not a script. Just open each file, decide if it is still guiding active work, and make the implicit lifecycle state explicit. You will discover which docs are already stale, which expiry conditions have already been met, and — most importantly — which docs you cannot assign an expiry condition to. Those are the ones that will drift again.

## Prevention Summary

The underlying failure: **AI agents write in reference mode when they are in planning mode.** The fix is not better AI writing. It is a structural separation of doc categories enforced by lifecycle rules, so planning artifacts cannot persist into reference positions.

```
Every benchmark run     →   Post-run checklist
Every planning doc      →   Status header + expiry condition
Every AI-written claim  →   Observed fact or explicit [SPECULATIVE] tag
Every one-shot script   →   Deleted after use
```
