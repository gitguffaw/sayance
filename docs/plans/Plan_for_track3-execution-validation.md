# Track 3 — Execution Validation Environment

## Context

The current benchmark (Tracks 1 and 2) measures token cost and POSIX compliance through **text analysis only** — pattern matching on the LLM's response. Compliance = "the response contains the expected command and doesn't mention non-POSIX tools." No command is ever actually run.

This creates a gap: a response can be marked POSIX-compliant because it uses `sort` while still being syntactically wrong or producing wrong output. More importantly, it fails to answer the real financial question:

> **If the LLM gives a wrong command on the first attempt, what does the retry loop cost?**

That retry cost — extra tokens + extra time — is the true financial delta between Raw (Track 1) and Step-Up (Track 2).

Track 3 proves this delta by actually running the suggested commands and measuring what happens when they fail.

---

## Intended Outcome

After running Track 3, you get three new metrics per track:

- `exec_success_rate` — what fraction of commands ran correctly on the first try
- `total_retry_tokens` — additional tokens burned in retry loops when the first attempt was wrong
- `total_retry_time_ms` — additional wall-clock time burned in retry loops

Side-by-side comparison: Raw vs Step-Up on all three metrics. Fewer retries = fewer tokens = less time = less money. That's the financial case for Step-Up.

---

## New Flag: `--execute`

Works independently of `--inject-posix`. Combining both runs Track 3b (Step-Up with execution validation).

```bash
# Track 3a: Raw execution
python3 run_benchmark.py --execute

# Track 3b: Step-Up execution
python3 run_benchmark.py --inject-posix --execute
```

Results land in new directories:

| Flags              | Results dir               |
|--------------------|--------------------------|
| (none)             | `results/`               |
| `--inject-posix`   | `results-stepup/`        |
| `--execute`        | `results-execute/`       |
| both               | `results-stepup-execute/` |

---

## Execution Flow Per Question

```
1. Get LLM response (same as Track 1/2)
2. Extract command from response → extract_command(response, expected_commands)
3. Copy fixture dir to temp dir (isolation per run)
4. Run command in temp dir → run_command(cmd, cwd)
5. Validate: compare stdout or resulting files to expected
6. If fail AND retries_remaining > 0:
   a. Build retry prompt: question + "Your command {cmd} failed: {stderr}"
   b. Re-invoke LLM → new response
   c. Add retry tokens + time to running totals
   d. Go to step 2 with the new response
7. Record ExecutionRecord alongside existing QuestionResult
```

Max retries per question: 3. After 3 failures, the question is marked failed and the run continues.

---

## Fixtures

### Structure

```
fixtures/
  T01/
    data.csv              ← input file(s)
    expected_stdout       ← what the correct command should print to stdout
  T03/
    setup/                ← files copied into temp dir before the command runs
      file1.txt
      file2.txt
    expected/             ← what files should look like after the command
      file1.txt
      file2.txt
```

### Validation Types

| Type         | How validated                                        |
|--------------|------------------------------------------------------|
| `stdout`     | stdout matches `expected_stdout` exactly (stripped)  |
| `exit_zero`  | command exits with code 0                            |
| `file_state` | files in temp dir match `expected/` after running    |

### New Fields in `benchmark_data.json` (per question)

```json
{
  "id": "T01",
  "fixture_dir": "T01",
  "exec_validation_type": "stdout",
  "exec_setup_note": "data.csv is the input; command should sort by second comma-delimited field"
}
```

### Initial Fixture Set — Tier 1 (T01–T10)

| ID  | Utility  | Fixture needed                         | Validation   |
|-----|----------|----------------------------------------|--------------|
| T01 | sort     | data.csv with 5 rows                   | stdout       |
| T02 | find     | conf/ dir, 2 old + 1 new .conf files   | stdout       |
| T03 | sed      | setup/ with files containing text      | file_state   |
| T04 | uniq     | words.txt with duplicate lines         | stdout       |
| T05 | cut      | data.tsv with 3 columns                | stdout       |
| T06 | pax      | src/ dir to archive                    | exit_zero    |
| T07 | grep     | src/ tree with target pattern          | stdout       |
| T08 | test     | script to check (via sh -c)            | exit_zero    |
| T09 | cp/pax   | files with specific permissions        | file_state   |
| T10 | comm     | file_a.txt and file_b.txt, sorted      | stdout       |

Tier 2 (T11–T23) and Tier 3 (T24–T30) fixtures are deferred to Phase 2. Tier 1 alone proves the concept.

---

## New Functions in `run_benchmark.py`

### `extract_command(response, expected_commands) -> str`

Extracts the runnable command from prose LLM output. Strategy in priority order:

1. If response is already a single short line with no prose → return as-is
2. Look for a fenced code block (`` ``` `` or `` ` ``) → extract contents
3. Look for lines starting with `$` → strip `$` prefix
4. Look for lines that begin with one of the `expected_commands` utilities
5. Fallback: return the full response stripped

Extraction failures surface as `exec_exit_code: 127` (command not found) rather than crashing the run.

### `setup_fixture(fixture_dir, temp_dir) -> Path`

- Copies `fixtures/{fixture_dir}/setup/` (or root) into `temp_dir`
- Returns the working directory path for the command
- Handles missing fixture gracefully: sets `exec_skipped: true`, skips execution

### `run_command(command, cwd, timeout=30) -> CommandResult`

```python
@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    elapsed_ms: float
```

Uses `shell=True` because LLM responses may include pipelines. The input is LLM-generated output for known questions; wrong syntax is the expected failure mode, not injection. Timeout: 30 seconds (slow commands = wrong commands).

### `validate_command_result(result, question, fixture_dir) -> bool`

- `stdout`: `result.stdout.strip() == (fixture_dir / "expected_stdout").read_text().strip()`
- `exit_zero`: `result.exit_code == 0`
- `file_state`: compare each file in temp dir against `fixture_dir/expected/` using `filecmp`

### `execute_with_retry(question, llm, initial_response, initial_tokens, max_retries=3) -> ExecutionRecord`

```python
@dataclass
class ExecutionRecord:
    command_extracted: str
    exec_success: bool
    exec_attempts: int           # 1 = first-try success
    retry_tokens: int            # tokens burned on retries only
    retry_time_ms: float         # time burned on retries only
    total_tokens_with_retries: int
    total_time_ms_with_retries: float
    attempts: list[dict]         # per-attempt: command, exit_code, stderr
```

---

## New Metrics

### Per-question (added to `QuestionResult`)

```json
"execution_record": {
  "command_extracted": "sort -t',' -k2,2 data.csv",
  "exec_success": true,
  "exec_attempts": 1,
  "retry_tokens": 0,
  "retry_time_ms": 0,
  "total_tokens_with_retries": 1279,
  "total_time_ms_with_retries": 2800,
  "attempts": [
    {"command": "sort -t',' -k2,2 data.csv", "exit_code": 0, "stderr": ""}
  ]
}
```

### Per-LLM summary

```json
{
  "exec_success_rate": 0.7,
  "first_attempt_success_rate": 0.6,
  "mean_retry_count": 0.8,
  "total_retry_tokens": 12400,
  "total_retry_time_ms": 45200
}
```

### Extended comparison report

The existing `--compare` report gains an **Execution** section:

- Exec success rate per run (green/red badges)
- First-attempt success rate
- Total retry token cost per run
- **Delta column**: tokens Step-Up saves by getting it right the first time

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `run_benchmark.py` | Add `--execute` flag, 5 new functions, new metrics, results dir routing |
| `benchmark_data.json` | Add `fixture_dir`, `exec_validation_type`, `exec_setup_note` to T01–T10 |
| `fixtures/T01/` through `fixtures/T10/` | Create with minimal test data and expected outputs |
| `docs/execution-validation.md` | Document Track 3, fixture format, retry loop design |
| `.gitignore` | Add `results-execute/`, `results-stepup-execute/` |

---

## Implementation Phases

### Phase 1 — Core harness (Tier 1 questions)
1. Create `fixtures/` with T01–T10 data and expected outputs
2. Implement `extract_command()`, `run_command()`, `validate_command_result()`
3. Wire `--execute` flag and results dir routing into `main()`
4. Add `ExecutionRecord` to `QuestionResult` and per-LLM summary
5. No retry loop yet — just first-attempt execution

### Phase 2 — Retry loop + reporting
1. Implement `execute_with_retry()` with token tracking
2. Add retry columns to comparison report
3. Run Track 3a and Track 3b; compare retry token delta

### Phase 3 — Full coverage (deferred)
1. Add fixtures for T11–T30
2. Consider Docker for stricter POSIX isolation (macOS BSD utilities vs GNU)

---

## Verification

```bash
# Syntax check
python3 -m py_compile run_benchmark.py

# Dry run (no API calls, no execution)
python3 run_benchmark.py --dry-run --execute

# Single question smoke test
python3 run_benchmark.py --llms claude --questions T01 --execute

# Full Track 3a
python3 run_benchmark.py --llms claude --execute

# Full Track 3b
python3 run_benchmark.py --llms claude --inject-posix --execute

# Compare all four tracks
python3 run_benchmark.py --compare \
  "Raw=results/summary-*.json" \
  "StepUp=results-stepup/summary-*.json" \
  "RawExec=results-execute/summary-*.json" \
  "StepUpExec=results-stepup-execute/summary-*.json"
```

Success criteria in the comparison report:
- `exec_success_rate` is higher for Step-Up than Raw
- `total_retry_tokens` is lower for Step-Up than Raw
- `total_retry_time_ms` is lower for Step-Up than Raw

Those three deltas are the proof.

---

## Design Decisions

**macOS vs Docker:** macOS subprocess first. The goal is to detect wrong syntax and wrong output — macOS POSIX utilities are sufficient. Docker is the Phase 3 upgrade for stricter POSIX isolation.

**`shell=True` justification:** Commands may be pipelines (`find . | sort`). The security surface is LLM output for known questions — wrong syntax is the expected failure mode. This is documented in code comments.

**Fixture scope:** Starting with Tier 1 only. 10 questions is enough to prove the concept and measure the retry delta. Tier 2/3 can be added without any changes to the harness.

**Command extraction:** Best-effort with graceful failure. A 127 exit code is an honest failure; it doesn't crash the run or invalidate other questions.
