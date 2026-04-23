# Git-History Retrospective: Gotchas, Mistakes, and Execution Misses

Scope: this list is intentionally commit-history-first, with lightweight specificity.
Where helpful, I include commit hashes/PR references as anchors.

## A) Product Framing, Scope, and Decision Quality

1. We spent early cycles benchmarking before product-path hardening, then had to realign intent around solving POSIX blindness (`a2550b6`).
2. README framing whiplashed multiple times (problem-first vs solution-first), signaling strategy churn (`efd18d5`, `7d14a1e`).
3. We repeatedly adjusted benchmark narrative after results landed, not before (docs catch-up pattern across `306a709`, `5465e15`, `9591bf8`).
4. We initially treated simulation outcomes as closer to production truth than they were (later corrected in `565f430`).
5. We introduced Track/Lane nomenclature and later simplified wording; this suggests conceptual overhead debt (`aafa9a1`).
6. Financial language had to be explicitly removed to stop metric confusion (`e533a50`).
7. We had to clarify repeatedly that benchmark is support tooling, not product value itself (`a2550b6`, `CLAUDE.md` updates).
8. We carried stale planning/brainstorm artifacts too long before archiving (`6346101`).
9. Public-release messaging required late-stage cleanup instead of being maintained continuously (`ffd015e`, `a69e640`).
10. We needed explicit governance sync rules because docs diverged often enough to become a risk (`d6f75c4`, `AGENTS.md`/`CLAUDE.md`).
11. We shipped wording that over-implied confidence, then requalified with confounds in evidence docs (`0d03fd2`, `docs/evidence.md`).
12. We kept discovering that "historical continuity" and "scientific comparability" were not the same thing (`565f430` rerun notes).

## B) Benchmark/Prompt Contract and Evaluation Design

13. The simulated bridge contract (`get_posix_syntax`) drifted from shipped behavior; we had to repair to real CLI contract (`565f430`).
14. Codex benchmark framing allowed local-host inspection behavior and stalls before BENCHMARK MODE tightening (`ffa97ef`, `565f430`).
15. Prompt contracts evolved faster than docs, creating short-term interpretation mismatch (`34155c7` as catch-up docs commit).
16. We assumed bridge would strongly drive lookup-call frequency; data showed lookup usage was sparse (Wave-3 notes).
17. We shipped regression fixes to command extraction multiple times, implying fragile parser assumptions (`6ff2f47`, `a57d0da`).
18. Tier/layer semantics were initially misstated (simulated vs MCP), then corrected (`5d8effa`).
19. We had to rename "failure modes" to "inefficiency modes" to reduce semantics drift (`58c0487`).
20. We needed hard model pinning after running into comparability risk from drifting defaults (`c2ef476`).
21. Unpinned model usage had to become explicit opt-in, which should have been baseline from day one (`c2ef476`).
22. Comparison report semantics needed repeated tightening and retention rules (`f83fdb4`).
23. A docs-only follow-up commit was required because reporting-change docs were initially missed (`34155c7`).
24. We found that text-analysis success can overstate real execution correctness; execute-mode had to be elevated (`9e56d92`).
25. Partial fixture coverage means some benchmark claims remain non-end-to-end (`docs/test-and-regression.md`: T31–T40 unverified).
26. We had to add bridge validation gates after discovering drift risk in injected reference layers (`0dd04e9`, `282939a`).
27. Table/chart UX broke in docs (Mermaid replacement) and had to be patched, suggesting brittle presentation path (`a94ff92`).
28. Reporting UI overflow bug made outputs harder to review until fixed (`58564b1`).

## C) Provider Runtime Integration and CLI Assumptions

29. Gemini JSON parsing repeatedly needed hardening due to noisy prefixes/schema variation (`3817368`, Known Issues).
30. Gemini quota assumptions had to be codified conservatively after practical run limits surfaced (`docs/benchmarks.md`, `CLAUDE.md`).
31. Claude cache semantics were misunderstood enough to require parser corrections (`9c8fa6a`).
32. Codex token parsing experienced schema drift and needed dedicated resilience fixes (`80514b6`).
33. Timeout stderr bytes/str handling broke parser paths until fixed (`7224ad4`).
34. Codex usage snapshot merging was wrong and later corrected (`3da0a38`).
35. Validity was too tightly coupled to billable-token gates before decoupling (`34bca58`).
36. Tool-simulation adjustment capture had diagnostic errors and required correction (`e6ca23e`).
37. We had to isolate stdin to stop Codex CLI blocking in benchmark runs (`565f430`/Known Issues context).
38. We repeatedly discovered provider-specific edge behavior after the fact rather than pre-encoding adapters.
39. Provider parity assumptions were optimistic; each CLI needed its own robustness envelope.
40. We learned the hard way that CLI contract stability is as important as prompt quality in agentic systems.

## D) Data Integrity, Fixtures, and Artifact Discipline

41. Fixture expansion happened in phases, leaving temporary blind spots in command verification (`8c00d85`).
42. Broken fixtures and test gaps required explicit closure work (`9597156`).
43. Symlink behavior in fixture setup was wrong and needed preserving fix (`1151368`).
44. Generated artifact handling needed cleanup and untracking (`1857bf7`, `8717966`).
45. Results directory normalization came after inconsistent output placement (`8717966`).
46. Run naming was standardized only after ambiguity had already accumulated (`44c0787`).
47. We accidentally committed a gitignored file via force-add and had to undo (`4430656`).
48. We needed custom-results retention tightening to prevent stale report confusion (`f83fdb4`).
49. Evidence docs required repeated corrections/backfills (Gemini snapshot and substitutions) (`44bcf27`, `334275c`).
50. We removed backfill footnotes later, indicating evolving stance on evidence verbosity/transparency (`86f4f65`).
51. Provenance hardening arrived after legacy artifact generation had already happened (`384245e`, `660c2d4`).
52. We had to explicitly separate fixture metadata from frozen question data after coupling pain (`c65fd13`).
53. Coverage/completeness checks for bridge sources had to become mandatory to avoid silent corruption (`0dd04e9`, `282939a`).
54. Repo integrity checks were added relatively late for a benchmark-heavy project (`08579b1`).

## E) Documentation/Release/Branding Execution Issues

55. We performed a multi-commit brand rename (`posix` -> `sayance`) with revert/re-apply churn (`dc134ec`, `571e1d9`, `851fc06`, `63ae044`).
56. URL updates across docs were done multiple times, showing release checklist incompleteness.
57. We needed a migration/uninstall helper after rename, meaning migration risk surfaced post hoc (`5e2be62`).
58. Internal docs were trimmed/deleted late for public release, indicating pre-release documentation debt (`290608c`, `a69e640`).
59. `docs/solutions` and design-rationale trees were removed after causing drift/conflict with shipped reality (`9e9e96e`, `a69e640`).
60. `AGENTS.md` references required patching after doc restructuring, showing dependency ripple under-managed (`8590c2b`).
61. Utility list naming (`posix-utilities.txt` -> `macOS-posix-utilities.txt`) was clarified only after ambiguity existed (`dd9daa5`).
62. We had to repeatedly qualify "142" with macOS context to stop misinterpretation (`431d2a2`).
63. We initially modeled all 155 POSIX utilities, then removed 13 unshipped-by-macOS entries (`d324120` then `5a997f1`).
64. Release cadence (v1.0.0 -> v1.0.1 -> v1.0.2 same day) reflects compressed stabilization under pressure (`523394d`, `a69e640`, `3b8065f`).
65. CI/public-install guardrails were added after release, not fully before (`729dd6e`, `08579b1`).
66. License appendix had to be restored after being lost (`81323b5`).
67. Portable `sed -i` fix indicates avoidable cross-platform scripting assumptions (`1d27986`).
68. Hardcoded local path leaked into script and required cleanup (`319ba0c`).

## F) Process, QA, and Team Workflow Misses

69. Review-fix commits and "post-review fixes" happened repeatedly, indicating first-pass QA misses (`a01c7ba`, `ffa97ef`).
70. We had to add deterministic unittest entrypoint after instability signals (`333fde9`).
71. Test aggregation strategy (`test_all.py`) drifted and was later replaced with discovery-based execution (`17f13b8`, `ffa97ef`).
72. Canary assertions were too permissive and later tightened to prevent false-green outcomes (`3335499`).
73. Live canary timeout behavior needed portability fixes (`af1d9ae`).
74. GitHub gating constraints were documented because enforcement assumptions were initially wrong/incomplete (`ad1939d`, later public-repo updates).
75. Public-readiness hygiene removed local config artifacts late in cycle (`f9eb800`).
76. Cherry-pick/recovery style merges suggest branch/process turbulence (`7454b42`, `743cde3`).
77. "Adding doc updates that should have gone with ..." commit explicitly shows sync slippage (`34155c7`).
78. The current branch still shows a syntax-gate failure in `benchmark_core/runner.py` line 123, undermining confidence in pre-merge discipline.

## G) Miscellaneous (intentionally unforced grouping)

79. Report terminology, folder names, and artifact semantics were all renamed over time, increasing cognitive switching cost (`f6eb3b0`, `58c0487`, `44c0787`).
80. We repeatedly had to make invisible assumptions explicit (cache state, quotas, excluded utilities, model pins), showing documentation lag behind runtime reality.
81. Compliance gains often arrived with verbosity/latency tradeoffs, meaning "better" was multidimensional and easy to overstate.
82. The project needed explicit anti-drift doctrine because drift was not hypothetical; it was recurrent across docs and benchmarks.
83. Evidence storytelling was revised several times (add, correct, footnote, remove), revealing tension between readability and forensic completeness.
84. Strong wins (e.g., compliance lifts) were real, but supporting process showed frequent repair loops.
85. The retrospective pattern is clear: most hard problems were not "model intelligence" problems; they were contract, telemetry, and process-quality problems.
