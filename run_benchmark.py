#!/usr/bin/env python3
"""POSIX Token Efficiency Benchmark v0.2

Measures how many tokens LLMs burn when reasoning about POSIX shell commands.
Captures token usage from CLI JSON output, tracks accuracy as a secondary metric.

Usage:
    python3 run_benchmark.py                        # Run all LLMs, all questions
    python3 run_benchmark.py --llms gemini           # Run only Gemini (free, validate first)
    python3 run_benchmark.py --judge claude           # Use Claude as grader
    python3 run_benchmark.py --questions Q1 Q5        # Run specific questions only
    python3 run_benchmark.py --dry-run                # Show what would be run
    python3 run_benchmark.py --no-grade               # Skip accuracy grading, tokens only
    python3 run_benchmark.py --delay 2                # 2-second pause between calls
    python3 run_benchmark.py --max-workers 2           # Limit concurrency per provider
"""

import json
import subprocess
import sys
import re
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TypedDict

SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "benchmark_data.json"
RESULTS_DIR = SCRIPT_DIR / "results"

# ---------------------------------------------------------------------------
# Data model (frozen — measurement data must not be mutated after capture)
# ---------------------------------------------------------------------------

class LLM(StrEnum):
    CLAUDE = "claude"
    GEMINI = "gemini"
    CODEX = "codex"


@dataclass(frozen=True)
class TokenUsage:
    input: int
    input_cached: int
    output: int
    thoughts: int
    billable: int
    cost_usd: float | None      # None if not reported by provider
    cost_source: str             # "reported" or "calculated"
    raw: dict                    # original CLI JSON for reproducibility


@dataclass(frozen=True)
class AccuracyGrade:
    score: int   # 0-2, clamped
    reason: str


@dataclass(frozen=True)
class QuestionResult:
    id: str
    llm: str
    model: str                   # e.g. "claude-opus-4-6", "gemini-3.1-pro-preview", "gpt-5.4"
    run_k: int
    question: str
    response: str                # truncated to 500 chars
    tokens: TokenUsage
    accuracy: AccuracyGrade | None
    cache_state: str             # "cold" or "warm"
    timestamp: str


# ---------------------------------------------------------------------------
# CLI invocation
# ---------------------------------------------------------------------------

LLM_COMMANDS: dict[str, list[str]] = {
    "claude": ["claude", "--output-format", "json", "-p"],
    "gemini": ["gemini", "-o", "json", "-p"],
    "codex": ["codex", "exec", "--json", "--skip-git-repo-check"],
}

SYSTEM_PROMPT = (
    "You are answering questions about POSIX shell utilities. "
    "Be specific about what is POSIX-compliant versus GNU/BSD extensions. "
    "Be concise but precise."
)


NOISE_PREFIXES = (
    "MCP issues detected",
    "Warning:",
    "Keychain initialization",
    "Loading extension:",
    "Registering notification",
    "Server '",
    "Loaded cached credentials",
    "Scheduling MCP",
    "Executing MCP",
    "Coalescing burst",
    "Tool with name",
    "Skill ",
    "[MCP error]",
)


def strip_cli_noise(output: str) -> str:
    """Remove known CLI prefixes that corrupt JSON parsing.

    Handles the case where noise text and JSON are on the same line,
    e.g.: 'MCP issues detected. Run /mcp list for status.{"session_id":...'
    """
    lines = output.split("\n")
    cleaned = []
    for line in lines:
        is_noise = False
        for prefix in NOISE_PREFIXES:
            if line.startswith(prefix):
                # Check if JSON starts on this same line
                json_start = line.find("{")
                if json_start > 0:
                    cleaned.append(line[json_start:])
                # else: pure noise line, skip entirely
                is_noise = True
                break
        if not is_noise:
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def invoke_cli(llm: str, prompt: str, *, timeout_seconds: int = 90) -> str:
    """Send a prompt to an LLM CLI and return raw stdout."""
    cmd = LLM_COMMANDS[llm].copy()
    cmd.append(prompt)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode != 0 and not result.stdout.strip():
            return f'{{"error": "exit code {result.returncode}", "stderr": {json.dumps(result.stderr.strip()[:200])}}}'
        return strip_cli_noise(result.stdout)
    except subprocess.TimeoutExpired:
        return '{"error": "timeout"}'
    except FileNotFoundError:
        return f'{{"error": "{llm} CLI not found"}}'


# ---------------------------------------------------------------------------
# Token parsers (one per provider)
# ---------------------------------------------------------------------------

def parse_claude_tokens(raw_json: dict) -> TokenUsage:
    """Parse token usage from Claude CLI JSON output."""
    usage = raw_json.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    input_cached = cache_creation + cache_read

    # billable includes cache_creation (charged at reduced rate) + fresh input + output
    # Claude reports total_cost_usd which accounts for cache pricing, so use that
    billable = input_tokens + cache_creation + cache_read + output_tokens

    return TokenUsage(
        input=input_tokens,
        input_cached=input_cached,
        output=output_tokens,
        thoughts=0,
        billable=billable,
        cost_usd=raw_json.get("total_cost_usd"),
        cost_source="reported" if "total_cost_usd" in raw_json else "unknown",
        raw=usage,
    )


def parse_gemini_tokens(raw_json: dict) -> TokenUsage:
    """Parse token usage from Gemini CLI JSON output."""
    stats = raw_json.get("stats", {})
    models = stats.get("models", {})
    # Get first model's tokens (model name varies)
    tokens = {}
    for model_data in models.values():
        tokens = model_data.get("tokens", {})
        break

    input_tokens = tokens.get("input", 0)
    prompt_tokens = tokens.get("prompt", 0)
    output_tokens = tokens.get("candidates", 0)
    cached = tokens.get("cached", 0)
    thoughts = tokens.get("thoughts", 0)

    return TokenUsage(
        input=input_tokens,
        input_cached=cached,
        output=output_tokens,
        thoughts=thoughts,
        billable=prompt_tokens - cached + output_tokens,
        cost_usd=None,
        cost_source="calculated",
        raw=tokens,
    )


def parse_codex_tokens(raw_stdout: str) -> TokenUsage:
    """Parse token usage from Codex JSONL output (last turn.completed event)."""
    usage = {}
    for line in raw_stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "turn.completed" and "usage" in event:
                usage = event["usage"]
        except json.JSONDecodeError:
            continue

    input_tokens = usage.get("input_tokens", 0)
    cached = usage.get("cached_input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    return TokenUsage(
        input=input_tokens,
        input_cached=cached,
        output=output_tokens,
        thoughts=0,
        billable=input_tokens - cached + output_tokens,
        cost_usd=None,
        cost_source="calculated",
        raw=usage,
    )


def _detect_codex_model() -> str:
    """Read Codex model from config (not available in JSONL output)."""
    import tomllib
    config_path = Path.home() / ".codex" / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        return config.get("model", "unknown")
    return "unknown"


def parse_response(llm: str, raw_stdout: str) -> tuple[str, TokenUsage, str]:
    """Parse CLI output into (response_text, token_usage, model_name)."""
    if llm == "codex":
        # Codex: JSONL format, extract text from item.completed events
        tokens = parse_codex_tokens(raw_stdout)
        model = _detect_codex_model()
        text_parts = []
        for line in raw_stdout.strip().splitlines():
            try:
                event = json.loads(line.strip())
                if event.get("type") == "item.completed":
                    item = event.get("item", {})
                    text_parts.append(item.get("text", ""))
            except json.JSONDecodeError:
                continue
        return "\n".join(text_parts).strip(), tokens, model

    # Claude and Gemini: single JSON object
    try:
        data = json.loads(raw_stdout)
    except json.JSONDecodeError:
        return raw_stdout[:500], TokenUsage(
            input=0, input_cached=0, output=0, thoughts=0,
            billable=0, cost_usd=None, cost_source="parse_error", raw={},
        ), "unknown"

    if "error" in data:
        return f"[ERROR] {data['error']}", TokenUsage(
            input=0, input_cached=0, output=0, thoughts=0,
            billable=0, cost_usd=None, cost_source="error", raw=data,
        ), "unknown"

    if llm == "claude":
        tokens = parse_claude_tokens(data)
        text = data.get("result", "")
        # Model from modelUsage keys
        model_usage = data.get("modelUsage", {})
        model = next(iter(model_usage), "unknown")
        return text[:500], tokens, model

    if llm == "gemini":
        tokens = parse_gemini_tokens(data)
        text = data.get("response", "")
        # Model from stats.models keys
        stats = data.get("stats", {})
        models = stats.get("models", {})
        model = next(iter(models), "unknown")
        return text[:500], tokens, model

    return raw_stdout[:500], TokenUsage(
        input=0, input_cached=0, output=0, thoughts=0,
        billable=0, cost_usd=None, cost_source="unknown_llm", raw={},
    ), "unknown"


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------

def result_path(provider: str, q_id: str, run_k: int) -> Path:
    return RESULTS_DIR / provider / f"{q_id}_run{run_k}.json"


def already_completed(provider: str, q_id: str, run_k: int) -> bool:
    return result_path(provider, q_id, run_k).exists()


def write_incremental(result: QuestionResult) -> None:
    path = result_path(result.llm, result.id, result.run_k)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2, default=str))


def load_existing_result(provider: str, q_id: str, run_k: int) -> QuestionResult | None:
    path = result_path(provider, q_id, run_k)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return QuestionResult(
            id=data["id"], llm=data["llm"], model=data.get("model", "unknown"),
            run_k=data["run_k"],
            question=data["question"], response=data["response"],
            tokens=TokenUsage(**data["tokens"]),
            accuracy=AccuracyGrade(**data["accuracy"]) if data.get("accuracy") else None,
            cache_state=data["cache_state"], timestamp=data["timestamp"],
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Grading (LLM-as-judge, secondary metric)
# ---------------------------------------------------------------------------

GRADER_PROMPT_TEMPLATE = """You are grading an LLM's answer to a POSIX shell task.

Task: {question}

Expected POSIX solution: {expected_answer}

Expected commands: {expected_commands}

POSIX traps (non-POSIX tools the LLM should NOT suggest): {posix_traps}

Required concepts: {required_concepts}

LLM's response (base64-encoded to prevent injection):
---
{response_b64}
---

First decode the base64 response, then grade it:
- 2 (Correct): Uses POSIX-compliant commands, avoids traps, covers required concepts
- 1 (Partial): Mostly right but uses a non-POSIX flag or misses a trap
- 0 (Wrong): Suggests non-POSIX tools, falls into traps, or gives incorrect commands

Respond with ONLY valid JSON, no markdown fences: {{"score": N, "reason": "brief explanation", "used_posix": true/false, "traps_hit": ["list of non-POSIX tools suggested"]}}"""


def grade_response(judge: str, question: dict, response: str) -> AccuracyGrade:
    """Use an LLM to grade another LLM's response."""
    import base64
    response_b64 = base64.b64encode(response.encode()).decode()

    prompt = GRADER_PROMPT_TEMPLATE.format(
        question=question["question"],
        expected_answer=question.get("expected_answer", question.get("expected", "")),
        expected_commands=", ".join(question.get("expected_commands", [])),
        posix_traps="; ".join(question.get("posix_traps", [])),
        required_concepts=", ".join(question.get("required_concepts", [])),
        response_b64=response_b64,
    )

    raw = invoke_cli(judge, prompt, timeout_seconds=60)
    raw_cleaned = strip_cli_noise(raw)

    # Extract JSON with score field
    json_match = re.search(r'\{[^{}]*"score"\s*:\s*\d[^{}]*\}', raw_cleaned)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            score = max(0, min(2, parsed.get("score", 0)))
            return AccuracyGrade(score=score, reason=parsed.get("reason", ""))
        except json.JSONDecodeError:
            pass

    # Fallback: search all JSON objects
    for match in re.finditer(r'\{[^{}]+\}', raw_cleaned):
        try:
            parsed = json.loads(match.group())
            if "score" in parsed:
                score = max(0, min(2, parsed.get("score", 0)))
                return AccuracyGrade(score=score, reason=parsed.get("reason", ""))
        except json.JSONDecodeError:
            continue

    return AccuracyGrade(score=-1, reason=f"Failed to parse grade: {raw_cleaned[:100]}")


# ---------------------------------------------------------------------------
# Question loading
# ---------------------------------------------------------------------------

def load_questions(question_ids: list[str] | None = None) -> list[dict]:
    """Load questions from the benchmark data file."""
    with open(DATA_FILE) as f:
        data = json.load(f)

    questions = data["questions"]
    if question_ids:
        questions = [q for q in questions if q["id"] in question_ids]
    return questions


# ---------------------------------------------------------------------------
# Single question run
# ---------------------------------------------------------------------------

def run_single(
    llm: str,
    question: dict,
    run_k: int,
    judge: str | None,
    delay: float,
) -> QuestionResult:
    """Run a single question against a single LLM and return the result."""
    import time

    if delay > 0:
        time.sleep(delay)

    q_id = question["id"]
    prompt = f"{SYSTEM_PROMPT}\n\n{question['question']}"

    # Detect cache state (first call to this provider = cold)
    cache_state = "warm" if already_completed(llm, q_id, 0) else "unknown"

    raw_stdout = invoke_cli(llm, prompt)
    response_text, tokens, model = parse_response(llm, raw_stdout)

    # Determine cache state from actual token data
    if tokens.input_cached > 0:
        cache_state = "warm"
    else:
        cache_state = "cold"

    # Grade if judge is specified and question has expected answer
    accuracy = None
    if judge and ("expected_answer" in question or "expected" in question):
        accuracy = grade_response(judge, question, response_text)

    return QuestionResult(
        id=q_id,
        llm=llm,
        model=model,
        run_k=run_k,
        question=question["question"],
        response=response_text[:500],
        tokens=tokens,
        accuracy=accuracy,
        cache_state=cache_state,
        timestamp=datetime.now().isoformat(),
    )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

PROVIDER_CONCURRENCY = {
    "claude": 3,
    "gemini": 5,
    "codex": 2,
}


def run_provider_batch(
    llm: str,
    questions: list[dict],
    k: int,
    judge: str | None,
    delay: float,
    max_workers: int | None,
) -> list[QuestionResult]:
    """Run all questions for a single provider with concurrency."""
    workers = max_workers or PROVIDER_CONCURRENCY.get(llm, 2)
    results: list[QuestionResult] = []
    tasks_to_run = []

    for q in questions:
        for run_idx in range(k):
            if already_completed(llm, q["id"], run_idx):
                existing = load_existing_result(llm, q["id"], run_idx)
                if existing:
                    results.append(existing)
                    print(f"  [{q['id']}] run {run_idx} — cached (skipped)")
                    continue
            tasks_to_run.append((q, run_idx))

    if not tasks_to_run:
        print(f"  All {len(questions) * k} results already cached.")
        return results

    print(f"  {len(tasks_to_run)} calls to make ({len(results)} cached)")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for q, run_idx in tasks_to_run:
            future = pool.submit(run_single, llm, q, run_idx, judge, delay)
            futures[future] = (q["id"], run_idx)

        for future in as_completed(futures):
            q_id, run_idx = futures[future]
            try:
                result = future.result(timeout=120)
                results.append(result)
                write_incremental(result)

                # Status indicator
                if result.tokens.billable > 0:
                    acc = ""
                    if result.accuracy and result.accuracy.score >= 0:
                        sym = "✓" if result.accuracy.score == 2 else "△" if result.accuracy.score == 1 else "✗"
                        acc = f" {sym}{result.accuracy.score}/2"
                    print(
                        f"  [{q_id}] run {run_idx} — "
                        f"in:{result.tokens.input} out:{result.tokens.output} "
                        f"cached:{result.tokens.input_cached} "
                        f"thoughts:{result.tokens.thoughts} "
                        f"billable:{result.tokens.billable}"
                        f"{acc}"
                    )
                else:
                    print(f"  [{q_id}] run {run_idx} — {result.response[:60]}")
            except Exception as e:
                print(f"  [{q_id}] run {run_idx} — ERROR: {e}")

    return results


def run_benchmark(
    llms: list[str],
    questions: list[dict],
    k: int,
    judge: str | None,
    delay: float,
    max_workers: int | None,
    dry_run: bool,
) -> dict[str, list[QuestionResult]]:
    """Run the full benchmark across all providers."""
    total_calls = len(questions) * len(llms) * k

    print(f"\n{'=' * 60}")
    print(f"  POSIX Token Efficiency Benchmark v0.2")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  LLMs: {', '.join(llms)}")
    print(f"  Judge: {judge or 'none (token-only mode)'}")
    print(f"  Questions: {len(questions)}, K={k} runs each")
    print(f"  Total calls: {total_calls}")
    print(f"{'=' * 60}\n")

    if dry_run:
        for q in questions:
            print(f"  [{q['id']}] {q['question'][:60]}...")
        print(f"\n  Would make {total_calls} CLI invocations.")
        return {}

    all_results: dict[str, list[QuestionResult]] = {}

    # Run all providers in parallel
    with ThreadPoolExecutor(max_workers=len(llms)) as provider_pool:
        provider_futures = {}
        for llm in llms:
            print(f"--- {llm.upper()} ---\n")
            future = provider_pool.submit(
                run_provider_batch, llm, questions, k, judge, delay, max_workers,
            )
            provider_futures[future] = llm

        for future in as_completed(provider_futures):
            llm = provider_futures[future]
            try:
                all_results[llm] = future.result()
            except Exception as e:
                print(f"\n  {llm.upper()} FAILED: {e}")
                all_results[llm] = []

    return all_results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(all_results: dict[str, list[QuestionResult]], questions: list[dict]) -> None:
    """Print a formatted token usage report."""
    if not all_results:
        return

    # Build question lookup for tier info
    q_lookup = {q["id"]: q for q in questions}

    print(f"\n{'=' * 70}")
    print(f"  POSIX TOKEN EFFICIENCY REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Spec: POSIX.1-2024 (Issue 8) — 155 utilities")
    print(f"{'=' * 70}\n")

    # --- Per-LLM summary ---
    for llm, results in all_results.items():
        if not results:
            continue

        valid = [r for r in results if r.tokens.billable > 0]
        if not valid:
            print(f"  {llm.upper()}: No valid results\n")
            continue

        # Detect model from first result
        model = valid[0].model if valid else "unknown"

        inputs = [r.tokens.input for r in valid]
        outputs = [r.tokens.output for r in valid]
        cached = [r.tokens.input_cached for r in valid]
        thoughts = [r.tokens.thoughts for r in valid]
        billable = [r.tokens.billable for r in valid]
        costs = [r.tokens.cost_usd for r in valid if r.tokens.cost_usd is not None]

        def stats(values: list[int | float]) -> str:
            if not values:
                return "n/a"
            s = sorted(values)
            n = len(s)
            mean = sum(s) / n
            median = s[n // 2]
            return f"mean={mean:.0f}  median={median:.0f}  min={s[0]:.0f}  max={s[-1]:.0f}"

        print(f"  {llm.upper()} — model: {model}")
        print(f"  {'─' * 50}")
        print(f"    Input tokens:   {stats(inputs)}")
        print(f"    Output tokens:  {stats(outputs)}")
        print(f"    Cached tokens:  {stats(cached)}")
        print(f"    Thought tokens: {stats(thoughts)}")
        print(f"    Billable:       {stats(billable)}")
        if costs:
            print(f"    Cost USD:       {stats(costs)}")
            print(f"    Total cost:     ${sum(costs):.4f}")
        print()

        # Cache state
        cold = [r for r in valid if r.cache_state == "cold"]
        warm = [r for r in valid if r.cache_state == "warm"]
        print(f"    Cache: {len(cold)} cold, {len(warm)} warm, {len(valid) - len(cold) - len(warm)} unknown")

        # Accuracy (if graded)
        graded = [r for r in valid if r.accuracy and r.accuracy.score >= 0]
        if graded:
            scores = [r.accuracy.score for r in graded]
            total = sum(scores)
            max_score = len(graded) * 2
            pct = (total / max_score * 100) if max_score else 0
            print(f"    Accuracy:  {total}/{max_score} ({pct:.0f}%)")

        print()

    # --- Per-tier breakdown ---
    print(f"  {'─' * 70}")
    print(f"  TOKEN USAGE BY TIER")
    print(f"  {'─' * 70}\n")

    tier_names = {1: "Tier 1 (Common)", 2: "Tier 2 (Less common)", 3: "Tier 3 (POSIX-blind spot)"}

    for llm, results in all_results.items():
        valid = [r for r in results if r.tokens.billable > 0]
        if not valid:
            continue

        model = valid[0].model if valid else "unknown"
        print(f"  {llm.upper()} ({model})")

        for tier_num, tier_name in tier_names.items():
            tier_results = [r for r in valid if q_lookup.get(r.id, {}).get("tier") == tier_num]
            if not tier_results:
                continue
            out_tokens = [r.tokens.output for r in tier_results]
            mean_out = sum(out_tokens) / len(out_tokens)
            median_out = sorted(out_tokens)[len(out_tokens) // 2]
            print(f"    {tier_name}: {len(tier_results)} questions, output mean={mean_out:.0f} median={median_out:.0f}")

        print()

    # --- Per-question detail ---
    print(f"  {'─' * 70}")
    print(f"  PER-QUESTION DETAIL (sorted by output tokens)")
    print(f"  {'─' * 70}\n")

    all_valid = []
    for results in all_results.values():
        all_valid.extend(r for r in results if r.tokens.billable > 0)

    by_output = sorted(all_valid, key=lambda r: r.tokens.output, reverse=True)
    for r in by_output:
        tier = q_lookup.get(r.id, {}).get("tier", "?")
        acc = ""
        if r.accuracy and r.accuracy.score >= 0:
            sym = "✓" if r.accuracy.score == 2 else "△" if r.accuracy.score == 1 else "✗"
            acc = f" {sym}{r.accuracy.score}/2"
        print(
            f"    {r.llm:>8} [{r.id}] T{tier} "
            f"out:{r.tokens.output:>5} in:{r.tokens.input:>6} "
            f"cached:{r.tokens.input_cached:>6} thoughts:{r.tokens.thoughts:>4}"
            f"{acc}"
        )
        print(f"             {r.question[:65]}")

    print()


def save_summary(all_results: dict[str, list[QuestionResult]]) -> Path:
    """Save a combined summary JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_path = RESULTS_DIR / f"summary-{ts}.json"

    summary = {
        "version": "0.2",
        "timestamp": ts,
        "spec": "POSIX.1-2024 (Issue 8)",
        "utilities_count": 155,
        "llms": {},
    }

    for llm, results in all_results.items():
        valid = [r for r in results if r.tokens.billable > 0]
        model = valid[0].model if valid else "unknown"
        summary["llms"][llm] = {
            "model": model,
            "total_results": len(results),
            "valid_results": len(valid),
            "total_billable_tokens": sum(r.tokens.billable for r in valid),
            "total_output_tokens": sum(r.tokens.output for r in valid),
            "total_cost_usd": sum(
                r.tokens.cost_usd for r in valid if r.tokens.cost_usd is not None
            ),
            "mean_output_tokens": (
                sum(r.tokens.output for r in valid) / len(valid) if valid else 0
            ),
        }

    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"  Summary saved: {summary_path}")
    return summary_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="POSIX Token Efficiency Benchmark",
    )
    parser.add_argument(
        "--llms", nargs="+", default=["gemini", "claude", "codex"],
        choices=["gemini", "claude", "codex"],
        help="Which LLMs to test (default: all three)",
    )
    parser.add_argument(
        "--judge", default=None,
        choices=["gemini", "claude", "codex"],
        help="Which LLM grades responses (default: none, token-only mode)",
    )
    parser.add_argument(
        "--questions", nargs="+",
        help="Specific question IDs to run (e.g. Q1 Q5 Q12)",
    )
    parser.add_argument(
        "--k", type=int, default=1,
        help="Number of runs per question (default: 1, use 3+ for statistics)",
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Seconds to pause between API calls (default: 0)",
    )
    parser.add_argument(
        "--max-workers", type=int, default=None,
        help="Max concurrent calls per provider (overrides defaults)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be run without executing",
    )
    parser.add_argument(
        "--no-grade", action="store_true",
        help="Skip accuracy grading, measure tokens only",
    )
    args = parser.parse_args()

    judge = None if args.no_grade else args.judge

    # Warn if judge is also a test subject
    if judge and judge in args.llms:
        print(f"  Warning: {judge} is both test subject and judge.")
        print(f"  Results may be unreliable due to prompt injection risk.\n")

    questions = load_questions(args.questions)

    all_results = run_benchmark(
        llms=args.llms,
        questions=questions,
        k=args.k,
        judge=judge,
        delay=args.delay,
        max_workers=args.max_workers,
        dry_run=args.dry_run,
    )

    if all_results:
        generate_report(all_results, questions)
        save_summary(all_results)


if __name__ == "__main__":
    main()
