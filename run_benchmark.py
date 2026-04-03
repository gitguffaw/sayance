#!/usr/bin/env python3
"""POSIX Token Efficiency Benchmark v0.4

Measures how many tokens LLMs burn when reasoning about POSIX shell commands.
Captures token, latency, and failure-mode data for shell tasks that already have
short POSIX-native answers.

Usage:
    python3 run_benchmark.py                        # Run all LLMs, all questions
    python3 run_benchmark.py --llms gemini           # Run only Gemini (free, validate first)
    python3 run_benchmark.py --judge claude           # Use Claude as grader
    python3 run_benchmark.py --questions T01 T17      # Run specific questions only
    python3 run_benchmark.py --validate-bridge        # Verify bridge coverage (core + tldr)
    python3 run_benchmark.py --dry-run                # Show what would be run
    python3 run_benchmark.py --no-grade               # Skip accuracy grading, tokens only
    python3 run_benchmark.py --delay 2                # 2-second pause between calls
    python3 run_benchmark.py --max-workers 2          # Limit concurrency per provider
"""

import filecmp
import json
import re
import shlex
import shutil
import subprocess
import argparse
import random
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import StrEnum
from html import escape
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "benchmark_data.json"
POSIX_CORE_FILE = SCRIPT_DIR / "posix-core.md"
POSIX_TLDR_FILE = SCRIPT_DIR / "posix-tldr.json"
POSIX_UTILITIES_FILE = SCRIPT_DIR / "posix-utilities.txt"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
RESULTS_DIR = SCRIPT_DIR / "results"
RESULTS_DIR_STEPUP = RESULTS_DIR / "stepup"
RESULTS_DIR_EXECUTE = RESULTS_DIR / "execute"
RESULTS_DIR_STEPUP_EXECUTE = RESULTS_DIR / "stepup-execute"

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
    usage_valid: bool = True
    usage_invalid_reason: str = ""


@dataclass(frozen=True)
class AccuracyGrade:
    score: int   # 0-2, clamped
    reason: str


@dataclass(frozen=True)
class ExecutionMetrics:
    latency_ms: int
    step_count: int
    tool_call_count: int
    tool_calls_by_type: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ResponseAnalysis:
    minimal_answer: str
    minimal_word_count: int
    minimal_shell_token_count: int
    response_word_count: int
    minimal_answer_gap_words: int
    verbosity_ratio: float
    expected_command_hits: list[str] = field(default_factory=list)
    trap_hits: list[str] = field(default_factory=list)
    missing_required_concepts: list[str] = field(default_factory=list)
    posix_compliant: bool = False
    issue8_refusal: bool = False
    inefficiency_mode: str = "unknown"
    estimated_excess_output_tokens: int = 0


@dataclass(frozen=True)
class ToolSimulationAdjustment:
    replay_input_billable: int = 0
    tool_call_output: int = 0
    adjusted_billable: int = 0


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    elapsed_ms: float


@dataclass(frozen=True)
class ExecutionRecord:
    command_extracted: str
    exec_success: bool
    exec_attempts: int           # 1 = first-try success
    exec_exit_code: int
    exec_stdout: str
    exec_stderr: str
    exec_elapsed_ms: float
    exec_validation_type: str
    exec_skipped: bool = False
    exec_skip_reason: str = ""


@dataclass(frozen=True)
class QuestionResult:
    id: str
    llm: str
    model: str                   # e.g. "claude-opus-4-6", "gemini-3.1-pro-preview", "gpt-5.4"
    run_k: int
    question: str
    response: str                # full response text
    tokens: TokenUsage
    execution: ExecutionMetrics
    analysis: ResponseAnalysis
    accuracy: AccuracyGrade | None
    execution_record: ExecutionRecord | None  # Track 3: populated when --execute is used
    cache_state: str             # "cold" or "warm"
    timestamp: str


@dataclass(frozen=True)
class CLIInvocation:
    stdout: str
    latency_ms: int


# ---------------------------------------------------------------------------
# CLI invocation
# ---------------------------------------------------------------------------

LLM_COMMANDS: dict[str, list[str]] = {
    "claude": ["claude", "--output-format", "json", "-p"],
    "gemini": ["gemini", "-o", "json", "-p"],
    "codex": ["codex", "exec", "--json", "--skip-git-repo-check"],
}


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

DEFAULT_CLI_TIMEOUT_SECONDS = 120
DEFAULT_SHUFFLE_SEED = 20260329
DEFAULT_CLAUDE_MODEL = "claude-opus-4-6"
DEFAULT_CODEX_MODEL = "gpt-5.4"
TOOL_CALL_PATTERN = re.compile(r"TOOL_CALL:\s*get_posix_syntax\((.*?)\)")
UTILITY_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


_TRAP_PATTERNS_RAW: dict[str, list[str]] = {
    "T02": [r"-newermt\b", r"-mmin\b"],
    "T03": [r"sed\s+-i\b"],
    "T06": [r"\btar\b"],
    "T07": [r"grep\s+-r\b", r"grep\s+-P\b"],
    "T08": [r"\becho\b", r"\[\["],
    "T09": [r"cp\s+-a\b", r"cp\s+-r\b"],
    "T10": [r"\bdiff\b"],
    "T11": [r"\bxxd\b", r"\bhexdump\b"],
    "T14": [r"\bscreen\b", r"\btmux\b", r"\bdisown\b"],
    "T21": [r"cat\s+-n\b"],
    "T23": [r"<\("],
    "T25": [r"\bmd5sum\b", r"\bsha256sum\b"],
    "T29": [r"\blet\b"],
    "T30": [r"\bbase64\b"],
}

TRAP_PATTERNS_BY_ID: dict[str, list[re.Pattern]] = {
    qid: [re.compile(p, re.IGNORECASE) for p in patterns]
    for qid, patterns in _TRAP_PATTERNS_RAW.items()
}

_ISSUE8_REFUSAL_PATTERNS: list[re.Pattern] = [
    re.compile(p) for p in (
        r"there is no dedicated posix(?: shell)? utility",
        r"not\W+posix(?:-compliant)?",
        r"not in the posix standard",
    )
]

ISSUE8_COMMANDS = {"readlink", "realpath", "timeout"}

_posix_core_cache: str | None = None
_posix_tldr_cache: dict | None = None
_posix_utilities_cache: list[str] | None = None


def _load_posix_core() -> str | None:
    global _posix_core_cache
    if _posix_core_cache is None:
        try:
            _posix_core_cache = POSIX_CORE_FILE.read_text()
        except (FileNotFoundError, OSError) as e:
            print(f"  WARNING: Could not load posix-core.md: {e}")
            return None
    return _posix_core_cache


def _load_posix_tldr() -> dict:
    global _posix_tldr_cache
    if _posix_tldr_cache is None:
        _posix_tldr_cache = json.loads(POSIX_TLDR_FILE.read_text())
    return dict(_posix_tldr_cache)


def _load_posix_utilities() -> list[str]:
    global _posix_utilities_cache
    if _posix_utilities_cache is None:
        utilities: list[str] = []
        for line in POSIX_UTILITIES_FILE.read_text().splitlines():
            entry = line.strip().lower()
            if not entry or entry.startswith("#"):
                continue
            utilities.append(entry)
        _posix_utilities_cache = utilities
    return list(_posix_utilities_cache)


def normalize_utility_name(raw_command: str) -> str | None:
    candidate = raw_command.strip().strip("'\"").strip().lower()
    if not candidate or not UTILITY_NAME_PATTERN.fullmatch(candidate):
        return None
    return candidate


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


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def count_shell_tokens(command: str) -> int:
    try:
        return len(shlex.split(command))
    except ValueError:
        return len(command.split())


def flatten_numeric_metrics(
    data: object,
    *,
    prefix: str = "",
) -> dict[str, int]:
    """Flatten nested numeric metrics into a single-level dict."""
    flattened: dict[str, int] = {}
    if isinstance(data, bool):
        return flattened
    if isinstance(data, int):
        key = prefix or "value"
        flattened[key] = data
        return flattened
    if isinstance(data, float):
        key = prefix or "value"
        flattened[key] = int(data)
        return flattened
    if isinstance(data, dict):
        for key, value in data.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            for nested_key, nested_value in flatten_numeric_metrics(value, prefix=nested_prefix).items():
                flattened[nested_key] = flattened.get(nested_key, 0) + nested_value
    return flattened


def invoke_cli(
    llm: str,
    prompt: str,
    *,
    timeout_seconds: int = DEFAULT_CLI_TIMEOUT_SECONDS,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> CLIInvocation:
    """Send a prompt to an LLM CLI and return raw stdout plus latency."""
    cmd = LLM_COMMANDS[llm].copy()
    if llm == "claude" and claude_model:
        cmd.extend(["--model", claude_model])
    if llm == "codex" and codex_model:
        cmd.extend(["--model", codex_model])
    cmd.append(prompt)

    started = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if result.returncode != 0 and not result.stdout.strip():
            return CLIInvocation(
                stdout=(
                    f'{{"error": "exit code {result.returncode}", '
                    f'"stderr": {json.dumps(result.stderr.strip()[:200])}}}'
                ),
                latency_ms=latency_ms,
            )
        if not result.stdout.strip():
            stderr_hint = result.stderr.strip()[:200] if result.stderr else "none"
            return CLIInvocation(
                stdout=(
                    f'{{"error": "empty response", '
                    f'"stderr": {json.dumps(stderr_hint)}}}'
                ),
                latency_ms=latency_ms,
            )
        return CLIInvocation(stdout=strip_cli_noise(result.stdout), latency_ms=latency_ms)
    except subprocess.TimeoutExpired:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return CLIInvocation(stdout='{"error": "timeout"}', latency_ms=latency_ms)
    except FileNotFoundError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return CLIInvocation(
            stdout=f'{{"error": "{llm} CLI not found"}}',
            latency_ms=latency_ms,
        )


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
    if not isinstance(models, dict) or not models:
        return invalid_token_usage("missing Gemini stats.models telemetry", raw={"stats": stats})

    aggregate = {
        "input": 0,
        "prompt": 0,
        "candidates": 0,
        "cached": 0,
        "thoughts": 0,
    }
    normalized_models: dict[str, dict[str, int]] = {}
    for model_name, model_data in models.items():
        tokens = model_data.get("tokens", {}) if isinstance(model_data, dict) else {}
        normalized_tokens, error = _normalize_gemini_tokens(tokens)
        if error:
            return invalid_token_usage(
                f"{model_name}: {error}",
                raw={"model": model_name, "tokens": tokens},
            )
        assert normalized_tokens is not None
        normalized_models[str(model_name)] = normalized_tokens
        for field_name, value in normalized_tokens.items():
            aggregate[field_name] += value

    input_tokens = aggregate["input"]
    prompt_tokens = aggregate["prompt"]
    output_tokens = aggregate["candidates"]
    cached = aggregate["cached"]
    thoughts = aggregate["thoughts"]
    billable = prompt_tokens - cached + output_tokens
    if billable < 0:
        return invalid_token_usage(
            "Gemini billable token estimate is negative",
            raw={"models": normalized_models},
        )

    return TokenUsage(
        input=input_tokens,
        input_cached=cached,
        output=output_tokens,
        thoughts=thoughts,
        billable=billable,
        cost_usd=None,
        cost_source="calculated",
        raw={"models": normalized_models} if len(normalized_models) > 1 else next(iter(normalized_models.values())),
    )


def invalid_token_usage(reason: str, raw: dict | None = None) -> TokenUsage:
    """Return a token payload that preserves explicit usage-invalid state."""
    return TokenUsage(
        input=0,
        input_cached=0,
        output=0,
        thoughts=0,
        billable=0,
        cost_usd=None,
        cost_source="usage_invalid",
        raw=raw or {},
        usage_valid=False,
        usage_invalid_reason=reason,
    )


def coerce_token_int(value: object, field_name: str) -> tuple[int | None, str | None]:
    """Coerce a token counter to a non-negative integer without raising."""
    if value is None:
        return 0, None
    if isinstance(value, bool):
        return None, f"{field_name} must be an integer, got bool"
    if isinstance(value, int):
        if value < 0:
            return None, f"{field_name} must be non-negative, got {value}"
        return value, None
    if isinstance(value, float):
        if not value.is_integer():
            return None, f"{field_name} must be an integer, got {value!r}"
        if value < 0:
            return None, f"{field_name} must be non-negative, got {value!r}"
        return int(value), None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None, f"{field_name} must be an integer, got empty string"
        try:
            parsed = int(stripped, 10)
        except ValueError:
            return None, f"{field_name} must be an integer, got {value!r}"
        if parsed < 0:
            return None, f"{field_name} must be non-negative, got {value!r}"
        return parsed, None
    return None, f"{field_name} must be an integer, got {type(value).__name__}"


def _get_first_present(data: dict, keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _normalize_gemini_tokens(tokens: object) -> tuple[dict[str, int] | None, str | None]:
    if not isinstance(tokens, dict):
        return None, "Gemini tokens payload is missing or not an object"

    field_aliases = {
        "input": ("input", "input_tokens"),
        "prompt": ("prompt", "prompt_tokens"),
        "candidates": ("candidates", "output", "output_tokens", "candidate_tokens"),
        "cached": ("cached", "cached_tokens", "cached_input_tokens"),
        "thoughts": ("thoughts", "thought_tokens", "reasoning_tokens"),
    }

    normalized: dict[str, int] = {}
    for normalized_name, aliases in field_aliases.items():
        value, error = coerce_token_int(_get_first_present(tokens, aliases), f"Gemini {normalized_name}")
        if error:
            return None, error
        assert value is not None
        normalized[normalized_name] = value

    if not any(alias in tokens for alias in field_aliases["prompt"]):
        return None, "Gemini prompt token field is missing"

    return normalized, None


def _is_gemini_count_metric(metric_name: str) -> bool:
    lowered = metric_name.lower()
    terminal = lowered.split(".")[-1]
    if terminal in {
        "count",
        "calls",
        "call_count",
        "tool_calls",
        "tool_call_count",
        "invocations",
        "invocation_count",
    }:
        return True
    return lowered.endswith(".call") or lowered.endswith(".calls")


def _flatten_gemini_tool_counts(data: object, *, prefix: str = "") -> dict[str, int]:
    flattened: dict[str, int] = {}
    if isinstance(data, bool):
        return flattened
    if isinstance(data, int):
        if prefix and _is_gemini_count_metric(prefix):
            flattened[prefix] = data
        return flattened
    if isinstance(data, float):
        if prefix and data.is_integer() and _is_gemini_count_metric(prefix):
            flattened[prefix] = int(data)
        return flattened
    if isinstance(data, dict):
        for key, value in data.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            for nested_key, nested_value in _flatten_gemini_tool_counts(value, prefix=nested_prefix).items():
                flattened[nested_key] = flattened.get(nested_key, 0) + nested_value
    return flattened


def _find_usage_dicts(obj: object, *, depth: int = 0, max_depth: int = 4) -> list[dict]:
    """Find nested usage dicts in a Codex event without assuming one fixed shape."""
    if depth > max_depth or not isinstance(obj, dict):
        return []

    found: list[dict] = []
    usage_value = obj.get("usage")
    if isinstance(usage_value, dict):
        found.append(usage_value)

    for value in obj.values():
        if isinstance(value, dict):
            found.extend(_find_usage_dicts(value, depth=depth + 1, max_depth=max_depth))
    return found


def _normalize_usage_snapshot(usage: dict) -> tuple[dict | None, str | None]:
    fields = ("input_tokens", "cached_input_tokens", "output_tokens")
    normalized: dict[str, int] = {}
    for field_name in fields:
        value, error = coerce_token_int(usage.get(field_name, 0), field_name)
        if error:
            return None, error
        assert value is not None
        normalized[field_name] = value
    return normalized, None


def _merge_codex_usage_snapshots(usage_snapshots: list[dict[str, int]]) -> tuple[dict[str, int], list[dict[str, int]]]:
    """Merge Codex usage snapshots while avoiding duplicate cumulative double counts."""
    if len(usage_snapshots) == 1:
        return usage_snapshots[0], usage_snapshots

    def _dominates(a: dict[str, int], b: dict[str, int]) -> bool:
        return (
            a["input_tokens"] >= b["input_tokens"]
            and a["cached_input_tokens"] >= b["cached_input_tokens"]
            and a["output_tokens"] >= b["output_tokens"]
        )

    unique_snapshots = {
        (
            snapshot["input_tokens"],
            snapshot["cached_input_tokens"],
            snapshot["output_tokens"],
        ): snapshot
        for snapshot in usage_snapshots
    }
    selected_usage = max(unique_snapshots.values(), key=lambda usage: (
        usage["input_tokens"],
        usage["cached_input_tokens"],
        usage["output_tokens"],
    ))
    snapshots_used = sorted(
        unique_snapshots.values(),
        key=lambda usage: (
            usage["input_tokens"],
            usage["cached_input_tokens"],
            usage["output_tokens"],
        ),
    )

    cumulative_in_order = all(
        _dominates(usage_snapshots[i + 1], usage_snapshots[i])
        for i in range(len(usage_snapshots) - 1)
    )
    selected_key = (
        selected_usage["input_tokens"],
        selected_usage["cached_input_tokens"],
        selected_usage["output_tokens"],
    )
    selected_occurrences = sum(
        1
        for snapshot in usage_snapshots
        if (
            snapshot["input_tokens"],
            snapshot["cached_input_tokens"],
            snapshot["output_tokens"],
        ) == selected_key
    )
    cumulative_with_duplicates = selected_occurrences > 1 and all(
        _dominates(selected_usage, snapshot)
        for snapshot in usage_snapshots
    )

    if cumulative_in_order or cumulative_with_duplicates:
        return selected_usage, snapshots_used

    # Treat as independent snapshots and sum exact-unique entries.
    merged = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    for snapshot in snapshots_used:
        merged["input_tokens"] += snapshot["input_tokens"]
        merged["cached_input_tokens"] += snapshot["cached_input_tokens"]
        merged["output_tokens"] += snapshot["output_tokens"]
    return merged, snapshots_used


def parse_codex_tokens(raw_stdout: str) -> TokenUsage:
    """Parse token usage from Codex JSONL output."""
    usage_snapshots: list[dict] = []
    malformed_usages: list[str] = []
    for line in raw_stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        for usage in _find_usage_dicts(event):
            normalized, error = _normalize_usage_snapshot(usage)
            if error:
                malformed_usages.append(error)
                continue
            assert normalized is not None
            usage_snapshots.append(normalized)

    if not usage_snapshots:
        reason = malformed_usages[0] if malformed_usages else "missing Codex usage telemetry"
        return invalid_token_usage(
            reason,
            raw={"usage_errors": malformed_usages} if malformed_usages else {},
        )

    selected_usage, snapshots_used = _merge_codex_usage_snapshots(usage_snapshots)

    input_tokens = selected_usage["input_tokens"]
    cached = selected_usage["cached_input_tokens"]
    output_tokens = selected_usage["output_tokens"]
    raw_usage: dict = selected_usage
    if len(snapshots_used) > 1:
        raw_usage = {
            **selected_usage,
            "usage_snapshots": snapshots_used,
        }

    return TokenUsage(
        input=input_tokens,
        input_cached=cached,
        output=output_tokens,
        thoughts=0,
        billable=input_tokens - cached + output_tokens,
        cost_usd=None,
        cost_source="calculated",
        raw=raw_usage,
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


def parse_codex_execution(raw_stdout: str, latency_ms: int) -> ExecutionMetrics:
    event_count = 0
    tool_calls: dict[str, int] = {}
    for line in raw_stdout.strip().splitlines():
        try:
            event = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        event_count += 1
        event_type = event.get("type", "")
        if "tool" in event_type.lower():
            tool_calls[event_type] = tool_calls.get(event_type, 0) + 1
        item = event.get("item", {})
        item_type = item.get("type", "")
        if "tool" in item_type.lower():
            tool_name = item.get("name") or item.get("tool_name") or item_type
            tool_calls[tool_name] = tool_calls.get(tool_name, 0) + 1

    return ExecutionMetrics(
        latency_ms=latency_ms,
        step_count=max(event_count, 1),
        tool_call_count=sum(tool_calls.values()),
        tool_calls_by_type=tool_calls,
    )


def parse_claude_execution(raw_json: dict, latency_ms: int) -> ExecutionMetrics:
    usage = raw_json.get("usage", {})
    iterations = usage.get("iterations", [])
    server_tool_use = usage.get("server_tool_use", {})
    tool_calls = {name: count for name, count in server_tool_use.items() if count}

    return ExecutionMetrics(
        latency_ms=latency_ms,
        step_count=max(len(iterations), 1),
        tool_call_count=sum(tool_calls.values()),
        tool_calls_by_type=tool_calls,
    )


def parse_gemini_execution(raw_json: dict, latency_ms: int) -> ExecutionMetrics:
    tool_calls = raw_json.get("stats", {}).get("tools", {}) or {}
    normalized = _flatten_gemini_tool_counts(tool_calls)
    return ExecutionMetrics(
        latency_ms=latency_ms,
        step_count=1,
        tool_call_count=sum(normalized.values()),
        tool_calls_by_type=normalized,
    )


def parse_response(
    llm: str,
    raw_stdout: str,
    latency_ms: int,
    codex_model: str | None = None,
) -> tuple[str, TokenUsage, str, ExecutionMetrics]:
    """Parse CLI output into response text, token usage, model name, and execution metrics."""
    if llm == "codex":
        # Check for error responses (timeout, empty response) before JSONL parsing
        try:
            maybe_error = json.loads(raw_stdout.strip())
            if isinstance(maybe_error, dict) and "error" in maybe_error:
                return f"[ERROR] {maybe_error['error']}", TokenUsage(
                    input=0, input_cached=0, output=0, thoughts=0,
                    billable=0, cost_usd=None, cost_source="error",
                    raw=maybe_error,
                ), (codex_model or _detect_codex_model()), ExecutionMetrics(
                    latency_ms=latency_ms,
                    step_count=1,
                    tool_call_count=0,
                    tool_calls_by_type={},
                )
        except (json.JSONDecodeError, ValueError):
            pass  # Not a single JSON object — proceed with JSONL parsing

        # Codex: JSONL format, extract text from item.completed events
        tokens = parse_codex_tokens(raw_stdout)
        model = codex_model or _detect_codex_model()
        text_parts = []
        for line in raw_stdout.strip().splitlines():
            try:
                event = json.loads(line.strip())
                if event.get("type") == "item.completed":
                    item = event.get("item", {})
                    text_parts.append(item.get("text", ""))
            except json.JSONDecodeError:
                continue
        return (
            "\n".join(text_parts).strip(),
            tokens,
            model,
            parse_codex_execution(raw_stdout, latency_ms),
        )

    # Claude and Gemini: single JSON object
    try:
        data = json.loads(raw_stdout)
    except json.JSONDecodeError:
        return raw_stdout, TokenUsage(
            input=0, input_cached=0, output=0, thoughts=0,
            billable=0, cost_usd=None, cost_source="parse_error", raw={},
        ), "unknown", ExecutionMetrics(
            latency_ms=latency_ms,
            step_count=1,
            tool_call_count=0,
            tool_calls_by_type={},
        )

    if "error" in data:
        return f"[ERROR] {data['error']}", TokenUsage(
            input=0, input_cached=0, output=0, thoughts=0,
            billable=0, cost_usd=None, cost_source="error", raw=data,
        ), "unknown", ExecutionMetrics(
            latency_ms=latency_ms,
            step_count=1,
            tool_call_count=0,
            tool_calls_by_type={},
        )

    if llm == "claude":
        tokens = parse_claude_tokens(data)
        text = data.get("result", "")
        # Model from modelUsage keys
        model_usage = data.get("modelUsage", {})
        model = next(iter(model_usage), "unknown")
        return text, tokens, model, parse_claude_execution(data, latency_ms)

    if llm == "gemini":
        tokens = parse_gemini_tokens(data)
        text = data.get("response", "")
        # Model from stats.models keys
        stats = data.get("stats", {})
        models = stats.get("models", {})
        model = next(iter(models), "unknown")
        return text, tokens, model, parse_gemini_execution(data, latency_ms)

    return raw_stdout, TokenUsage(
        input=0, input_cached=0, output=0, thoughts=0,
        billable=0, cost_usd=None, cost_source="unknown_llm", raw={},
    ), "unknown", ExecutionMetrics(
        latency_ms=latency_ms,
        step_count=1,
        tool_call_count=0,
        tool_calls_by_type={},
    )


def raw_usage_input_billable_tokens(raw_usage: dict) -> int:
    """Estimate provider-native billable input tokens from a raw usage payload."""
    if not raw_usage:
        return 0
    if isinstance(raw_usage.get("turns"), list):
        return sum(raw_usage_input_billable_tokens(turn) for turn in raw_usage["turns"])
    if "cache_creation_input_tokens" in raw_usage or "cache_read_input_tokens" in raw_usage:
        return (
            int(raw_usage.get("input_tokens", 0))
            + int(raw_usage.get("cache_creation_input_tokens", 0))
            + int(raw_usage.get("cache_read_input_tokens", 0))
        )
    if "cached_input_tokens" in raw_usage:
        return max(
            int(raw_usage.get("input_tokens", 0)) - int(raw_usage.get("cached_input_tokens", 0)),
            0,
        )
    if "prompt" in raw_usage:
        return max(int(raw_usage.get("prompt", 0)) - int(raw_usage.get("cached", 0)), 0)
    return 0


def raw_usage_output_tokens(raw_usage: dict) -> int:
    """Extract provider-native output tokens from a raw usage payload."""
    if not raw_usage:
        return 0
    if isinstance(raw_usage.get("turns"), list):
        return sum(raw_usage_output_tokens(turn) for turn in raw_usage["turns"])
    if "output_tokens" in raw_usage:
        return int(raw_usage.get("output_tokens", 0))
    if "candidates" in raw_usage:
        return int(raw_usage.get("candidates", 0))
    return 0


def tool_simulation_adjustment(tokens: TokenUsage) -> ToolSimulationAdjustment:
    """Compute a simulation-adjusted billable total without mutating raw measurements."""
    raw = tokens.raw
    if not isinstance(raw, dict):
        return ToolSimulationAdjustment(adjusted_billable=tokens.billable)

    run1 = raw.get("run1")
    run2 = raw.get("run2")
    if not isinstance(run1, dict) or not isinstance(run2, dict):
        return ToolSimulationAdjustment(adjusted_billable=tokens.billable)

    replay_input_billable = raw_usage_input_billable_tokens(run2)
    tool_call_output = raw_usage_output_tokens(run1)
    adjusted_billable = max(tokens.billable - replay_input_billable - tool_call_output, 0)
    return ToolSimulationAdjustment(
        replay_input_billable=replay_input_billable,
        tool_call_output=tool_call_output,
        adjusted_billable=adjusted_billable,
    )


def shuffled_questions_for_run(
    questions: list[dict],
    *,
    run_idx: int,
    seed: int,
) -> list[dict]:
    ordered = list(questions)
    random.Random(seed + run_idx).shuffle(ordered)
    return ordered


def detect_issue8_refusal(question: dict, response_lower: str) -> bool:
    expected_commands = set(question.get("expected_commands", []))
    issue8_commands = expected_commands.intersection(ISSUE8_COMMANDS)
    if not issue8_commands:
        return False
    if any(p.search(response_lower) for p in _ISSUE8_REFUSAL_PATTERNS):
        return True

    for command in issue8_commands:
        if re.search(rf"{command}[\s\S]{{0,160}}not posix(?:-compliant)?", response_lower):
            return True
        if re.search(rf"not posix(?:-compliant)?[\s\S]{{0,160}}{command}", response_lower):
            return True

    return False


def analyze_response(
    question: dict,
    response: str,
    tokens: TokenUsage,
    llm: str,
    execution: ExecutionMetrics,
) -> ResponseAnalysis:
    minimal_answer = question.get("minimal_answer") or question.get("expected_answer") or question.get("expected", "")
    
    # Remove injected tool results to prevent false positives on negative warnings (e.g., "DO NOT USE tar")
    response_for_grading = re.sub(r"\[TOOL RESULT\]:.*?(?=\n\n|\Z)", "", response, flags=re.DOTALL)
    response_lower = response_for_grading.lower()
    
    expected_hits = [
        command for command in question.get("expected_commands", [])
        if re.search(rf"(?<![\\w-]){re.escape(command.lower())}(?![\\w-])", response_lower)
    ]

    trap_hits = []
    for compiled_re in TRAP_PATTERNS_BY_ID.get(question["id"], []):
        if compiled_re.search(response_for_grading):
            trap_hits.append(compiled_re.pattern)

    missing_concepts = [
        concept for concept in question.get("required_concepts", [])
        if concept.lower() not in response_lower
    ]
    issue8_refusal = detect_issue8_refusal(question, response_lower)
    posix_compliant = bool(expected_hits) and not trap_hits and not issue8_refusal

    minimal_word_count = count_words(minimal_answer)
    response_word_count = count_words(response)
    gap_words = max(response_word_count - minimal_word_count, 0)
    verbosity_ratio = round(response_word_count / max(minimal_word_count, 1), 2)

    if issue8_refusal:
        inefficiency_mode = "issue8_stale_knowledge"
    elif trap_hits:
        inefficiency_mode = "non_posix_substitution"
    elif not expected_hits:
        inefficiency_mode = "workaround_instead_of_native_utility"
    elif llm == "codex" and (execution.tool_call_count > 0 or execution.step_count > 20):
        inefficiency_mode = "tool_heavy_detour"
    elif tokens.output > max(minimal_word_count * 12, 150):
        inefficiency_mode = "over_explaining"
    else:
        inefficiency_mode = "minimal_or_near_minimal"

    estimated_excess_output_tokens = (
        tokens.output
        if not posix_compliant
        else max(tokens.output - max(minimal_word_count, 1), 0)
    )

    return ResponseAnalysis(
        minimal_answer=minimal_answer,
        minimal_word_count=minimal_word_count,
        minimal_shell_token_count=count_shell_tokens(minimal_answer),
        response_word_count=response_word_count,
        minimal_answer_gap_words=gap_words,
        verbosity_ratio=verbosity_ratio,
        expected_command_hits=expected_hits,
        trap_hits=trap_hits,
        missing_required_concepts=missing_concepts,
        posix_compliant=posix_compliant,
        issue8_refusal=issue8_refusal,
        inefficiency_mode=inefficiency_mode,
        estimated_excess_output_tokens=estimated_excess_output_tokens,
    )


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


def load_existing_result(provider: str, question: dict, run_k: int) -> QuestionResult | None:
    q_id = question["id"]
    path = result_path(provider, q_id, run_k)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        execution_data = data.get("execution")
        execution = ExecutionMetrics(**execution_data) if execution_data else ExecutionMetrics(
            latency_ms=0,
            step_count=1,
            tool_call_count=0,
            tool_calls_by_type={},
        )
        analysis_data = data.get("analysis")
        if analysis_data and "inefficiency_mode" not in analysis_data and "failure_mode" in analysis_data:
            analysis_data = dict(analysis_data)
            analysis_data["inefficiency_mode"] = analysis_data.pop("failure_mode")
        analysis = ResponseAnalysis(**analysis_data) if analysis_data else analyze_response(
            question=question,
            response=data["response"],
            tokens=TokenUsage(**data["tokens"]),
            llm=data["llm"],
            execution=execution,
        )
        exec_rec_data = data.get("execution_record")
        exec_rec = ExecutionRecord(**exec_rec_data) if exec_rec_data else None
        return QuestionResult(
            id=data["id"], llm=data["llm"], model=data.get("model", "unknown"),
            run_k=data["run_k"],
            question=data["question"], response=data["response"],
            tokens=TokenUsage(**data["tokens"]),
            execution=execution,
            analysis=analysis,
            accuracy=AccuracyGrade(**data["accuracy"]) if data.get("accuracy") else None,
            execution_record=exec_rec,
            cache_state=data["cache_state"], timestamp=data["timestamp"],
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Execution validation (Track 3)
# ---------------------------------------------------------------------------

COMMAND_TIMEOUT_SECONDS = 30
FIXTURE_MANIFEST = FIXTURES_DIR / "manifest.json"

_fixture_manifest_cache: dict | None = None


def load_fixture_manifest() -> dict[str, dict]:
    """Load fixture metadata from fixtures/manifest.json.

    Returns a dict keyed by question ID (e.g. "T01") with fixture_dir,
    exec_validation_type, and exec_setup_note. Keeps benchmark_data.json
    as a frozen dataset — execution metadata lives separately.
    """
    global _fixture_manifest_cache
    if _fixture_manifest_cache is not None:
        return _fixture_manifest_cache
    if not FIXTURE_MANIFEST.exists():
        _fixture_manifest_cache = {}
        return _fixture_manifest_cache
    with open(FIXTURE_MANIFEST) as f:
        data = json.load(f)
    _fixture_manifest_cache = data.get("fixtures", {})
    return _fixture_manifest_cache


def extract_command(response: str, expected_commands: list[str]) -> str:
    """Extract a runnable shell command from LLM prose output.

    Strategy in priority order:
    1. Single short line starting with an expected utility -> return as-is
    2. Fenced code block (``` or `) -> extract contents
    3. Lines starting with $ -> strip $ prefix
    4. Lines starting with an expected utility name
    5. Fallback: return the full response stripped

    Extraction failures surface as exec_exit_code 127 (command not found)
    rather than crashing the run.
    """
    text = response.strip()

    # 1. Single short line starting with an expected utility
    if "\n" not in text and len(text) < 200:
        if any(text.startswith(cmd) for cmd in expected_commands):
            return text

    # 2. Fenced code block — filter by expected_commands to avoid executing
    #    arbitrary code (e.g., "pip install ..." in an earlier code block).
    fenced = re.findall(r"```(?:\w*)\n(.*?)```", text, re.DOTALL)
    if fenced:
        for block_raw in fenced:
            block = block_raw.strip()
            lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith("#")]
            matched = [l for l in lines if any(l.strip().startswith(cmd) for cmd in expected_commands)]
            if matched:
                return "\n".join(matched) if len(matched) > 1 else matched[0]

    # Also check single backtick inline code
    inline = re.findall(r"`([^`]+)`", text)
    for candidate in inline:
        candidate = candidate.strip()
        if any(candidate.startswith(cmd) for cmd in expected_commands):
            return candidate

    # 3. Lines starting with $ (filtered to expected commands only)
    dollar_lines = [l.lstrip("$ ").strip() for l in text.splitlines() if l.strip().startswith("$")]
    for dl in dollar_lines:
        if any(dl.startswith(cmd) for cmd in expected_commands):
            return dl

    # 4. Lines starting with an expected utility
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(cmd) for cmd in expected_commands):
            return stripped

    # 5. Fallback — returns full text; will fail as exit_code 127 if not a valid command
    return text


def setup_fixture(fixture_spec: dict) -> tuple[Path | None, str]:
    """Copy fixture files into a temp directory for isolated execution.

    Returns (temp_dir_path, skip_reason). If skip_reason is non-empty,
    execution should be skipped.
    """
    fixture_name = fixture_spec.get("fixture_dir")
    if not fixture_name:
        return None, "no fixture_dir in spec"
    if not re.match(r'^[A-Za-z0-9_-]+$', fixture_name):
        return None, f"invalid fixture_dir name: {fixture_name}"

    fixture_path = FIXTURES_DIR / fixture_name
    if not fixture_path.is_dir():
        return None, f"fixture directory not found: {fixture_path}"

    temp_dir = Path(tempfile.mkdtemp(prefix=f"posix_exec_{fixture_name}_"))

    # If there's a setup/ subdir, copy its contents; otherwise copy everything
    # except expected_stdout and expected/
    setup_dir = fixture_path / "setup"
    if setup_dir.is_dir():
        shutil.copytree(setup_dir, temp_dir, dirs_exist_ok=True)
    else:
        for item in fixture_path.iterdir():
            if item.name in ("expected_stdout", "expected", "setup_timestamps.sh"):
                continue
            if item.is_dir():
                shutil.copytree(item, temp_dir / item.name)
            else:
                shutil.copy2(item, temp_dir / item.name)

    # Run setup script if present (e.g., for timestamp manipulation).
    # These scripts are part of the trusted fixture corpus, not LLM output.
    setup_script = fixture_path / "setup_timestamps.sh"
    if setup_script.exists():
        proc = subprocess.run(
            ["sh", str(setup_script)],
            cwd=str(temp_dir),
            timeout=5,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, f"setup script failed (exit {proc.returncode}): {proc.stderr[:200]}"

    return temp_dir, ""


def run_command(command: str, cwd: Path, timeout: int = COMMAND_TIMEOUT_SECONDS) -> CommandResult:
    """Execute a shell command in the given working directory.

    Uses shell=True because LLM responses may include pipelines.
    Timeout enforces a 30-second ceiling — slow commands are wrong commands.
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = (time.monotonic() - start) * 1000
        return CommandResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed_ms=round(elapsed, 1),
        )
    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return CommandResult(
            exit_code=124,  # standard timeout exit code
            stdout="",
            stderr=f"TIMEOUT: command exceeded {timeout}s",
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return CommandResult(
            exit_code=127,
            stdout="",
            stderr=str(e),
            elapsed_ms=round(elapsed, 1),
        )


def validate_command_result(
    result: CommandResult, fixture_spec: dict, temp_dir: Path
) -> bool:
    """Validate command output against expected results.

    Validation types:
    - stdout: compare stdout against expected_stdout file (stripped)
    - exit_zero: command exits with code 0
    - file_state: files in temp_dir match expected/ directory
    """
    validation_type = fixture_spec.get("exec_validation_type", "exit_zero")
    fixture_path = FIXTURES_DIR / fixture_spec["fixture_dir"]

    if validation_type == "stdout":
        expected_file = fixture_path / "expected_stdout"
        if not expected_file.exists():
            return False
        expected = expected_file.read_text().strip()
        actual = result.stdout.strip()
        if fixture_spec.get("exec_stdout_unordered", False):
            return sorted(actual.splitlines()) == sorted(expected.splitlines())
        return actual == expected

    elif validation_type == "exit_zero":
        return result.exit_code == 0

    elif validation_type == "file_state":
        expected_dir = fixture_path / "expected"
        if not expected_dir.is_dir():
            return False
        for expected_file in expected_dir.rglob("*"):
            if expected_file.is_dir():
                continue
            rel = expected_file.relative_to(expected_dir)
            actual_file = temp_dir / rel
            if not actual_file.exists():
                return False
            if not filecmp.cmp(str(expected_file), str(actual_file), shallow=False):
                return False
        return True

    return False


def _skip_record(validation_type: str, reason: str) -> ExecutionRecord:
    """Return an ExecutionRecord for a skipped question."""
    return ExecutionRecord(
        command_extracted="",
        exec_success=False,
        exec_attempts=0,  # 0 = skipped, 1 = single attempt
        exec_exit_code=-1,
        exec_stdout="",
        exec_stderr="",
        exec_elapsed_ms=0,
        exec_validation_type=validation_type,
        exec_skipped=True,
        exec_skip_reason=reason,
    )


def execute_question(question: dict, response: str) -> ExecutionRecord:
    """Execute the command from an LLM response against the question's fixture.

    Looks up fixture metadata from fixtures/manifest.json by question ID.
    Phase 1: single-attempt execution only (no retry loop).
    """
    manifest = load_fixture_manifest()
    fixture_spec = manifest.get(question["id"])

    if not fixture_spec:
        return _skip_record("exit_zero", f"no fixture for {question['id']}")

    validation_type = fixture_spec.get("exec_validation_type", "exit_zero")

    temp_dir, skip_reason = setup_fixture(fixture_spec)
    if skip_reason:
        return _skip_record(validation_type, skip_reason)

    try:
        command = extract_command(response, question.get("expected_commands", []))
        result = run_command(command, temp_dir)
        success = validate_command_result(result, fixture_spec, temp_dir)

        return ExecutionRecord(
            command_extracted=command,
            exec_success=success,
            exec_attempts=1,
            exec_exit_code=result.exit_code,
            exec_stdout=result.stdout[:2000] + ("\n[TRUNCATED]" if len(result.stdout) > 2000 else ""),
            exec_stderr=result.stderr[:2000] + ("\n[TRUNCATED]" if len(result.stderr) > 2000 else ""),
            exec_elapsed_ms=result.elapsed_ms,
            exec_validation_type=validation_type,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


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


def grade_response(
    judge: str,
    question: dict,
    response: str,
    *,
    timeout_seconds: int,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> AccuracyGrade:
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

    raw = invoke_cli(
        judge,
        prompt,
        timeout_seconds=timeout_seconds,
        claude_model=claude_model,
        codex_model=codex_model,
    )
    raw_cleaned = strip_cli_noise(raw.stdout)

    # Extract JSON with score field.
    # Strategy: find every { position, try json.loads from each one to find
    # the first valid object containing "score". This avoids greedy over-matching
    # and handles both nested objects and multiple JSON chunks in the response.
    for i, ch in enumerate(raw_cleaned):
        if ch != '{':
            continue
        # Try parsing from this brace to end of string, let json.loads find the boundary
        try:
            decoder = json.JSONDecoder()
            parsed, end = decoder.raw_decode(raw_cleaned, i)
            if isinstance(parsed, dict) and "score" in parsed:
                try:
                    score = max(0, min(2, int(parsed["score"])))
                except (ValueError, TypeError):
                    score = 0
                return AccuracyGrade(score=score, reason=str(parsed.get("reason", "")))
        except (json.JSONDecodeError, ValueError):
            continue

    return AccuracyGrade(score=-1, reason=f"Failed to parse grade: {raw_cleaned[:100]}")


# ---------------------------------------------------------------------------
# Question loading
# ---------------------------------------------------------------------------

def load_questions(question_ids: list[str] | None = None) -> list[dict]:
    """Load questions from the benchmark data file."""
    with open(DATA_FILE) as f:
        data = json.load(f)

    questions = []
    for question in data["questions"]:
        normalized = dict(question)
        normalized.setdefault("minimal_answer", normalized.get("expected_answer", normalized.get("expected", "")))
        questions.append(normalized)

    if question_ids:
        valid_ids = {q["id"] for q in questions}
        unknown = [qid for qid in question_ids if qid not in valid_ids]
        if unknown:
            print(f"  ERROR: Unknown question IDs: {', '.join(unknown)}")
            print(f"  Valid IDs: {', '.join(sorted(valid_ids))}")
            raise SystemExit(1)
        questions = [q for q in questions if q["id"] in question_ids]

    return questions


def validate_posix_bridge(
    questions: list[dict],
    *,
    require_full_coverage: bool,
) -> list[str]:
    """Validate semantic bridge completeness and return human-readable errors."""
    errors: list[str] = []

    try:
        tldr = _load_posix_tldr()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return [f"Could not load {POSIX_TLDR_FILE.name}: {e}"]

    try:
        utilities = _load_posix_utilities()
    except (FileNotFoundError, OSError) as e:
        return [f"Could not load {POSIX_UTILITIES_FILE.name}: {e}"]

    core_text = _load_posix_core()
    if core_text is None:
        errors.append(f"Could not load {POSIX_CORE_FILE.name}.")
        core_text = ""
    core_lower = core_text.lower()

    tldr_keys = {str(name).lower() for name in tldr.keys()}
    utility_set = set(utilities)

    def in_core(name: str) -> bool:
        return bool(re.search(rf"\b{re.escape(name)}\b", core_lower))

    def preview(items: list[str], limit: int = 20) -> str:
        if not items:
            return ""
        if len(items) <= limit:
            return ", ".join(items)
        return f"{', '.join(items[:limit])}, ... (+{len(items) - limit} more)"

    expected_commands = sorted({
        command.strip().lower()
        for question in questions
        for command in question.get("expected_commands", [])
        if isinstance(command, str) and command.strip()
    })

    missing_expected_tldr = [cmd for cmd in expected_commands if cmd not in tldr_keys]
    if missing_expected_tldr:
        errors.append(
            "Missing expected commands in "
            f"{POSIX_TLDR_FILE.name}: {preview(missing_expected_tldr)}"
        )

    missing_expected_core = [cmd for cmd in expected_commands if not in_core(cmd)]
    if missing_expected_core:
        errors.append(
            "Missing expected commands in "
            f"{POSIX_CORE_FILE.name}: {preview(missing_expected_core)}"
        )

    empty_tldr_entries = sorted(
        str(name)
        for name, value in tldr.items()
        if not isinstance(value, list) or not any(isinstance(item, str) and item.strip() for item in value)
    )
    if empty_tldr_entries:
        errors.append(f"Empty or invalid entries in {POSIX_TLDR_FILE.name}: {preview(empty_tldr_entries)}")

    if require_full_coverage:
        missing_tldr_utility = [name for name in utilities if name not in tldr_keys]
        if missing_tldr_utility:
            errors.append(
                "Missing POSIX utilities in "
                f"{POSIX_TLDR_FILE.name}: {preview(missing_tldr_utility)}"
            )

        missing_core_utility = [name for name in utilities if not in_core(name)]
        if missing_core_utility:
            errors.append(
                "Missing POSIX utilities in "
                f"{POSIX_CORE_FILE.name}: {preview(missing_core_utility)}"
            )

        unknown_tldr_entries = sorted(tldr_keys - utility_set)
        if unknown_tldr_entries:
            errors.append(
                "Unknown utility keys in "
                f"{POSIX_TLDR_FILE.name}: {preview(unknown_tldr_entries)}"
            )

    return errors


# ---------------------------------------------------------------------------
# Single question run
# ---------------------------------------------------------------------------

def run_single(
    llm: str,
    question: dict,
    run_k: int,
    judge: str | None,
    delay: float,
    timeout_seconds: int,
    inject_posix: bool = False,
    execute: bool = False,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> QuestionResult:
    """Run a single question against a single LLM and return the result."""
    if delay > 0:
        with _provider_locks[llm]:
            time.sleep(delay)

    q_id = question["id"]
    # Benchmark prompt must remain the raw user task. Do not prime with "POSIX"
    # framing, because that leaks the answer space and corrupts the measurement.
    prompt = question["question"]

    if inject_posix:
        core_md = _load_posix_core()
        if core_md is None:
            print(f"  [{q_id}] Skipping POSIX injection — posix-core.md not available")
        else:
            prompt = f"{core_md}\n\nTOOL INSTRUCTION: You must use the get_posix_syntax tool for any non-trivial command. Output exactly: TOOL_CALL: get_posix_syntax(command) and stop. Do not guess syntax.\n\nTASK:\n{prompt}"


    # Detect cache state (first call to this provider = cold)
    cache_state = "warm" if already_completed(llm, q_id, 0) else "unknown"

    invocation = invoke_cli(
        llm,
        prompt,
        timeout_seconds=timeout_seconds,
        claude_model=claude_model,
        codex_model=codex_model,
    )
    response_text, tokens, model, execution = parse_response(
        llm,
        invocation.stdout,
        invocation.latency_ms,
        codex_model=codex_model,
    )

    # Determine cache state from actual token data
    if tokens.input_cached > 0:
        cache_state = "warm"
    else:
        cache_state = "cold"


    if inject_posix and "TOOL_CALL: get_posix_syntax(" in response_text:
        match = TOOL_CALL_PATTERN.search(response_text)
        if match:
            cmd = normalize_utility_name(match.group(1))
            if not cmd:
                match = None
        if match and cmd:
            try:
                tldr = _load_posix_tldr()
                syntax = tldr.get(
                    cmd,
                    [
                        (
                            f"Utility '{cmd}' is not yet covered by the local syntax index. "
                            "Continue cautiously and prefer POSIX.1-2024 Issue 8 syntax only."
                        )
                    ],
                )
            except (FileNotFoundError, json.JSONDecodeError):
                syntax = ["Error reading posix-tldr.json"]

            tool_call = f"TOOL_CALL: get_posix_syntax({cmd})"
            follow_up = (
                f"{prompt}\n\nAssistant: {tool_call}\n\n"
                f"TOOL_RESULT:\n{json.dumps(syntax)}\nNow complete the task."
            )
            inv2 = invoke_cli(
                llm,
                follow_up,
                timeout_seconds=timeout_seconds,
                claude_model=claude_model,
                codex_model=codex_model,
            )
            resp2, tok2, _, exec2 = parse_response(
                llm,
                inv2.stdout,
                inv2.latency_ms,
                codex_model=codex_model,
            )

            response_text = f"{tool_call}\n\n[TOOL RESULT]: {syntax}\n\n{resp2}"

            # Keep the raw totals intact; adjusted reporting is derived later.
            tokens = TokenUsage(
                input=tokens.input + tok2.input,
                input_cached=tokens.input_cached + tok2.input_cached,
                output=tokens.output + tok2.output,
                thoughts=tokens.thoughts + tok2.thoughts,
                billable=tokens.billable + tok2.billable,
                cost_usd=((tokens.cost_usd or 0) + (tok2.cost_usd or 0)) if (tokens.cost_usd is not None or tok2.cost_usd is not None) else None,
                cost_source=tokens.cost_source,
                raw={"run1": tokens.raw, "run2": tok2.raw}
            )
            
            # Explicitly log the tool call success
            by_type = execution.tool_calls_by_type.copy()
            by_type["get_posix_syntax"] = by_type.get("get_posix_syntax", 0) + 1
            
            execution = ExecutionMetrics(
                latency_ms=execution.latency_ms + exec2.latency_ms,
                step_count=execution.step_count + exec2.step_count + 1,
                tool_call_count=execution.tool_call_count + exec2.tool_call_count + 1,
                tool_calls_by_type=by_type
            )

    analysis = analyze_response(question, response_text, tokens, llm, execution)

    # Grade if judge is specified and question has expected answer
    accuracy = None
    if judge and ("expected_answer" in question or "expected" in question):
        accuracy = grade_response(
            judge,
            question,
            response_text,
            timeout_seconds=timeout_seconds,
            claude_model=claude_model,
            codex_model=codex_model,
        )

    # Track 3: execute the extracted command if --execute was passed
    exec_record = None
    if execute:
        exec_record = execute_question(question, response_text)

    return QuestionResult(
        id=q_id,
        llm=llm,
        model=model,
        run_k=run_k,
        question=question["question"],
        response=response_text,
        tokens=tokens,
        execution=execution,
        analysis=analysis,
        accuracy=accuracy,
        execution_record=exec_record,
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

_provider_locks: dict[str, threading.Lock] = {
    "claude": threading.Lock(),
    "gemini": threading.Lock(),
    "codex": threading.Lock(),
}


def run_provider_batch(
    llm: str,
    questions: list[dict],
    k: int,
    judge: str | None,
    delay: float,
    timeout_seconds: int,
    max_workers: int | None,
    seed: int,
    inject_posix: bool = False,
    execute: bool = False,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> list[QuestionResult]:
    """Run all questions for a single provider with concurrency."""
    workers = max_workers or PROVIDER_CONCURRENCY.get(llm, 2)
    results: list[QuestionResult] = []
    tasks_to_run = []

    for run_idx in range(k):
        for q in shuffled_questions_for_run(questions, run_idx=run_idx, seed=seed):
            if already_completed(llm, q["id"], run_idx):
                existing = load_existing_result(llm, q, run_idx)
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
            future = pool.submit(
                run_single,
                llm,
                q,
                run_idx,
                judge,
                delay,
                timeout_seconds,
                inject_posix,
                execute,
                claude_model,
                codex_model,
            )
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
                    exec_info = ""
                    if result.execution_record and not result.execution_record.exec_skipped:
                        sym = "✓" if result.execution_record.exec_success else "✗"
                        exec_info = f" exec:{sym}"
                    print(
                        f"  [{q_id}] run {run_idx} — "
                        f"in:{result.tokens.input} out:{result.tokens.output} "
                        f"cached:{result.tokens.input_cached} "
                        f"thoughts:{result.tokens.thoughts} "
                        f"billable:{result.tokens.billable} "
                        f"lat:{result.execution.latency_ms}ms "
                        f"mode:{result.analysis.inefficiency_mode}"
                        f"{acc}{exec_info}"
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
    timeout_seconds: int,
    max_workers: int | None,
    dry_run: bool,
    seed: int,
    inject_posix: bool = False,
    execute: bool = False,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> dict[str, list[QuestionResult]]:
    """Run the full benchmark across all providers."""
    total_calls = len(questions) * len(llms) * k

    mode_label = "Track 1 (Raw)"
    if inject_posix and execute:
        mode_label = "Track 3b (Step-Up + Execute)"
    elif execute:
        mode_label = "Track 3a (Raw + Execute)"
    elif inject_posix:
        mode_label = "Track 2 (Step-Up)"

    manifest = load_fixture_manifest() if execute else {}
    exec_qs = [q for q in questions if q["id"] in manifest] if execute else []

    print(f"\n{'=' * 60}")
    print(f"  POSIX Token Efficiency Benchmark v0.4")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {mode_label}")
    print(f"  LLMs: {', '.join(llms)}")
    print(f"  Judge: {judge or 'none (token-only mode)'}")
    print(f"  Questions: {len(questions)}, K={k} runs each")
    if execute:
        print(f"  Executable fixtures: {len(exec_qs)}/{len(questions)}")
    print(f"  Shuffle seed: {seed}")
    print(f"  CLI timeout: {timeout_seconds}s")
    print(f"  Total calls: {total_calls}")
    print(f"{'=' * 60}\n")

    if dry_run:
        for run_idx in range(k):
            ordered = shuffled_questions_for_run(questions, run_idx=run_idx, seed=seed)
            ids = ", ".join(q["id"] for q in ordered)
            print(f"  Run {run_idx} order: {ids}")
        if execute:
            print(f"\n  Would execute commands for {len(exec_qs)} questions with fixtures.")
        print(f"\n  Would make {total_calls} CLI invocations.")
        return {}

    all_results: dict[str, list[QuestionResult]] = {}

    # Run all providers in parallel
    with ThreadPoolExecutor(max_workers=len(llms)) as provider_pool:
        provider_futures = {}
        for llm in llms:
            print(f"--- {llm.upper()} ---\n")
            future = provider_pool.submit(
                run_provider_batch,
                llm,
                questions,
                k,
                judge,
                delay,
                timeout_seconds,
                max_workers,
                seed,
                inject_posix,
                execute,
                claude_model,
                codex_model,
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
    """Print a formatted benchmark report with efficiency and inefficiency-mode metrics."""
    if not all_results:
        return

    q_lookup = {q["id"]: q for q in questions}

    print(f"\n{'=' * 70}")
    print(f"  POSIX TOKEN EFFICIENCY REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Spec: POSIX.1-2024 (Issue 8) — 155 utilities")
    print(f"{'=' * 70}\n")

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
        latency = [r.execution.latency_ms for r in valid]
        steps = [r.execution.step_count for r in valid]
        excess = [r.analysis.estimated_excess_output_tokens for r in valid]
        costs = [r.tokens.cost_usd for r in valid if r.tokens.cost_usd is not None]
        compliant = [r for r in valid if r.analysis.posix_compliant]
        issue8_refusals = [r for r in valid if r.analysis.issue8_refusal]
        inefficiency_modes = Counter(r.analysis.inefficiency_mode for r in valid)
        adjustments = [tool_simulation_adjustment(r.tokens) for r in valid]

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
        print(f"    Latency ms:     {stats(latency)}")
        print(f"    Step count:     {stats(steps)}")
        print(f"    Excess output:  {stats(excess)}")
        if costs:
            print(f"    Cost USD:       {stats(costs)}")
            print(f"    Total cost:     ${sum(costs):.4f}")
        total_replay_input = sum(a.replay_input_billable for a in adjustments)
        total_tool_call_output = sum(a.tool_call_output for a in adjustments)
        if total_replay_input or total_tool_call_output:
            adjusted_billable = [a.adjusted_billable for a in adjustments]
            print(f"    Tool-sim replay input:  {stats([a.replay_input_billable for a in adjustments])}")
            print(f"    Tool-call stub output:  {stats([a.tool_call_output for a in adjustments])}")
            print(f"    Billable (sim-adjusted): {stats(adjusted_billable)}")
        print()

        errors = [r for r in results if r.response.startswith("[ERROR]")]
        if errors:
            print(f"    Errors: {len(errors)}/{len(results)} questions failed")
            for r in errors:
                error_type = r.response.removeprefix("[ERROR] ")
                print(f"      {r.id}: {error_type} (after {r.execution.latency_ms}ms)")
            print()

        cold = [r for r in valid if r.cache_state == "cold"]
        warm = [r for r in valid if r.cache_state == "warm"]
        print(f"    Cache: {len(cold)} cold, {len(warm)} warm, {len(valid) - len(cold) - len(warm)} unknown")
        print(
            f"    POSIX compliance: {len(compliant)}/{len(valid)} "
            f"({len(compliant) / len(valid) * 100:.0f}%)"
        )
        print(f"    Issue 8 refusals: {len(issue8_refusals)}")
        print(f"    Tool calls: {sum(r.execution.tool_call_count for r in valid)} total")
        if inefficiency_modes:
            print(
                "    Inefficiency modes: "
                + ", ".join(f"{mode}={count}" for mode, count in inefficiency_modes.most_common())
            )

        graded = [r for r in valid if r.accuracy and r.accuracy.score >= 0]
        if graded:
            scores = [r.accuracy.score for r in graded]
            total = sum(scores)
            max_score = len(graded) * 2
            pct = (total / max_score * 100) if max_score else 0
            print(f"    Accuracy:  {total}/{max_score} ({pct:.0f}%)")

        # Track 3: execution validation summary
        executed = [r for r in valid if r.execution_record and not r.execution_record.exec_skipped]
        if executed:
            successes = sum(1 for r in executed if r.execution_record.exec_success)
            rate = successes / len(executed) * 100
            print(f"    Execution: {successes}/{len(executed)} passed ({rate:.0f}%)")

        print()

    print(f"  {'─' * 70}")
    print(f"  MINIMAL-ANSWER GAP BY TIER")
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
            excess_tokens = [r.analysis.estimated_excess_output_tokens for r in tier_results]
            latency_ms = [r.execution.latency_ms for r in tier_results]
            compliant_count = sum(1 for r in tier_results if r.analysis.posix_compliant)
            mean_out = sum(out_tokens) / len(out_tokens)
            mean_excess = sum(excess_tokens) / len(excess_tokens)
            mean_latency = sum(latency_ms) / len(latency_ms)
            print(
                f"    {tier_name}: {len(tier_results)} questions, "
                f"output mean={mean_out:.0f} excess mean={mean_excess:.0f} "
                f"latency mean={mean_latency:.0f}ms compliant={compliant_count}/{len(tier_results)}"
            )

        print()

    print(f"  {'─' * 70}")
    print(f"  TASK SCORECARDS (sorted by estimated excess output)")
    print(f"  {'─' * 70}\n")

    all_valid = []
    for results in all_results.values():
        all_valid.extend(r for r in results if r.tokens.billable > 0)

    by_excess = sorted(all_valid, key=lambda r: r.analysis.estimated_excess_output_tokens, reverse=True)
    for r in by_excess:
        tier = q_lookup.get(r.id, {}).get("tier", "?")
        compliance = "posix" if r.analysis.posix_compliant else "miss"
        print(
            f"    {r.llm:>8} [{r.id}] T{tier} "
            f"out:{r.tokens.output:>5} excess:{r.analysis.estimated_excess_output_tokens:>5} "
            f"lat:{r.execution.latency_ms:>5}ms gap:{r.analysis.minimal_answer_gap_words:>4}w "
            f"{compliance:>5} {r.analysis.inefficiency_mode}"
        )
        print(f"             {r.question[:65]}")
        print(f"             minimal: {r.analysis.minimal_answer}")

    print()


def save_summary(all_results: dict[str, list[QuestionResult]]) -> Path:
    """Save a combined summary JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_path = RESULTS_DIR / f"summary-{ts}.json"

    summary = {
        "version": "0.4",
        "timestamp": ts,
        "spec": "POSIX.1-2024 (Issue 8)",
        "utilities_count": 155,
        "llms": {},
    }

    for llm, results in all_results.items():
        valid = [r for r in results if r.tokens.billable > 0]
        model = valid[0].model if valid else "unknown"
        inefficiency_modes = Counter(r.analysis.inefficiency_mode for r in valid)
        adjustments = [tool_simulation_adjustment(r.tokens) for r in valid]
        summary["llms"][llm] = {
            "model": model,
            "total_results": len(results),
            "valid_results": len(valid),
            "total_billable_tokens": sum(r.tokens.billable for r in valid),
            "total_simulation_adjusted_billable_tokens": sum(
                adjustment.adjusted_billable for adjustment in adjustments
            ),
            "total_tool_simulation_replay_input_tokens": sum(
                adjustment.replay_input_billable for adjustment in adjustments
            ),
            "total_tool_call_stub_output_tokens": sum(
                adjustment.tool_call_output for adjustment in adjustments
            ),
            "total_output_tokens": sum(r.tokens.output for r in valid),
            "total_estimated_excess_output_tokens": sum(
                r.analysis.estimated_excess_output_tokens for r in valid
            ),
            "total_cost_usd": sum(
                r.tokens.cost_usd for r in valid if r.tokens.cost_usd is not None
            ),
            "mean_output_tokens": (
                sum(r.tokens.output for r in valid) / len(valid) if valid else 0
            ),
            "mean_latency_ms": (
                sum(r.execution.latency_ms for r in valid) / len(valid) if valid else 0
            ),
            "mean_step_count": (
                sum(r.execution.step_count for r in valid) / len(valid) if valid else 0
            ),
            "posix_compliance_rate": (
                sum(1 for r in valid if r.analysis.posix_compliant) / len(valid)
                if valid else 0
            ),
            "issue8_refusal_count": sum(1 for r in valid if r.analysis.issue8_refusal),
            "inefficiency_modes": dict(inefficiency_modes),
            # Back-compat for older compare/report tooling.
            "failure_modes": dict(inefficiency_modes),
            "errors": [
                {
                    "question_id": r.id,
                    "error": r.response.removeprefix("[ERROR] "),
                    "latency_ms": r.execution.latency_ms,
                }
                for r in results
                if r.response.startswith("[ERROR]")
            ],
        }

        # Track 3: execution validation metrics
        executed = [r for r in valid if r.execution_record and not r.execution_record.exec_skipped]
        if executed:
            successes = sum(1 for r in executed if r.execution_record.exec_success)
            summary["llms"][llm]["exec_success_rate"] = successes / len(executed)
            summary["llms"][llm]["exec_attempted"] = len(executed)
            summary["llms"][llm]["exec_passed"] = successes

    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"  Summary saved: {summary_path}")
    return summary_path


def save_visual_report(
    all_results: dict[str, list[QuestionResult]],
    questions: list[dict],
) -> Path:
    """Save a self-contained HTML report with charts and task scorecards."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = RESULTS_DIR / f"report-{ts}.html"

    q_lookup = {q["id"]: q for q in questions}
    all_valid = [
        result
        for results in all_results.values()
        for result in results
        if result.tokens.billable > 0
    ]
    all_errors = [
        result
        for results in all_results.values()
        for result in results
        if result.response.startswith("[ERROR]")
    ]
    all_flat = [
        result
        for results in all_results.values()
        for result in results
    ]

    def mean(values: list[int | float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def pct(value: float) -> str:
        return f"{value * 100:.0f}%"

    max_output = max((r.tokens.output for r in all_valid), default=1)
    max_excess = max((r.analysis.estimated_excess_output_tokens for r in all_valid), default=1)
    max_latency = max((r.execution.latency_ms for r in all_valid), default=1)

    # --- Model cards ---
    model_cards = []
    for llm, results in all_results.items():
        valid = [r for r in results if r.tokens.billable > 0]
        errors = [r for r in results if r.response.startswith("[ERROR]")]
        if not valid:
            continue
        inefficiency_modes = Counter(r.analysis.inefficiency_mode for r in valid)
        model_cards.append({
            "llm": llm,
            "model": valid[0].model,
            "count": len(valid),
            "total": len(results),
            "error_count": len(errors),
            "compliance_rate": sum(1 for r in valid if r.analysis.posix_compliant) / len(valid),
            "issue8_refusal_count": sum(1 for r in valid if r.analysis.issue8_refusal),
            "mean_output": mean([r.tokens.output for r in valid]),
            "mean_excess": mean([r.analysis.estimated_excess_output_tokens for r in valid]),
            "mean_latency": mean([r.execution.latency_ms for r in valid]),
            "mean_steps": mean([r.execution.step_count for r in valid]),
            "tool_calls": sum(r.execution.tool_call_count for r in valid),
            "total_cost": sum(r.tokens.cost_usd for r in valid if r.tokens.cost_usd is not None),
            "inefficiency_modes": inefficiency_modes,
            "errors": errors,
        })

    # --- Tier breakdown per model ---
    tier_breakdown_rows = []
    for card in model_cards:
        llm = card["llm"]
        valid = [r for r in all_results[llm] if r.tokens.billable > 0]
        for tier_num, tier_label in [(1, "Tier 1 — Common"), (2, "Tier 2 — Less common"), (3, "Tier 3 — Blind spot")]:
            tier_results = [r for r in valid if q_lookup.get(r.id, {}).get("tier") == tier_num]
            if not tier_results:
                continue
            compliant = sum(1 for r in tier_results if r.analysis.posix_compliant)
            tier_breakdown_rows.append({
                "llm": llm,
                "tier_label": tier_label,
                "count": len(tier_results),
                "compliant": compliant,
                "rate": compliant / len(tier_results),
                "mean_output": mean([r.tokens.output for r in tier_results]),
                "mean_excess": mean([r.analysis.estimated_excess_output_tokens for r in tier_results]),
                "mean_latency": mean([r.execution.latency_ms for r in tier_results]),
            })

    top_gap_results = sorted(
        all_valid,
        key=lambda r: r.analysis.estimated_excess_output_tokens,
        reverse=True,
    )[:12]
    issue8_results = [r for r in all_valid if r.analysis.issue8_refusal][:8]

    # --- All results for full scorecard ---
    all_sorted = sorted(
        all_flat,
        key=lambda r: (r.id, r.llm),
    )

    def metric_bar(value: float, max_value: float, label: str, suffix: str = "") -> str:
        width = 0 if max_value <= 0 else min(100, (value / max_value) * 100)
        return (
            "<div class='metric-row'>"
            f"<div class='metric-label'>{escape(label)}</div>"
            "<div class='metric-track'>"
            f"<div class='metric-fill' style='width:{width:.1f}%'></div>"
            "</div>"
            f"<div class='metric-value'>{value:.0f}{escape(suffix)}</div>"
            "</div>"
        )

    def result_card(result: QuestionResult) -> str:
        tier = q_lookup.get(result.id, {}).get("tier", "?")
        is_error = result.response.startswith("[ERROR]")
        status = "ERROR" if is_error else ("POSIX" if result.analysis.posix_compliant else "MISS")
        status_class = "error" if is_error else ("good" if result.analysis.posix_compliant else "bad")
        excerpt = result.response.strip()[:480]
        return f"""
        <article class="task-card">
          <div class="task-meta">
            <span class="pill model-pill">{escape(result.llm.upper())}</span>
            <span class="pill tier-pill">T{tier}</span>
            <span class="pill mode-pill {escape(status_class)}">{escape(status)}</span>
            <span class="pill failure-pill">{escape(result.analysis.inefficiency_mode.replace('_', ' ') if not is_error else result.response.removeprefix('[ERROR] '))}</span>
          </div>
          <h3>{escape(result.id)} · {escape(result.question)}</h3>
          <div class="task-stats">
            <div><strong>Output</strong><span>{result.tokens.output}</span></div>
            <div><strong>Excess</strong><span>{result.analysis.estimated_excess_output_tokens}</span></div>
            <div><strong>Latency</strong><span>{result.execution.latency_ms} ms</span></div>
            <div><strong>Gap</strong><span>{result.analysis.minimal_answer_gap_words} words</span></div>
          </div>
          <div class="code-pair">
            <div>
              <label>Minimal POSIX answer</label>
              <pre>{escape(result.analysis.minimal_answer)}</pre>
            </div>
            <div>
              <label>Model response{' (error)' if is_error else ' excerpt'}</label>
              <pre>{escape(excerpt)}</pre>
            </div>
          </div>
        </article>
        """

    # --- Question reference rows ---
    TIER_NAMES = {1: "Common", 2: "Less common", 3: "Blind spot"}
    question_rows = []
    for q in questions:
        traps = q.get("posix_traps", [])
        trap_html = ", ".join(escape(t) for t in traps) if traps else '<span class="no-traps">None</span>'
        cmds = q.get("expected_commands", [])
        cmds_html = " ".join(f'<code>{escape(c)}</code>' for c in cmds)
        tier = q.get("tier", "?")
        tier_name = TIER_NAMES.get(tier, "?")
        question_rows.append(f"""
        <tr>
          <td class="q-id"><strong>{escape(q['id'])}</strong></td>
          <td><span class="pill tier-pill tier-{tier}">Tier {tier}</span></td>
          <td class="q-category">{escape(q.get('category', '').replace('_', ' '))}</td>
          <td class="q-text">{escape(q['question'])}</td>
          <td class="q-cmds">{cmds_html}</td>
          <td><pre class="q-answer">{escape(q.get('expected_answer', ''))}</pre></td>
          <td class="q-traps">{trap_html}</td>
        </tr>
        """)

    # --- Model sections ---
    model_sections = []
    for card in model_cards:
        inefficiency_summary = ", ".join(
            f"{name.replace('_', ' ')}={count}"
            for name, count in card["inefficiency_modes"].most_common()
        )
        error_html = ""
        if card["errors"]:
            error_items = "".join(
                f"<li><strong>{escape(r.id)}</strong>: {escape(r.response.removeprefix('[ERROR] '))} "
                f"(after {r.execution.latency_ms:,}ms)</li>"
                for r in card["errors"]
            )
            error_html = f"""
            <div class="error-list">
              <span class="error-label">Errors ({card['error_count']})</span>
              <ul>{error_items}</ul>
            </div>
            """
        cost_line = ""
        if card["total_cost"] > 0:
            cost_line = f"<div><span>Total cost</span><strong>${card['total_cost']:.4f}</strong></div>"

        model_sections.append(f"""
        <section class="model-card">
          <div class="model-heading">
            <div>
              <p class="eyebrow">{escape(card["llm"].upper())}</p>
              <h2>{escape(card["model"])}</h2>
            </div>
            <div class="compliance-badge">{pct(card["compliance_rate"])}</div>
          </div>
          <p class="caption">{card["count"]}/{card["total"]} tasks valid · {card["issue8_refusal_count"]} Issue 8 refusals · {card["tool_calls"]} tool calls</p>
          {metric_bar(card["mean_output"], max(max_output, 1), "Mean output tokens")}
          {metric_bar(card["mean_excess"], max(max_excess, 1), "Mean excess output")}
          {metric_bar(card["mean_latency"], max(max_latency, 1), "Mean latency", " ms")}
          <div class="micro-stats">
            <div><span>Mean steps</span><strong>{card["mean_steps"]:.1f}</strong></div>
            {cost_line}
            <div><span>Inefficiency modes</span><strong>{escape(inefficiency_summary or 'none')}</strong></div>
          </div>
          {error_html}
        </section>
        """)

    # --- Tier breakdown table ---
    tier_table_rows = []
    for row in tier_breakdown_rows:
        rate_color = "good" if row["rate"] >= 0.7 else ("bad" if row["rate"] < 0.5 else "muted")
        tier_table_rows.append(f"""
        <tr>
          <td>{escape(row['llm'].upper())}</td>
          <td>{escape(row['tier_label'])}</td>
          <td class="{rate_color}">{row['compliant']}/{row['count']} ({pct(row['rate'])})</td>
          <td>{row['mean_output']:.0f}</td>
          <td>{row['mean_excess']:.0f}</td>
          <td>{row['mean_latency']:.0f}ms</td>
        </tr>
        """)

    issue8_section = "".join(result_card(result) for result in issue8_results) or (
        "<p class='empty-state'>No Issue 8 refusals were detected in this run.</p>"
    )
    top_gap_section = "".join(result_card(result) for result in top_gap_results)
    all_results_section = "".join(result_card(result) for result in all_sorted)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POSIX Benchmark Report</title>
  <style>
    :root {{
      --bg: #f5f0e8;
      --paper: rgba(255, 250, 241, 0.88);
      --ink: #181512;
      --muted: #655a4d;
      --accent: #bf5b2c;
      --accent-soft: #e6b89d;
      --steel: #24464e;
      --line: rgba(24, 21, 18, 0.12);
      --good: #2f6b47;
      --bad: #8a2e2e;
      --warn: #9a6b1b;
      --shadow: 0 24px 80px rgba(43, 26, 14, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(191, 91, 44, 0.18), transparent 32%),
        radial-gradient(circle at top right, rgba(36, 70, 78, 0.15), transparent 24%),
        linear-gradient(180deg, #f8f3ea, var(--bg));
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }}
    .frame {{
      width: min(1240px, calc(100vw - 48px));
      margin: 24px auto 64px;
    }}

    /* --- Hero --- */
    .hero {{
      background: linear-gradient(140deg, rgba(255,250,241,0.95), rgba(246,235,221,0.92));
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
      padding: 40px;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -80px -80px auto;
      width: 240px;
      height: 240px;
      background: conic-gradient(from 45deg, rgba(191,91,44,0.12), rgba(36,70,78,0.16), transparent 70%);
      border-radius: 50%;
      filter: blur(4px);
    }}
    .eyebrow {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 12px;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    h1, h2, h3 {{
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      letter-spacing: -0.02em;
      margin: 0;
    }}
    h1 {{
      font-size: clamp(40px, 6vw, 72px);
      line-height: 0.95;
      max-width: 900px;
    }}
    .hero p, .intro-text {{
      max-width: 760px;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.55;
    }}
    .intro-text {{ margin: 16px 0 0; font-size: 15px; line-height: 1.65; }}
    .hero-grid, .model-grid, .task-grid {{
      display: grid;
      gap: 20px;
    }}
    .hero-grid {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-top: 28px;
    }}
    .hero-stat, .model-card, .task-card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .hero-stat {{ padding: 20px; }}
    .hero-stat span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .hero-stat strong {{
      font-size: 34px;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }}

    /* --- Sections --- */
    .section {{
      margin-top: 28px;
      padding: 28px;
      background: rgba(255, 250, 241, 0.62);
      border: 1px solid var(--line);
      border-radius: 28px;
    }}
    .section-header {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .section-header p {{ margin: 0; color: var(--muted); }}

    /* --- Model cards --- */
    .model-grid {{ grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
    .model-card {{ padding: 22px; }}
    .model-heading {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
    }}
    .model-heading h2 {{ font-size: 28px; }}
    .compliance-badge {{
      min-width: 76px;
      padding: 14px 12px;
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(47,107,71,0.14), rgba(47,107,71,0.06));
      color: var(--good);
      text-align: center;
      font-weight: 700;
      font-size: 20px;
    }}
    .caption {{ color: var(--muted); margin: 8px 0 18px; line-height: 1.5; }}
    .metric-row {{
      display: grid;
      grid-template-columns: 130px 1fr 64px;
      gap: 12px;
      align-items: center;
      margin-top: 12px;
    }}
    .metric-label, .metric-value {{ font-size: 13px; color: var(--muted); }}
    .metric-track {{
      height: 14px;
      border-radius: 999px;
      background: rgba(36,70,78,0.08);
      overflow: hidden;
    }}
    .metric-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--steel), var(--accent));
      border-radius: 999px;
    }}
    .micro-stats {{
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
      display: grid;
      gap: 12px;
    }}
    .micro-stats div {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: start;
    }}
    .micro-stats span {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .micro-stats strong {{ text-align: right; max-width: 60%; font-size: 14px; }}

    /* --- Error list in model cards --- */
    .error-list {{
      margin-top: 16px;
      padding: 14px;
      border-radius: 16px;
      background: rgba(138, 46, 46, 0.06);
      border: 1px solid rgba(138, 46, 46, 0.15);
    }}
    .error-label {{
      display: block;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--bad);
      margin-bottom: 8px;
    }}
    .error-list ul {{ margin: 0; padding-left: 18px; font-size: 13px; }}
    .error-list li {{ margin-bottom: 4px; color: var(--ink); }}

    /* --- Task cards --- */
    .task-grid {{ grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
    .task-card {{ padding: 18px; }}
    .task-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 7px 10px;
      border-radius: 999px;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.55);
    }}
    .mode-pill.good {{ color: var(--good); }}
    .mode-pill.bad {{ color: var(--bad); }}
    .mode-pill.error {{ color: var(--bad); background: rgba(138,46,46,0.08); }}
    .task-card h3 {{ font-size: 26px; line-height: 1.06; margin-bottom: 16px; }}
    .task-stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    .task-stats div {{
      padding: 12px;
      border-radius: 16px;
      background: rgba(255,255,255,0.56);
      border: 1px solid var(--line);
    }}
    .task-stats strong {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 8px;
    }}
    .task-stats span {{ font-family: "Iowan Old Style", "Palatino Linotype", serif; font-size: 24px; }}
    .code-pair {{ display: grid; gap: 14px; }}
    .code-pair label {{
      display: block;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    pre {{
      margin: 0;
      padding: 14px;
      white-space: pre-wrap;
      word-break: break-word;
      border-radius: 16px;
      background: rgba(24, 21, 18, 0.04);
      border: 1px solid var(--line);
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 13px;
      line-height: 1.5;
    }}
    .empty-state {{ margin: 0; color: var(--muted); }}

    /* --- Question reference table --- */
    .q-table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    .q-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 13px;
    }}
    .q-table th {{
      text-align: left;
      padding: 10px 12px;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      border-bottom: 2px solid var(--line);
      position: sticky;
      top: 0;
      background: rgba(255,250,241,0.95);
    }}
    .q-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    .q-table tr:hover td {{ background: rgba(191,91,44,0.04); }}
    .q-id {{ white-space: nowrap; }}
    .q-text {{ min-width: 260px; line-height: 1.5; }}
    .q-cmds code {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 8px;
      background: rgba(36,70,78,0.1);
      color: var(--steel);
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 13px;
      font-weight: 600;
    }}
    .q-answer {{
      padding: 8px 10px !important;
      font-size: 12px !important;
      border-radius: 10px !important;
      white-space: nowrap;
    }}
    .q-traps {{ font-size: 12px; color: var(--bad); min-width: 180px; }}
    .no-traps {{ color: var(--muted); font-style: italic; }}
    .q-category {{ text-transform: capitalize; white-space: nowrap; color: var(--muted); }}
    .tier-pill {{ font-size: 10px; padding: 4px 8px; }}
    .tier-1 {{ color: var(--good); }}
    .tier-2 {{ color: var(--warn); }}
    .tier-3 {{ color: var(--bad); }}

    /* --- Tier breakdown table --- */
    .tier-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 14px;
    }}
    .tier-table th {{
      text-align: left;
      padding: 10px 14px;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      border-bottom: 2px solid var(--line);
    }}
    .tier-table td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .tier-table tr:hover td {{ background: rgba(191,91,44,0.04); }}
    .tier-table .good {{ color: var(--good); font-weight: 700; }}
    .tier-table .bad {{ color: var(--bad); font-weight: 700; }}
    .tier-table .muted {{ color: var(--warn); font-weight: 700; }}

    /* --- Nav --- */
    .report-nav {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(245,240,232,0.92);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
      margin-bottom: 4px;
    }}
    .report-nav ul {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      gap: 24px;
      justify-content: center;
      flex-wrap: wrap;
    }}
    .report-nav a {{
      color: var(--muted);
      text-decoration: none;
      font-size: 12px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      font-weight: 600;
      padding: 6px 0;
      border-bottom: 2px solid transparent;
      transition: color 0.2s, border-color 0.2s;
    }}
    .report-nav a:hover {{ color: var(--accent); border-bottom-color: var(--accent); }}

    @media (max-width: 760px) {{
      .frame {{ width: min(100vw - 20px, 1240px); margin: 10px auto 40px; }}
      .hero, .section {{ padding: 20px; border-radius: 22px; }}
      .task-stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric-row {{ grid-template-columns: 1fr; }}
      .report-nav ul {{ gap: 12px; }}
    }}
  </style>
</head>
<body>
  <nav class="report-nav">
    <ul>
      <li><a href="#overview">Overview</a></li>
      <li><a href="#models">Models</a></li>
      <li><a href="#tiers">By Tier</a></li>
      <li><a href="#questions">Question Set</a></li>
      <li><a href="#issue8">Issue 8</a></li>
      <li><a href="#top-gaps">Top Gaps</a></li>
      <li><a href="#all-results">All Results</a></li>
    </ul>
  </nav>

  <main class="frame">
    <section class="hero" id="overview">
      <p class="eyebrow">POSIX Token Efficiency Benchmark</p>
      <h1>How many tokens do LLMs waste on shell tasks?</h1>
      <p>Every POSIX task in this benchmark has a short, correct answer using a standard utility. This report measures how far each model's response deviates from that minimal answer — in tokens, latency, and compliance.</p>
      <p class="intro-text">The primary metric is <strong>token cost</strong>, not accuracy. A correct answer in 5 tokens beats a correct answer in 500. An answer that uses GNU extensions or writes a Python script for a one-liner is wasted compute. All questions follow the <strong>Taboo rule</strong> (defined in <code>benchmark_data.json</code>): the expected utility name, the word "POSIX", and any standards language are banned from the question text.</p>
      <div class="hero-grid">
        <div class="hero-stat"><span>Spec</span><strong>Issue 8</strong></div>
        <div class="hero-stat"><span>Utilities</span><strong>155</strong></div>
        <div class="hero-stat"><span>Tasks</span><strong>{len(questions)}</strong></div>
        <div class="hero-stat"><span>Valid</span><strong>{len(all_valid)}/{len(all_flat)}</strong></div>
        <div class="hero-stat"><span>Errors</span><strong style="color: {'var(--bad)' if all_errors else 'var(--good)'}">{len(all_errors)}</strong></div>
      </div>
    </section>

    <section class="section" id="models">
      <div class="section-header">
        <div>
          <p class="eyebrow">Model Comparison</p>
          <h2>Where the excess goes</h2>
        </div>
        <p>{escape(datetime.now().strftime("%Y-%m-%d %H:%M"))}</p>
      </div>
      <div class="model-grid">
        {''.join(model_sections)}
      </div>
    </section>

    <section class="section" id="tiers">
      <div class="section-header">
        <div>
          <p class="eyebrow">Compliance by Tier</p>
          <h2>The deeper the obscurity, the worse the answers</h2>
        </div>
        <p>Tier 1 = common utilities. Tier 2 = less common but POSIX-specified. Tier 3 = utilities LLMs rarely see in training data.</p>
      </div>
      <div class="q-table-wrap">
        <table class="tier-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Tier</th>
              <th>Compliance</th>
              <th>Mean Output</th>
              <th>Mean Excess</th>
              <th>Mean Latency</th>
            </tr>
          </thead>
          <tbody>
            {''.join(tier_table_rows)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section" id="questions">
      <div class="section-header">
        <div>
          <p class="eyebrow">Question Reference</p>
          <h2>All 30 tasks and their expected POSIX answers</h2>
        </div>
        <p>Each question is intent-based. See <code>benchmark_data.json</code> for the Taboo rule that governs question authoring.</p>
      </div>
      <div class="q-table-wrap">
        <table class="q-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Tier</th>
              <th>Category</th>
              <th>Task</th>
              <th>Expected</th>
              <th>Minimal Answer</th>
              <th>POSIX Traps</th>
            </tr>
          </thead>
          <tbody>
            {''.join(question_rows)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section" id="issue8">
      <div class="section-header">
        <div>
          <p class="eyebrow">Issue 8 Watchlist</p>
          <h2>Recency-driven failures</h2>
        </div>
        <p>Answers that still reject <code>readlink</code>, <code>realpath</code>, or <code>timeout</code> as non-POSIX.</p>
      </div>
      <div class="task-grid">
        {issue8_section}
      </div>
    </section>

    <section class="section" id="top-gaps">
      <div class="section-header">
        <div>
          <p class="eyebrow">Top Scorecards</p>
          <h2>Largest minimal-answer gaps</h2>
        </div>
        <p>The 12 responses with the most excess tokens. These are the worst offenders.</p>
      </div>
      <div class="task-grid">
        {top_gap_section}
      </div>
    </section>

    <section class="section" id="all-results">
      <div class="section-header">
        <div>
          <p class="eyebrow">Full Results</p>
          <h2>Every question, every model</h2>
        </div>
        <p>All {len(all_flat)} responses sorted by question ID. Includes errors and timeouts.</p>
      </div>
      <div class="task-grid">
        {all_results_section}
      </div>
    </section>
  </main>
</body>
</html>
"""

    report_path.write_text(html_doc)
    print(f"  Visual report saved: {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# Comparison report
# ---------------------------------------------------------------------------

def save_comparison_report(named_summaries: list[tuple[str, dict]]) -> Path:
    """Generate a standalone HTML report comparing multiple benchmark runs."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = RESULTS_DIR / f"comparison-{ts}.html"

    # Collect all LLM names across all runs
    all_llms: list[str] = []
    for _, summary in named_summaries:
        for llm in summary.get("llms", {}):
            if llm not in all_llms:
                all_llms.append(llm)

    run_names = [name for name, _ in named_summaries]
    num_runs = len(named_summaries)

    def fmt_pct(val: float) -> str:
        return f"{val * 100:.1f}%"

    def delta_cell(current: float, baseline: float, fmt: str = ".0f", suffix: str = "", invert: bool = False) -> str:
        """Render a value with a delta badge vs the first run (baseline)."""
        diff = current - baseline
        if abs(diff) < 0.001:
            badge = ""
        else:
            # For metrics where lower is better (tokens, latency), negative diff is good
            # For compliance rate, positive diff is good
            is_good = (diff < 0) if not invert else (diff > 0)
            color = "good" if is_good else "bad"
            sign = "+" if diff > 0 else ""
            badge = f' <span class="delta {color}">{sign}{diff:{fmt}}{suffix}</span>'
        return f"<td>{current:{fmt}}{suffix}{badge}</td>"

    # --- Per-LLM comparison tables ---
    llm_sections = []
    for llm in all_llms:
        rows_data = []
        for name, summary in named_summaries:
            data = summary.get("llms", {}).get(llm)
            if data:
                rows_data.append((name, data))

        if not rows_data:
            continue

        baseline = rows_data[0][1]

        # Header row
        header_cells = "".join(f"<th>{escape(name)}</th>" for name, _ in rows_data)

        # Metric rows
        metrics = [
            ("Model", "model", "s", "", False),
            ("Valid Results", "valid_results", "d", "", False),
            ("Total Results", "total_results", "d", "", False),
            ("Compliance Rate", "posix_compliance_rate", ".1%", "", True),
            ("Mean Output Tokens", "mean_output_tokens", ".0f", "", False),
            ("Mean Latency (ms)", "mean_latency_ms", ".0f", "", False),
            ("Mean Steps", "mean_step_count", ".1f", "", False),
            ("Total Output Tokens", "total_output_tokens", "d", "", False),
            ("Total Excess Tokens", "total_estimated_excess_output_tokens", "d", "", False),
            ("Total Billable Tokens", "total_billable_tokens", "d", "", False),
            ("Total Cost (USD)", "total_cost_usd", ".4f", "$", False),
            ("Issue 8 Refusals", "issue8_refusal_count", "d", "", False),
        ]

        metric_rows = []
        for label, key, fmt, prefix, invert in metrics:
            cells = []
            for i, (name, data) in enumerate(rows_data):
                val = data.get(key, 0)
                if fmt == "s":
                    cells.append(f"<td>{escape(str(val))}</td>")
                elif fmt == ".1%":
                    if i == 0:
                        cells.append(f"<td>{fmt_pct(val)}</td>")
                    else:
                        diff = val - baseline.get(key, 0)
                        color = "good" if (diff > 0 if invert else diff < 0) else "bad"
                        sign = "+" if diff > 0 else ""
                        badge = f' <span class="delta {color}">{sign}{diff * 100:.1f}pp</span>' if abs(diff) > 0.001 else ""
                        cells.append(f"<td>{fmt_pct(val)}{badge}</td>")
                else:
                    if i == 0:
                        cells.append(f"<td>{prefix}{val:{fmt}}</td>")
                    else:
                        diff = val - baseline.get(key, 0)
                        if abs(diff) < 0.001:
                            badge = ""
                        else:
                            is_good = (diff < 0) if not invert else (diff > 0)
                            color = "good" if is_good else "bad"
                            sign = "+" if diff > 0 else ""
                            badge = f' <span class="delta {color}">{sign}{prefix}{diff:{fmt}}</span>'
                        cells.append(f"<td>{prefix}{val:{fmt}}{badge}</td>")
            metric_rows.append(f"<tr><td class='metric-name'>{escape(label)}</td>{''.join(cells)}</tr>")

        # Inefficiency modes comparison
        def get_modes(payload: dict) -> dict:
            return payload.get("inefficiency_modes", payload.get("failure_modes", {}))

        all_modes: list[str] = []
        for _, data in rows_data:
            for mode in get_modes(data):
                if mode not in all_modes:
                    all_modes.append(mode)

        fm_rows = []
        for mode in all_modes:
            cells = []
            baseline_val = get_modes(baseline).get(mode, 0)
            for i, (name, data) in enumerate(rows_data):
                val = get_modes(data).get(mode, 0)
                if i == 0:
                    cells.append(f"<td>{val}</td>")
                else:
                    diff = val - baseline_val
                    if diff == 0:
                        badge = ""
                    else:
                        color = "good" if diff < 0 else "bad"
                        sign = "+" if diff > 0 else ""
                        badge = f' <span class="delta {color}">{sign}{diff}</span>'
                    cells.append(f"<td>{val}{badge}</td>")
            fm_rows.append(f"<tr><td class='metric-name'>{escape(mode.replace('_', ' '))}</td>{''.join(cells)}</tr>")

        # Errors comparison
        error_rows = []
        for name, data in rows_data:
            errors = data.get("errors", [])
            if errors:
                for err in errors:
                    error_rows.append(f"<tr><td>{escape(name)}</td><td>{escape(err['question_id'])}</td><td>{escape(err['error'])}</td><td>{err['latency_ms']:,}ms</td></tr>")

        error_section = ""
        if error_rows:
            error_section = f"""
            <h3>Errors</h3>
            <table class="comp-table">
              <thead><tr><th>Run</th><th>Question</th><th>Error</th><th>Latency</th></tr></thead>
              <tbody>{''.join(error_rows)}</tbody>
            </table>
            """

        llm_sections.append(f"""
        <section class="section" id="llm-{escape(llm)}">
          <div class="section-header">
            <div>
              <p class="eyebrow">{escape(llm.upper())}</p>
              <h2>Across {len(rows_data)} runs</h2>
            </div>
          </div>
          <table class="comp-table">
            <thead><tr><th>Metric</th>{header_cells}</tr></thead>
            <tbody>{''.join(metric_rows)}</tbody>
          </table>
          <h3>Inefficiency Modes</h3>
          <table class="comp-table">
            <thead><tr><th>Mode</th>{header_cells}</tr></thead>
            <tbody>{''.join(fm_rows)}</tbody>
          </table>
          {error_section}
        </section>
        """)

    # --- Nav ---
    nav_items = "".join(
        f'<li><a href="#llm-{escape(llm)}">{escape(llm.upper())}</a></li>'
        for llm in all_llms
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POSIX Benchmark Comparison</title>
  <style>
    :root {{
      --bg: #f5f0e8;
      --paper: rgba(255, 250, 241, 0.88);
      --ink: #181512;
      --muted: #655a4d;
      --accent: #bf5b2c;
      --steel: #24464e;
      --line: rgba(24, 21, 18, 0.12);
      --good: #2f6b47;
      --bad: #8a2e2e;
      --shadow: 0 24px 80px rgba(43, 26, 14, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(191, 91, 44, 0.18), transparent 32%),
        radial-gradient(circle at top right, rgba(36, 70, 78, 0.15), transparent 24%),
        linear-gradient(180deg, #f8f3ea, var(--bg));
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }}
    .frame {{
      width: min(1240px, calc(100vw - 48px));
      margin: 24px auto 64px;
    }}
    .hero {{
      background: linear-gradient(140deg, rgba(255,250,241,0.95), rgba(246,235,221,0.92));
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
      padding: 40px;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -80px -80px auto;
      width: 240px;
      height: 240px;
      background: conic-gradient(from 45deg, rgba(191,91,44,0.12), rgba(36,70,78,0.16), transparent 70%);
      border-radius: 50%;
      filter: blur(4px);
    }}
    .eyebrow {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 12px;
      letter-spacing: 0.24em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    h1, h2, h3 {{
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      letter-spacing: -0.02em;
      margin: 0;
    }}
    h1 {{ font-size: clamp(40px, 6vw, 72px); line-height: 0.95; max-width: 900px; }}
    h3 {{ margin: 24px 0 12px; font-size: 20px; }}
    .hero p {{ max-width: 760px; color: var(--muted); font-size: 18px; line-height: 1.55; }}
    .hero-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 20px;
      margin-top: 28px;
    }}
    .hero-stat {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 20px;
    }}
    .hero-stat span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .hero-stat strong {{
      font-size: 34px;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }}
    .section {{
      margin-top: 28px;
      padding: 28px;
      background: rgba(255, 250, 241, 0.62);
      border: 1px solid var(--line);
      border-radius: 28px;
    }}
    .section-header {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .section-header p {{ margin: 0; color: var(--muted); }}
    .comp-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 14px;
    }}
    .comp-table th {{
      text-align: left;
      padding: 10px 14px;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      border-bottom: 2px solid var(--line);
      background: rgba(255,250,241,0.95);
      position: sticky;
      top: 44px;
    }}
    .comp-table td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
      font-variant-numeric: tabular-nums;
    }}
    .comp-table tr:hover td {{ background: rgba(191,91,44,0.04); }}
    .metric-name {{
      font-weight: 600;
      white-space: nowrap;
    }}
    .delta {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 8px;
      font-size: 11px;
      font-weight: 700;
      margin-left: 6px;
    }}
    .delta.good {{
      color: var(--good);
      background: rgba(47,107,71,0.1);
    }}
    .delta.bad {{
      color: var(--bad);
      background: rgba(138,46,46,0.1);
    }}
    .report-nav {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(245,240,232,0.92);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
      margin-bottom: 4px;
    }}
    .report-nav ul {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      gap: 24px;
      justify-content: center;
      flex-wrap: wrap;
    }}
    .report-nav a {{
      color: var(--muted);
      text-decoration: none;
      font-size: 12px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      font-weight: 600;
      padding: 6px 0;
      border-bottom: 2px solid transparent;
      transition: color 0.2s, border-color 0.2s;
    }}
    .report-nav a:hover {{ color: var(--accent); border-bottom-color: var(--accent); }}
    .run-list {{ margin: 16px 0 0; padding: 0; list-style: none; }}
    .run-list li {{
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
    }}
    .run-list .run-name {{ font-weight: 700; }}
    .run-list .run-ts {{ color: var(--muted); font-size: 13px; }}
    @media (max-width: 760px) {{
      .frame {{ width: min(100vw - 20px, 1240px); margin: 10px auto 40px; }}
      .hero, .section {{ padding: 20px; border-radius: 22px; }}
    }}
  </style>
</head>
<body>
  <nav class="report-nav">
    <ul>
      <li><a href="#overview">Overview</a></li>
      {nav_items}
    </ul>
  </nav>

  <main class="frame">
    <section class="hero" id="overview">
      <p class="eyebrow">POSIX Benchmark Comparison</p>
      <h1>Side-by-side across {num_runs} runs</h1>
      <p>Comparing benchmark results across different conditions. The first run listed is the baseline — deltas are computed against it.</p>
      <div class="hero-grid">
        <div class="hero-stat"><span>Runs</span><strong>{num_runs}</strong></div>
        <div class="hero-stat"><span>Models</span><strong>{len(all_llms)}</strong></div>
        <div class="hero-stat"><span>Spec</span><strong>Issue 8</strong></div>
      </div>
      <ul class="run-list">
        {''.join(
            f'<li><span class="run-name">{escape(name)}</span>'
            f'<span class="run-ts">{escape(summary.get("timestamp", "?"))}</span></li>'
            for name, summary in named_summaries
        )}
      </ul>
    </section>

    {''.join(llm_sections)}
  </main>
</body>
</html>
"""

    report_path.write_text(html_doc)
    print(f"  Comparison report saved: {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="POSIX Token Efficiency Benchmark",
    )
    parser.add_argument(
        "--llms", nargs="+", default=["claude", "codex"],
        choices=["gemini", "claude", "codex"],
        help="Which LLMs to test (default: claude and codex; add gemini explicitly when API is available)",
    )
    parser.add_argument(
        "--judge", default=None,
        choices=["gemini", "claude", "codex"],
        help="Which LLM grades responses (default: none, token-only mode)",
    )
    parser.add_argument(
        "--questions", nargs="+",
        help="Specific question IDs to run (e.g. T01 T17 T30)",
    )
    parser.add_argument(
        "--k", type=int, default=1,
        help="Number of runs per question (default: 1, use 3+ for statistics)",
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SHUFFLE_SEED,
        help="Seed for randomized question order (default: 20260329)",
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Seconds to pause between API calls (default: 0)",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_CLI_TIMEOUT_SECONDS,
        help="Abort an external CLI call if it exceeds this many seconds (default: 120)",
    )
    parser.add_argument(
        "--claude-model",
        default=DEFAULT_CLAUDE_MODEL,
        help=f"Claude model override for benchmark runs (default: {DEFAULT_CLAUDE_MODEL})",
    )
    parser.add_argument(
        "--codex-model",
        default=DEFAULT_CODEX_MODEL,
        help=f"Codex model override for benchmark runs (default: {DEFAULT_CODEX_MODEL})",
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
        "--validate-bridge", action="store_true",
        help="Validate POSIX bridge completeness (core + tldr) and exit",
    )
    parser.add_argument(
        "--no-grade", action="store_true",
        help="Skip accuracy grading, measure tokens only",
    )
    parser.add_argument(
        "--inject-posix", action="store_true",
        help="Inject POSIX Step-Up Architecture for testing",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Execute extracted commands against fixtures (Track 3)",
    )
    parser.add_argument(
        "--results-dir",
        help="Override results directory for this run (absolute path, or relative path under results/)",
    )
    parser.add_argument(
        "--compare", nargs="+", metavar="NAME=PATH",
        help='Compare multiple runs: "Raw Baseline=results/summary-1.json" "Step-Up=results/summary-2.json"',
    )
    args = parser.parse_args()

    # --- Compare mode: generate comparison report and exit ---
    if args.compare:
        named_summaries: list[tuple[str, dict]] = []
        for entry in args.compare:
            if "=" not in entry:
                parser.error(f"--compare entries must be NAME=PATH, got: {entry}")
            name, path_str = entry.split("=", 1)
            path = Path(path_str)
            if not path.exists():
                parser.error(f"Summary file not found: {path}")
            with open(path) as f:
                named_summaries.append((name.strip(), json.load(f)))
        if len(named_summaries) < 2:
            parser.error("--compare requires at least 2 summary files")
        save_comparison_report(named_summaries)
        return

    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0")

    # Switch results directory based on flag combinations
    global RESULTS_DIR
    if args.inject_posix and args.execute:
        RESULTS_DIR = RESULTS_DIR_STEPUP_EXECUTE
    elif args.execute:
        RESULTS_DIR = RESULTS_DIR_EXECUTE
    elif args.inject_posix:
        RESULTS_DIR = RESULTS_DIR_STEPUP
    if args.results_dir:
        custom_results_dir = Path(args.results_dir)
        if not custom_results_dir.is_absolute():
            relative_parts = [part for part in custom_results_dir.parts if part not in ("", ".")]
            if not relative_parts or relative_parts[0] != "results":
                parser.error("--results-dir relative paths must start with 'results/'")
            if ".." in relative_parts:
                parser.error("--results-dir relative paths must not contain '..'")
            custom_results_dir = SCRIPT_DIR.joinpath(*relative_parts)
        RESULTS_DIR = custom_results_dir

    judge = None if args.no_grade else args.judge

    # Warn if judge is also a test subject
    if judge and judge in args.llms:
        print(f"  Warning: {judge} is both test subject and judge.")
        print(f"  Results may be unreliable due to prompt injection risk.\n")

    questions = load_questions(args.questions)

    if args.validate_bridge or args.inject_posix:
        bridge_errors = validate_posix_bridge(questions, require_full_coverage=True)
        if bridge_errors:
            print("  ERROR: POSIX bridge validation failed:")
            for error in bridge_errors:
                print(f"    - {error}")
            raise SystemExit(1)
        print("  POSIX bridge validation passed: core + tldr cover all 155 utilities.")
        if args.validate_bridge:
            return

    all_results = run_benchmark(
        llms=args.llms,
        questions=questions,
        k=args.k,
        judge=judge,
        delay=args.delay,
        timeout_seconds=args.timeout,
        max_workers=args.max_workers,
        dry_run=args.dry_run,
        seed=args.seed,
        inject_posix=args.inject_posix,
        execute=args.execute,
        claude_model=args.claude_model,
        codex_model=args.codex_model,
    )

    if all_results:
        generate_report(all_results, questions)
        save_summary(all_results)
        save_visual_report(all_results, questions)


if __name__ == "__main__":
    main()
