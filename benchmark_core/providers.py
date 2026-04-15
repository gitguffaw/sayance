import json
import random
import re
import shlex
import subprocess
import time
from pathlib import Path

from benchmark_core import config
from benchmark_core.models import (
    CLIInvocation,
    ExecutionMetrics,
    ResponseAnalysis,
    TokenUsage,
    ToolSimulationAdjustment,
)

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
MODEL_OVERRIDE_AUTO_VALUES = {"", "auto", "default", "cli-default"}
PINNED_CLAUDE_MODEL = "claude-opus-4-6"
PINNED_CODEX_MODEL = "gpt-5.4"
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
    "T11": [r"\bdiff\b", r"\bmd5sum\b", r"\bshasum\b"],
    "T14": [r"\bscreen\b", r"\btmux\b", r"\bdisown\b"],
    "T21": [r"cat\s+-n\b"],
    "T23": [r"<\("],
    "T25": [r"\bmd5sum\b", r"\bsha256sum\b"],
    "T29": [r"\blet\b"],
    "T30": [r"\bbase64\b"],
    "T39": [r"xargs\s+--show-limits\b"],
    "T40": [r"\bionice\b", r"\bcpulimit\b"],
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
            _posix_core_cache = config.POSIX_CORE_FILE.read_text()
        except (FileNotFoundError, OSError) as e:
            print(f"  WARNING: Could not load posix-core.md: {e}")
            return None
    return _posix_core_cache


def _load_posix_tldr() -> dict:
    global _posix_tldr_cache
    if _posix_tldr_cache is None:
        _posix_tldr_cache = json.loads(config.POSIX_TLDR_FILE.read_text())
    return dict(_posix_tldr_cache)


def _load_posix_utilities() -> list[str]:
    global _posix_utilities_cache
    if _posix_utilities_cache is None:
        utilities: list[str] = []
        for line in config.POSIX_UTILITIES_FILE.read_text().splitlines():
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


def normalize_model_override(raw_model: str | None) -> str | None:
    """Normalize optional model override flags.

    Returning None means "use CLI/account default model."
    """
    if raw_model is None:
        return None
    normalized = raw_model.strip()
    if normalized.lower() in MODEL_OVERRIDE_AUTO_VALUES:
        return None
    return normalized


def format_seconds_from_ms(ms: int | float) -> str:
    """Render milliseconds as a concise seconds string."""
    seconds = max(float(ms), 0.0) / 1000.0
    if seconds >= 10:
        return f"{seconds:.1f}s"
    return f"{seconds:.2f}s"


def prune_timestamped_artifacts(directory: Path, pattern: str, keep_path: Path) -> None:
    """Delete old timestamped artifacts, keeping only the most recent path."""
    for candidate in sorted(directory.glob(pattern)):
        if candidate == keep_path:
            continue
        try:
            candidate.unlink()
        except OSError:
            continue


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
    except subprocess.TimeoutExpired as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        stderr_hint = exc.stderr.strip()[:200] if exc.stderr else ""
        return CLIInvocation(
            stdout=f'{{"error": "timeout", "stderr": {json.dumps(stderr_hint)}}}',
            latency_ms=latency_ms,
        )
    except FileNotFoundError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return CLIInvocation(
            stdout=f'{{"error": "{llm} CLI not found"}}',
            latency_ms=latency_ms,
        )


def parse_claude_tokens(raw_json: dict) -> TokenUsage:
    """Parse token usage from Claude CLI JSON output."""
    usage = raw_json.get("usage")
    if usage is None:
        usage = {}
    if not isinstance(usage, dict):
        return invalid_token_usage("Claude usage payload is not an object", raw={"usage": usage})

    input_tokens, error = coerce_token_int(usage.get("input_tokens", 0), "Claude input_tokens")
    if error:
        return invalid_token_usage(error, raw=usage)
    cache_creation, error = coerce_token_int(
        usage.get("cache_creation_input_tokens", 0),
        "Claude cache_creation_input_tokens",
    )
    if error:
        return invalid_token_usage(error, raw=usage)
    cache_read, error = coerce_token_int(
        usage.get("cache_read_input_tokens", 0),
        "Claude cache_read_input_tokens",
    )
    if error:
        return invalid_token_usage(error, raw=usage)
    output_tokens, error = coerce_token_int(usage.get("output_tokens", 0), "Claude output_tokens")
    if error:
        return invalid_token_usage(error, raw=usage)

    assert input_tokens is not None
    assert cache_creation is not None
    assert cache_read is not None
    assert output_tokens is not None
    input_cached = cache_read

    billable = input_tokens + cache_creation + cache_read + output_tokens

    return TokenUsage(
        input=input_tokens,
        input_cached=input_cached,
        output=output_tokens,
        thoughts=0,
        billable=billable,
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
        raw={"models": normalized_models} if len(normalized_models) > 1 else next(iter(normalized_models.values())),
    )


def invalid_token_usage(
    reason: str,
    raw: dict | None = None,
) -> TokenUsage:
    """Return a token payload that preserves explicit usage-invalid state."""
    return TokenUsage(
        input=0,
        input_cached=0,
        output=0,
        thoughts=0,
        billable=0,
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


def _usage_snapshot_key(snapshot: dict[str, int]) -> tuple[int, int, int]:
    return (
        snapshot["input_tokens"],
        snapshot["cached_input_tokens"],
        snapshot["output_tokens"],
    )


def _dominates_usage_snapshot(a: dict[str, int], b: dict[str, int]) -> bool:
    return (
        a["input_tokens"] >= b["input_tokens"]
        and a["cached_input_tokens"] >= b["cached_input_tokens"]
        and a["output_tokens"] >= b["output_tokens"]
    )


def _merge_codex_usage_snapshots(
    usage_snapshots: list[tuple[str, dict[str, int]]],
) -> tuple[dict[str, int], list[dict[str, int]]]:
    """Merge Codex usage snapshots without collapsing independent turn totals."""
    normalized_snapshots = [snapshot for _, snapshot in usage_snapshots]
    if len(normalized_snapshots) == 1:
        return normalized_snapshots[0], normalized_snapshots

    selected_usage = max(normalized_snapshots, key=_usage_snapshot_key)
    all_dominated = all(
        _dominates_usage_snapshot(selected_usage, snapshot)
        for snapshot in normalized_snapshots
    )
    has_non_turn_snapshot = any(
        event_type != "turn.completed"
        for event_type, _ in usage_snapshots
    )
    if has_non_turn_snapshot and all_dominated:
        unique_snapshots: dict[tuple[int, int, int], dict[str, int]] = {}
        for snapshot in normalized_snapshots:
            unique_snapshots[_usage_snapshot_key(snapshot)] = snapshot
        snapshots_used = sorted(unique_snapshots.values(), key=_usage_snapshot_key)
        return selected_usage, snapshots_used

    merged = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    for snapshot in normalized_snapshots:
        merged["input_tokens"] += snapshot["input_tokens"]
        merged["cached_input_tokens"] += snapshot["cached_input_tokens"]
        merged["output_tokens"] += snapshot["output_tokens"]
    return merged, normalized_snapshots


def parse_codex_tokens(raw_stdout: str) -> TokenUsage:
    """Parse token usage from Codex JSONL output."""
    usage_snapshots: list[tuple[str, dict[str, int]]] = []
    malformed_usages: list[str] = []
    for line in raw_stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type", ""))
        for usage in _find_usage_dicts(event):
            normalized, error = _normalize_usage_snapshot(usage)
            if error:
                malformed_usages.append(error)
                continue
            assert normalized is not None
            usage_snapshots.append((event_type, normalized))

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
        raw=raw_usage,
    )


def _detect_codex_model() -> str:
    """Read Codex model from config (not available in JSONL output)."""
    import tomllib
    config_path = Path.home() / ".codex" / "config.toml"
    try:
        if config_path.exists():
            with open(config_path, "rb") as f:
                codex_cfg = tomllib.load(f)
            return codex_cfg.get("model", "unknown")
    except (tomllib.TOMLDecodeError, PermissionError, OSError):
        pass
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
                    billable=0, raw=maybe_error,
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
        return raw_stdout, invalid_token_usage(
            "response JSON parse failed",
            raw={"raw_stdout": raw_stdout[:200]},
        ), "unknown", ExecutionMetrics(
            latency_ms=latency_ms,
            step_count=1,
            tool_call_count=0,
            tool_calls_by_type={},
        )

    if "error" in data:
        return f"[ERROR] {data['error']}", TokenUsage(
            input=0, input_cached=0, output=0, thoughts=0,
            billable=0, raw=data,
        ), "unknown", ExecutionMetrics(
            latency_ms=latency_ms,
            step_count=1,
            tool_call_count=0,
            tool_calls_by_type={},
        )

    if llm == "claude":
        tokens = parse_claude_tokens(data)
        text = data.get("result", "")
        # Model from modelUsage: pick the model with the most output tokens
        # (the CLI uses haiku for routing and the requested model for the response)
        model_usage = data.get("modelUsage", {})
        if model_usage:
            model = max(model_usage, key=lambda m: model_usage[m].get("outputTokens", 0))
        else:
            model = "unknown"
        return text, tokens, model, parse_claude_execution(data, latency_ms)

    if llm == "gemini":
        tokens = parse_gemini_tokens(data)
        text = data.get("response", "")
        # Model from stats.models: pick the model with the most output tokens
        stats = data.get("stats", {})
        models = stats.get("models", {})
        if models:
            def _gemini_output(m: str) -> int:
                t = models[m].get("tokens", {}) if isinstance(models[m], dict) else {}
                return t.get("candidates", 0) + t.get("output_tokens", 0) + t.get("output", 0)
            model = max(models, key=_gemini_output)
        else:
            model = "unknown"
        return text, tokens, model, parse_gemini_execution(data, latency_ms)

    return raw_stdout, invalid_token_usage(
        "unknown llm parser",
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
    if "cached_input_tokens" in raw_usage:
        input_tokens, input_error = coerce_token_int(raw_usage.get("input_tokens", 0), "input_tokens")
        cached_tokens, cached_error = coerce_token_int(
            raw_usage.get("cached_input_tokens", 0),
            "cached_input_tokens",
        )
        if input_error or cached_error:
            return 0
        assert input_tokens is not None
        assert cached_tokens is not None
        return max(
            input_tokens - cached_tokens,
            0,
        )
    if (
        "cache_creation_input_tokens" in raw_usage
        or "cache_read_input_tokens" in raw_usage
    ):
        input_tokens, input_error = coerce_token_int(raw_usage.get("input_tokens", 0), "input_tokens")
        cache_creation, creation_error = coerce_token_int(
            raw_usage.get("cache_creation_input_tokens", 0),
            "cache_creation_input_tokens",
        )
        cache_read, read_error = coerce_token_int(
            raw_usage.get("cache_read_input_tokens", 0),
            "cache_read_input_tokens",
        )
        if input_error or creation_error or read_error:
            return 0
        assert input_tokens is not None
        assert cache_creation is not None
        assert cache_read is not None
        return (
            input_tokens
            + cache_creation
            + cache_read
        )
    if "input_tokens" in raw_usage:
        input_tokens, input_error = coerce_token_int(raw_usage.get("input_tokens", 0), "input_tokens")
        if input_error:
            return 0
        assert input_tokens is not None
        return input_tokens
    if "prompt" in raw_usage:
        prompt_tokens, prompt_error = coerce_token_int(raw_usage.get("prompt", 0), "prompt")
        cached_tokens, cached_error = coerce_token_int(raw_usage.get("cached", 0), "cached")
        if prompt_error or cached_error:
            return 0
        assert prompt_tokens is not None
        assert cached_tokens is not None
        return max(prompt_tokens - cached_tokens, 0)
    return 0


def raw_usage_output_tokens(raw_usage: dict) -> int:
    """Extract provider-native output tokens from a raw usage payload."""
    if not raw_usage:
        return 0
    if isinstance(raw_usage.get("turns"), list):
        return sum(raw_usage_output_tokens(turn) for turn in raw_usage["turns"])
    if "output_tokens" in raw_usage:
        output_tokens, output_error = coerce_token_int(raw_usage.get("output_tokens", 0), "output_tokens")
        if output_error:
            return 0
        assert output_tokens is not None
        return output_tokens
    if "candidates" in raw_usage:
        candidate_tokens, candidate_error = coerce_token_int(raw_usage.get("candidates", 0), "candidates")
        if candidate_error:
            return 0
        assert candidate_tokens is not None
        return candidate_tokens
    return 0


def _allocate_segment_billable_input(
    total_billable_input: int,
    segments: list[tuple[str, str]],
) -> dict[str, int]:
    allocations = {name: 0 for name, _ in segments}
    if total_billable_input <= 0:
        return allocations

    weighted_segments = [
        (name, len(text))
        for name, text in segments
        if text
    ]
    total_weight = sum(weight for _, weight in weighted_segments)
    if total_weight <= 0:
        return allocations

    fractional_allocations: list[tuple[float, int, str]] = []
    allocated = 0
    for idx, (name, weight) in enumerate(weighted_segments):
        exact_share = total_billable_input * weight / total_weight
        base_share = int(exact_share)
        allocations[name] = base_share
        allocated += base_share
        fractional_allocations.append((exact_share - base_share, idx, name))

    remainder = total_billable_input - allocated
    for _, _, name in sorted(fractional_allocations, reverse=True)[:remainder]:
        allocations[name] += 1
    return allocations


def estimate_tool_call_stub_output_tokens(
    *,
    run1_total_output_tokens: int,
    run1_response_text: str,
    tool_call: str,
) -> int:
    """Estimate the run1 output portion attributable to the tool-call stub."""
    if run1_total_output_tokens <= 0:
        return 0

    response = run1_response_text.strip()
    stub = tool_call.strip()
    if not response:
        return 0
    if response == stub:
        return run1_total_output_tokens

    if stub in response:
        other_output = response.replace(stub, "", 1)
        allocations = _allocate_segment_billable_input(
            run1_total_output_tokens,
            [
                ("tool_call_stub_output_tokens", stub),
                ("other_output_tokens", other_output),
            ],
        )
        return allocations.get("tool_call_stub_output_tokens", 0)

    # Conservative fallback when no literal stub is present in the response text.
    return min(
        run1_total_output_tokens,
        max(1, round(run1_total_output_tokens * len(stub) / max(len(response), 1))),
    )


def captured_tool_simulation_adjustment(
    *,
    total_billable: int,
    tool_call_output: int,
    run2_input_billable: int,
    prompt: str,
    tool_call: str,
    syntax: list[str],
) -> ToolSimulationAdjustment:
    assistant_stub = f"\n\nAssistant: {tool_call}\n\n"
    tool_result_context = f"TOOL_RESULT:\n{json.dumps(syntax)}\n"
    follow_up_instruction = "Now complete the task."
    allocations = _allocate_segment_billable_input(
        run2_input_billable,
        [
            ("prompt_replay_input_billable", prompt),
            ("replayed_tool_call_input_billable", assistant_stub),
            ("tool_result_input_billable", tool_result_context),
            ("follow_up_instruction_input_billable", follow_up_instruction),
        ],
    )
    replay_input_billable = (
        allocations["prompt_replay_input_billable"]
        + allocations["replayed_tool_call_input_billable"]
    )
    adjusted_billable = total_billable - replay_input_billable - tool_call_output
    integrity_violation = adjusted_billable < 0
    integrity_violation_amount = max(-adjusted_billable, 0)
    integrity_violation_reason = ""
    if integrity_violation:
        integrity_violation_reason = (
            "captured tool-simulation adjustment produced negative adjusted billable"
        )
    return ToolSimulationAdjustment(
        replay_input_billable=replay_input_billable,
        tool_call_output=tool_call_output,
        adjusted_billable=adjusted_billable,
        prompt_replay_input_billable=allocations["prompt_replay_input_billable"],
        replayed_tool_call_input_billable=allocations["replayed_tool_call_input_billable"],
        tool_result_input_billable=allocations["tool_result_input_billable"],
        follow_up_instruction_input_billable=allocations["follow_up_instruction_input_billable"],
        source="captured_estimate",
        integrity_violation=integrity_violation,
        integrity_violation_reason=integrity_violation_reason,
        integrity_violation_amount=integrity_violation_amount,
    )


def tool_simulation_adjustment(tokens: TokenUsage) -> ToolSimulationAdjustment:
    """Compute a simulation-adjusted billable total without mutating raw measurements."""
    raw = tokens.raw
    if not isinstance(raw, dict):
        return ToolSimulationAdjustment(adjusted_billable=tokens.billable)

    captured = raw.get("tool_simulation_adjustment")
    if isinstance(captured, dict):
        return ToolSimulationAdjustment(
            replay_input_billable=int(captured.get("replay_input_billable", 0)),
            tool_call_output=int(captured.get("tool_call_output", 0)),
            adjusted_billable=int(captured.get("adjusted_billable", tokens.billable)),
            prompt_replay_input_billable=int(captured.get("prompt_replay_input_billable", 0)),
            replayed_tool_call_input_billable=int(captured.get("replayed_tool_call_input_billable", 0)),
            tool_result_input_billable=int(captured.get("tool_result_input_billable", 0)),
            follow_up_instruction_input_billable=int(captured.get("follow_up_instruction_input_billable", 0)),
            source=str(captured.get("source", "captured_estimate")),
            integrity_violation=bool(captured.get("integrity_violation", False)),
            integrity_violation_reason=str(captured.get("integrity_violation_reason", "")),
            integrity_violation_amount=int(captured.get("integrity_violation_amount", 0)),
        )

    run1 = raw.get("run1")
    run2 = raw.get("run2")
    if not isinstance(run1, dict) or not isinstance(run2, dict):
        return ToolSimulationAdjustment(adjusted_billable=tokens.billable)

    replay_input_billable = raw_usage_input_billable_tokens(run2)
    tool_call_output = raw_usage_output_tokens(run1)
    adjusted_billable = tokens.billable - replay_input_billable - tool_call_output
    integrity_violation = adjusted_billable < 0
    return ToolSimulationAdjustment(
        replay_input_billable=replay_input_billable,
        tool_call_output=tool_call_output,
        adjusted_billable=adjusted_billable,
        source="legacy_derived",
        integrity_violation=integrity_violation,
        integrity_violation_reason=(
            "legacy raw-derived tool-simulation adjustment produced negative adjusted billable"
            if integrity_violation else ""
        ),
        integrity_violation_amount=max(-adjusted_billable, 0),
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
