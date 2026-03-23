---
title: "feat: POSIX Token Efficiency Benchmark"
type: feat
status: active
date: 2026-03-22
deepened: 2026-03-22
revised: 2026-03-22
origin: docs/brainstorms/2026-03-22-posix-token-efficiency-brainstorm.md
---

# POSIX Token Efficiency Benchmark

## Core Requirement

**The answer is already in POSIX. The LLM just doesn't know it.**

POSIX defines 155 utilities (Issue 8, 2024). When a user asks "compute a checksum," the answer is `cksum`. When they ask "encode a file for email," the answer is `uuencode`. When they ask "archive a directory portably," the answer is `pax`. But LLMs reach for `sha256sum`, `base64`, `tar` — tools that aren't POSIX — and burn tokens doing it.

This project measures:
1. **How many tokens** LLMs burn answering real POSIX tasks
2. **How often** they reach for non-POSIX tools when POSIX has the answer
3. **What it costs** in dollars when they get it wrong and the user retries

---

## Problem Statement

Users ask LLMs to help with shell tasks. The LLMs:

- **Don't know POSIX tools exist** — suggest `xxd` instead of `od`, `tar` instead of `pax`, `base64` instead of `uuencode`, `md5sum` instead of `cksum`
- **Confuse POSIX with GNU** — suggest `sed -i` (GNU), `grep -r` (GNU), `cp -a` (GNU) when POSIX alternatives exist
- **Don't know the spec changed** — say `readlink`, `realpath`, `timeout` aren't POSIX when they became POSIX in Issue 8 (2024)
- **Burn tokens on all of the above** — wrong answers, retries, explanations of why their suggestion doesn't work on the target system

Nobody has measured this. This benchmark does.

(see brainstorm: docs/brainstorms/2026-03-22-posix-token-efficiency-brainstorm.md)

---

## Benchmark Design

### Task-Based Questions (Not Trivia)

Questions are real tasks a user would ask:

- "Sort a CSV by the second column only" — not "What does sort -k 2,2 do?"
- "Create a portable archive" — not "What is pax?"
- "Encode a file for a text-only channel" — not "What is uuencode?"

Each question has a key:

```json
{
  "id": "T06",
  "question": "Create a portable archive of a directory that works across POSIX systems.",
  "expected_commands": ["pax"],
  "expected_answer": "pax -w -f archive.pax directory/",
  "posix_traps": ["tar is NOT a POSIX utility", "pax is the POSIX archiver"],
  "required_concepts": ["pax", "not tar"]
}
```

- **`expected_commands`** — which POSIX utilities solve this task
- **`posix_traps`** — where LLMs will likely reach for non-POSIX tools
- **`required_concepts`** — what the answer must include to be correct

### What We Measure Per Question

1. **Tokens** — input, output, cached, thoughts, billable, cost USD
2. **Did it use a POSIX solution?** — check response against `expected_commands`
3. **Did it fall into a trap?** — check response against `posix_traps`
4. **How many tokens were wasted?** — if the answer is wrong/non-POSIX, the entire output is waste

### Three Tiers

- **Tier 1** (T01-T10): Common tasks — sort, find, sed, cut, grep, cp, test. LLMs should do well.
- **Tier 2** (T11-T23): Real but less common tasks — od, paste, tr, nohup, readlink, realpath, timeout, join, nl, pathchk, comm. Includes Issue 8 trap questions.
- **Tier 3** (T24-T30): Tasks where the POSIX answer exists but LLMs are blind to it — tsort, cksum, iconv, mkfifo, pr, expr, uuencode.

Current question set: **30 task-based questions** in `benchmark_data.json`.

---

## Token Capture Method (Confirmed Working)

Each CLI reports tokens in JSON output mode:

**Claude** (`claude --output-format json -p "prompt"`):
```json
{
  "usage": {
    "input_tokens": 3,
    "cache_creation_input_tokens": 22168,
    "output_tokens": 478
  },
  "total_cost_usd": 0.1505
}
```

**Gemini** (`gemini -o json -p "prompt"`):
```json
{
  "stats": {
    "models": {
      "gemini-3.1-pro-preview": {
        "tokens": {
          "input": 13844, "candidates": 245,
          "cached": 0, "thoughts": 334
        }
      }
    }
  }
}
```

**Codex** (`codex exec --json --skip-git-repo-check "prompt"`):
```jsonl
{"type":"turn.completed","usage":{"input_tokens":23303,"cached_input_tokens":3456,"output_tokens":841}}
```

**Note on Codex**: Codex is an agent, not a Q&A tool. It may read files, make tool calls, and do multi-step research before answering. Its token costs are non-deterministic and can vary 10x+ for the same question. This is a valid measurement — it's what the user actually pays.

### Verified Measurements (Q1: "Sort CSV by second column")

| | Gemini | Claude | Codex |
|---|--------|--------|-------|
| Input | 13,844 | 3 (+22,168 cache) | 23,303 |
| Output | 245 | 478 | 841 |
| Thoughts | 334 | 0 | 0 |
| Cost | free | $0.15 | TBD |

---

## Technical Approach

### Architecture

```
run_benchmark.py (single file)
├── invoke_cli(llm, prompt) → raw stdout
├── strip_cli_noise(output) → cleaned stdout
├── parse_response(llm, stdout) → (response_text, TokenUsage)
├── run_single(llm, question, run_k) → QuestionResult
├── run_provider_batch(llm, questions) → [QuestionResult]
├── grade_response(judge, question, response) → AccuracyGrade
└── generate_report(results) → printed report + summary JSON
```

### Data Model (Frozen Dataclasses)

```python
@dataclass(frozen=True)
class TokenUsage:
    input: int
    input_cached: int
    output: int
    thoughts: int
    billable: int
    cost_usd: float | None
    cost_source: str        # "reported" or "calculated"
    raw: dict               # original CLI JSON

@dataclass(frozen=True)
class QuestionResult:
    id: str
    llm: str
    run_k: int
    question: str
    response: str           # truncated to 500 chars
    tokens: TokenUsage
    accuracy: AccuracyGrade | None
    cache_state: str        # "cold" or "warm"
    timestamp: str
```

### Key Implementation Details

- **CLI noise stripping**: Handles Gemini's "MCP issues detected..." prefix on the same line as JSON
- **Per-provider token parsers**: Isolated functions for Claude, Gemini, Codex JSON formats
- **Checkpoint/resume**: Each result written to `results/{provider}/{id}_run{k}.json` immediately. Restart skips completed work.
- **Parallelization**: ThreadPoolExecutor with per-provider concurrency limits (Claude: 3, Gemini: 5, Codex: 2)
- **Score clamping**: `max(0, min(2, score))` prevents judge manipulation
- **Base64 grading**: Responses encoded before embedding in judge prompt to mitigate prompt injection

---

## Implementation Phases

### Phase 1: Token Measurement Core ✅ (Built, needs fixes)

- [x] JSON output flags in CLI commands
- [x] CLI noise stripping (MCP prefix)
- [x] Separate invoke_cli + parse_response
- [x] Per-provider token parsers
- [x] Frozen dataclasses
- [x] Score clamping
- [x] Subprocess timeout (90s)
- [x] Checkpoint/resume
- [x] --delay and --max-workers flags
- [ ] **Fix Claude billable** — currently ignores cache_creation tokens which still cost money
- [ ] **Fix cache_state detection** — shows "unknown" for Claude and Codex
- [ ] **Test grading** — --judge flag built but never verified
- [ ] **Add per-tier breakdown** to report
- [ ] **Add "POSIX compliance" check** — scan response for expected_commands and posix_traps

### Phase 2: Run Full Benchmark

- [ ] Task-based questions (30 currently, expand to cover more of the 155 utilities)
- [ ] Randomize question order per run
- [ ] Run Gemini first (free) to validate
- [ ] K=3 runs per question for variance estimation
- [ ] Total: 30 questions × 3 LLMs × 3 runs = 270 calls (expandable)

### Phase 3: Analysis & Report

- [ ] Per-task token cost table (sorted by most expensive)
- [ ] Per-tier breakdown
- [ ] **POSIX compliance rate** — what % of answers used POSIX tools vs non-POSIX
- [ ] **Trap hit rate** — which posix_traps did LLMs fall into most?
- [ ] **Waste analysis** — tokens burned on non-POSIX answers (entire output = waste)
- [ ] Mean/median tokens per task per LLM with IQR
- [ ] Total cost in USD per LLM (pinned to date)

### Phase 4: With-vs-Without Reference (Future)

- [ ] Create compact POSIX specs for 10 commands (~50-100 tokens each)
- [ ] Inject into system prompt, re-run benchmark
- [ ] Measure: does the LLM find POSIX tools it missed before?
- [ ] Calculate ROI: tokens spent on reference vs tokens saved by getting it right the first time

---

## Acceptance Criteria

- [ ] Script captures token usage from all 3 CLIs via JSON output mode
- [ ] Per-question results include: input, output, cached, thought tokens + cost USD
- [ ] Cache state (cold/warm) tracked per result
- [ ] **Response checked for POSIX compliance** — did it use expected_commands? Did it fall into posix_traps?
- [ ] Report shows per-tier token breakdown
- [ ] **Report shows POSIX compliance rate** — % of answers that used POSIX tools
- [ ] **Report shows trap hit rate** — which non-POSIX tools LLMs reached for most
- [ ] Raw CLI JSON output preserved in results for reproducibility
- [ ] Checkpoint/resume works — interrupted runs continue from last completed result
- [ ] `.gitignore` covers `results/`
- [ ] Report answers: "How many tokens does it cost, and how often does the LLM miss the POSIX answer?"

## Success Metrics

The benchmark succeeds if it can answer:
1. **"How often does the LLM miss the POSIX answer?"** — POSIX compliance rate across all tasks
2. **"Which traps do LLMs fall into?"** — sed -i, tar, xxd, grep -r, base64 — rank by frequency
3. **"How many tokens does it burn?"** — Mean/median output tokens per task per LLM
4. **"What does it cost when it's wrong?"** — Tokens wasted on non-POSIX answers
5. **"Would a compact reference fix this?"** — If LLMs miss >30% of POSIX answers, the project has clear value

---

## Known Issues

1. **Gemini MCP prefix** — "MCP issues detected..." on same line as JSON. Fixed in strip_cli_noise.
2. **Codex needs git** — `--skip-git-repo-check` flag. Fixed.
3. **Claude system context** — 22k tokens of CLAUDE.md loaded. Engine Check directive wastes output tokens. Consider `--bare`.
4. **Claude billable undercounted** — cache_creation tokens still cost money at reduced rate. Need to fix calculation.
5. **Codex non-determinism** — same question can cost 841 or 3,538 output tokens depending on whether Codex decides to use tools.
6. **Caching effects** — track cold/warm per result, randomize question order.

---

## Sources & References

### Origin

- **Brainstorm:** [docs/brainstorms/2026-03-22-posix-token-efficiency-brainstorm.md](docs/brainstorms/2026-03-22-posix-token-efficiency-brainstorm.md)

### Internal

- `run_benchmark.py` — benchmark runner (v0.2)
- `benchmark_data.json` — 30 task-based questions with answer keys
- `posix-utilities.txt` — all 155 POSIX Issue 8 utilities

### External

- POSIX Issue 8 utility index: https://pubs.opengroup.org/onlinepubs/9799919799/idx/utilities.html
- Inspect AI token tracking: https://inspect.aisi.org.uk/
- Langfuse token/cost tracking: https://langfuse.com/docs/observability/features/token-and-cost-tracking
- Artificial Analysis (tiktoken normalization): https://artificialanalysis.ai/methodology
- Statistical LLM eval methods: https://cameronrwolfe.substack.com/p/stats-llm-evals
