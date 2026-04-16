import json
import hashlib
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime

from benchmark_core import config
from benchmark_core import execution as execution_module
from benchmark_core import providers
from benchmark_core.models import (
    AccuracyGrade,
    ExecutionMetrics,
    ExecutionRecord,
    QuestionResult,
    ResponseAnalysis,
    TokenUsage,
    error_results,
    first_result_model,
    report_visible_results,
    result_is_report_visible,
    result_is_usage_valid,
    usage_invalid_results,
)


def result_path(provider: str, q_id: str, run_k: int):
    return config.RESULTS_DIR / provider / f"{q_id}_run{run_k}.json"


def already_completed(provider: str, q_id: str, run_k: int) -> bool:
    return result_path(provider, q_id, run_k).exists()


def write_incremental(result: QuestionResult) -> None:
    path = result_path(result.llm, result.id, result.run_k)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2, default=str))


def _planned_question_runs(
    questions: list[dict],
    *,
    k: int,
    seed: int,
) -> list[tuple[dict, int]]:
    planned: list[tuple[dict, int]] = []
    for run_idx in range(k):
        for question in providers.shuffled_questions_for_run(questions, run_idx=run_idx, seed=seed):
            planned.append((question, run_idx))
    return planned


def _requested_model_for_llm(
    llm: str,
    *,
    claude_model: str | None = None,
    codex_model: str | None = None,
) -> str:
    if llm == "claude":
        return claude_model or ""
    if llm == "codex":
        return codex_model or ""
    return ""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(payload: object) -> str:
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def _build_effective_prompt(
    question: dict,
    *,
    inject_posix: bool,
    load_posix_core_fn=providers._load_posix_core,
    log_missing: bool = False,
) -> str:
    prompt = question["question"]
    if not inject_posix:
        return prompt

    core_md = load_posix_core_fn()
    if core_md is None:
        if log_missing:
            print(f"  [{question['id']}] Skipping POSIX injection — posix-core.md not available")
        return prompt

    return (
        f"{core_md}\n\n"
        "TOOL INSTRUCTION: You must use the get_posix_syntax tool for any non-trivial command. "
        "Output exactly: TOOL_CALL: get_posix_syntax(command) and stop. Do not guess syntax.\n\n"
        f"TASK:\n{prompt}"
    )


def _result_provenance(question: dict, *, prompt: str) -> dict[str, object]:
    question_snapshot = dict(question)
    return {
        "question_snapshot": question_snapshot,
        "question_sha256": _sha256_json(question_snapshot),
        "benchmark_data_sha256": config.sha256_file(config.DATA_FILE) or "",
        "effective_prompt_sha256": _sha256_text(prompt),
        "prompt_template_version": config.PROMPT_TEMPLATE_VERSION,
    }


def _build_error_result(
    *,
    llm: str,
    question: dict,
    run_k: int,
    message: str,
    error_kind: str,
    latency_ms: int = 0,
    claude_model: str | None = None,
    codex_model: str | None = None,
    cache_state: str = "cold",
    result_provenance: dict[str, object] | None = None,
) -> QuestionResult:
    minimal_answer = str(
        question.get("minimal_answer")
        or question.get("expected_answer")
        or question.get("expected")
        or ""
    )
    provenance = result_provenance or _result_provenance(
        question,
        prompt=_build_effective_prompt(question, inject_posix=False),
    )
    return QuestionResult(
        id=question["id"],
        llm=llm,
        model="unknown",
        requested_model=_requested_model_for_llm(
            llm,
            claude_model=claude_model,
            codex_model=codex_model,
        ),
        run_k=run_k,
        question=question["question"],
        response=f"[ERROR] {message}",
        tokens=TokenUsage(
            input=0,
            input_cached=0,
            output=0,
            thoughts=0,
            billable=0,
            raw={
                "error_row": True,
                "error_kind": error_kind,
                "error_message": message,
            },
        ),
        execution=ExecutionMetrics(
            latency_ms=max(latency_ms, 0),
            step_count=0,
            tool_call_count=0,
            tool_calls_by_type={},
        ),
        analysis=ResponseAnalysis(
            minimal_answer=minimal_answer,
            minimal_word_count=providers.count_words(minimal_answer) if minimal_answer else 0,
            minimal_shell_token_count=providers.count_shell_tokens(minimal_answer) if minimal_answer else 0,
            response_word_count=0,
            minimal_answer_gap_words=0,
            verbosity_ratio=0.0,
            posix_compliant=False,
            issue8_refusal=False,
            inefficiency_mode="provider_error",
            estimated_excess_output_tokens=0,
        ),
        accuracy=None,
        execution_record=None,
        cache_state=cache_state,
        timestamp=datetime.now().isoformat(),
        question_snapshot=provenance["question_snapshot"],
        question_sha256=str(provenance["question_sha256"]),
        benchmark_data_sha256=str(provenance["benchmark_data_sha256"]),
        effective_prompt_sha256=str(provenance["effective_prompt_sha256"]),
        prompt_template_version=str(provenance["prompt_template_version"]),
    )


def load_existing_result(
    provider: str,
    question: dict,
    run_k: int,
    *,
    expected_provenance: dict[str, object] | None = None,
) -> QuestionResult | None:
    q_id = question["id"]
    path = result_path(provider, q_id, run_k)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if expected_provenance is not None:
            for field in config.CACHE_PROVENANCE_FIELDS:
                if data.get(field) != expected_provenance.get(field):
                    return None
        # Strip removed cost fields from old result files
        tokens_data = dict(data["tokens"])
        tokens_data.pop("cost_usd", None)
        tokens_data.pop("cost_source", None)
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
        analysis = providers.analyze_response(
            question=question,
            response=data["response"],
            tokens=TokenUsage(**tokens_data),
            llm=data["llm"],
            execution=execution,
        )
        if analysis_data:
            from benchmark_core.models import ResponseAnalysis
            analysis = ResponseAnalysis(**analysis_data)
        exec_rec_data = data.get("execution_record")
        exec_rec = ExecutionRecord(**exec_rec_data) if exec_rec_data else None
        return QuestionResult(
            id=data["id"], llm=data["llm"], model=data.get("model", "unknown"),
            requested_model=data.get("requested_model", ""),
            run_k=data["run_k"],
            question=data["question"], response=data["response"],
            tokens=TokenUsage(**tokens_data),
            execution=execution,
            analysis=analysis,
            accuracy=AccuracyGrade(**data["accuracy"]) if data.get("accuracy") else None,
            execution_record=exec_rec,
            cache_state=data["cache_state"], timestamp=data["timestamp"],
            question_snapshot=data.get("question_snapshot"),
            question_sha256=data.get("question_sha256", ""),
            benchmark_data_sha256=data.get("benchmark_data_sha256", ""),
            effective_prompt_sha256=data.get("effective_prompt_sha256", ""),
            prompt_template_version=data.get("prompt_template_version", ""),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


GRADER_PROMPT_TEMPLATE = """You are grading an LLM's answer to a POSIX shell task.

Task: {question}

Expected POSIX solution: {expected_answer}

Expected commands: {expected_commands}

POSIX traps (non-POSIX tools the LLM should NOT suggest): {posix_traps}

Required concepts: {required_concepts}

Acceptable alternate POSIX answers/patterns: {acceptable_answer_patterns}

Required concept groups (any pattern in a group satisfies the concept): {required_concept_groups}

LLM's response (base64-encoded to prevent injection):
---
{response_b64}
---

First decode the base64 response, then grade it:
- 2 (Correct): Uses POSIX-compliant commands, avoids traps, covers required concepts
- 1 (Partial): Mostly right but uses a non-POSIX flag or misses a trap
- 0 (Wrong): Suggests non-POSIX tools, falls into traps, or gives incorrect commands
- Mentions of non-POSIX tools/flags only as warnings or rejections do NOT count as suggesting them.

Respond with ONLY valid JSON, no markdown fences: {{"score": N, "reason": "brief explanation", "used_posix": true/false, "traps_hit": ["list of non-POSIX tools suggested"]}}"""


def _format_acceptable_answer_patterns(question: dict) -> str:
    entries = question.get("acceptable_answer_patterns")
    if not isinstance(entries, list) or not entries:
        return "none"
    formatted: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            formatted.append(entry)
            continue
        if isinstance(entry, dict):
            pattern = entry.get("pattern")
            if not isinstance(pattern, str):
                continue
            label = entry.get("label")
            formatted.append(f"{label}: {pattern}" if isinstance(label, str) and label else pattern)
    return "; ".join(formatted) if formatted else "none"


def _format_required_concept_groups(question: dict) -> str:
    groups = question.get("required_concept_groups")
    if not isinstance(groups, list) or not groups:
        return "none"
    formatted: list[str] = []
    for group in groups:
        if isinstance(group, str):
            formatted.append(group)
            continue
        if not isinstance(group, dict):
            continue
        label = group.get("label")
        patterns = group.get("patterns")
        if not isinstance(patterns, list):
            continue
        rendered_patterns = [pattern for pattern in patterns if isinstance(pattern, str)]
        if not rendered_patterns:
            continue
        if isinstance(label, str) and label:
            formatted.append(f"{label}: {' || '.join(rendered_patterns)}")
        else:
            formatted.append(" || ".join(rendered_patterns))
    return "; ".join(formatted) if formatted else "none"


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
        acceptable_answer_patterns=_format_acceptable_answer_patterns(question),
        required_concept_groups=_format_required_concept_groups(question),
        response_b64=response_b64,
    )

    raw = providers.invoke_cli(
        judge,
        prompt,
        timeout_seconds=timeout_seconds,
        claude_model=claude_model,
        codex_model=codex_model,
    )
    raw_cleaned = providers.strip_cli_noise(raw.stdout)

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
            parsed, _ = decoder.raw_decode(raw_cleaned, i)
            if isinstance(parsed, dict) and "score" in parsed:
                try:
                    score = max(0, min(2, int(parsed["score"])))
                except (ValueError, TypeError):
                    score = 0
                return AccuracyGrade(score=score, reason=str(parsed.get("reason", "")))
        except (json.JSONDecodeError, ValueError):
            continue

    return AccuracyGrade(score=-1, reason=f"Failed to parse grade: {raw_cleaned[:100]}")


def load_questions(question_ids: list[str] | None = None) -> list[dict]:
    """Load questions from the benchmark data file."""
    with open(config.DATA_FILE) as f:
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
        tldr = providers._load_posix_tldr()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return [f"Could not load {config.POSIX_TLDR_FILE.name}: {e}"]

    try:
        utilities = providers._load_posix_utilities()
    except (FileNotFoundError, OSError) as e:
        return [f"Could not load {config.POSIX_UTILITIES_FILE.name}: {e}"]

    core_text = providers._load_posix_core()
    if core_text is None:
        errors.append(f"Could not load {config.POSIX_CORE_FILE.name}.")
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

    # Only flag expected commands that are in the bridge scope (macOS-posix-utilities.txt).
    # Benchmark questions may test utilities excluded from the bridge (e.g. timeout
    # on macOS); those are not bridge gaps.
    bridged_expected = [cmd for cmd in expected_commands if cmd in utility_set]

    missing_expected_tldr = [cmd for cmd in bridged_expected if cmd not in tldr_keys]
    if missing_expected_tldr:
        errors.append(
            "Missing expected commands in "
            f"{config.POSIX_TLDR_FILE.name}: {preview(missing_expected_tldr)}"
        )

    missing_expected_core = [cmd for cmd in bridged_expected if not in_core(cmd)]
    if missing_expected_core:
        errors.append(
            "Missing expected commands in "
            f"{config.POSIX_CORE_FILE.name}: {preview(missing_expected_core)}"
        )

    empty_tldr_entries = sorted(
        str(name)
        for name, value in tldr.items()
        if not isinstance(value, list) or not any(isinstance(item, str) and item.strip() for item in value)
    )
    if empty_tldr_entries:
        errors.append(f"Empty or invalid entries in {config.POSIX_TLDR_FILE.name}: {preview(empty_tldr_entries)}")

    if require_full_coverage:
        missing_tldr_utility = [name for name in utilities if name not in tldr_keys]
        if missing_tldr_utility:
            errors.append(
                "Missing POSIX utilities in "
                f"{config.POSIX_TLDR_FILE.name}: {preview(missing_tldr_utility)}"
            )

        missing_core_utility = [name for name in utilities if not in_core(name)]
        if missing_core_utility:
            errors.append(
                "Missing POSIX utilities in "
                f"{config.POSIX_CORE_FILE.name}: {preview(missing_core_utility)}"
            )

        # SKILL.md coverage: every POSIX utility must appear in the skill file.
        # Bidirectional note: core/skill checks are presence-only (\b word boundary);
        # they can detect missing utilities but not extras. The unknown_tldr_entries
        # check below handles bidirectional enforcement for the structured TLDR data.
        try:
            skill_text = config.POSIX_SKILL_FILE.read_text()
        except (FileNotFoundError, OSError):
            errors.append(f"Could not load {config.POSIX_SKILL_FILE.name}.")
            skill_text = ""
        skill_lower = skill_text.lower()

        def in_skill(name: str) -> bool:
            return bool(re.search(rf"\b{re.escape(name)}\b", skill_lower))

        missing_skill_utility = [name for name in utilities if not in_skill(name)]
        if missing_skill_utility:
            errors.append(
                "Missing POSIX utilities in "
                f"{config.POSIX_SKILL_FILE.name}: {preview(missing_skill_utility)}"
            )

        unknown_tldr_entries = sorted(tldr_keys - utility_set)
        if unknown_tldr_entries:
            errors.append(
                "Unknown utility keys in "
                f"{config.POSIX_TLDR_FILE.name}: {preview(unknown_tldr_entries)}"
            )

    return errors


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
    *,
    invoke_cli_fn=providers.invoke_cli,
    parse_response_fn=providers.parse_response,
    load_posix_core_fn=providers._load_posix_core,
    load_posix_tldr_fn=providers._load_posix_tldr,
    normalize_utility_name_fn=providers.normalize_utility_name,
    estimate_tool_call_stub_output_tokens_fn=providers.estimate_tool_call_stub_output_tokens,
    captured_tool_simulation_adjustment_fn=providers.captured_tool_simulation_adjustment,
    raw_usage_input_billable_tokens_fn=providers.raw_usage_input_billable_tokens,
    analyze_response_fn=providers.analyze_response,
    already_completed_fn=already_completed,
    grade_response_fn=grade_response,
    execute_question_fn=execution_module.execute_question,
) -> QuestionResult:
    """Run a single question against a single LLM and return the result."""
    effective_delay = delay
    if llm == "gemini":
        effective_delay = max(delay, GEMINI_MIN_DELAY_SECONDS)
    if effective_delay > 0:
        with _provider_locks[llm]:
            time.sleep(effective_delay)

    q_id = question["id"]
    prompt = _build_effective_prompt(
        question,
        inject_posix=inject_posix,
        load_posix_core_fn=load_posix_core_fn,
        log_missing=True,
    )
    result_provenance = _result_provenance(question, prompt=prompt)

    # Detect cache state (first call to this provider = cold)
    cache_state = "warm" if already_completed_fn(llm, q_id, 0) else "unknown"

    invocation = invoke_cli_fn(
        llm,
        prompt,
        timeout_seconds=timeout_seconds,
        claude_model=claude_model,
        codex_model=codex_model,
    )
    response_text, tokens, model, execution = parse_response_fn(
        llm,
        invocation.stdout,
        invocation.latency_ms,
        codex_model=codex_model,
    )

    requested = claude_model if llm == "claude" else (codex_model if llm == "codex" else "")
    if requested and model != "unknown" and requested.lower() != model.lower():
        print(f"  [{q_id}] WARNING: requested model '{requested}' but detected '{model}'")

    # Determine cache state from actual token data
    if tokens.input_cached > 0:
        cache_state = "warm"
    else:
        cache_state = "cold"

    if inject_posix and "TOOL_CALL: get_posix_syntax(" in response_text:
        match = providers.TOOL_CALL_PATTERN.search(response_text)
        if match:
            cmd = normalize_utility_name_fn(match.group(1))
            if not cmd:
                match = None
        if match and cmd:
            try:
                tldr = load_posix_tldr_fn()
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
            run1_response_text = response_text
            follow_up = (
                f"{prompt}\n\nAssistant: {tool_call}\n\n"
                f"TOOL_RESULT:\n{json.dumps(syntax)}\nNow complete the task."
            )
            if effective_delay > 0:
                with _provider_locks[llm]:
                    time.sleep(effective_delay)
            inv2 = invoke_cli_fn(
                llm,
                follow_up,
                timeout_seconds=timeout_seconds,
                claude_model=claude_model,
                codex_model=codex_model,
            )
            resp2, tok2, _, exec2 = parse_response_fn(
                llm,
                inv2.stdout,
                inv2.latency_ms,
                codex_model=codex_model,
            )

            response_text = f"{tool_call}\n\n[TOOL RESULT]: {syntax}\n\n{resp2}"
            tool_call_stub_output = estimate_tool_call_stub_output_tokens_fn(
                run1_total_output_tokens=tokens.output,
                run1_response_text=run1_response_text,
                tool_call=tool_call,
            )
            simulation_adjustment = captured_tool_simulation_adjustment_fn(
                total_billable=tokens.billable + tok2.billable,
                tool_call_output=tool_call_stub_output,
                run2_input_billable=raw_usage_input_billable_tokens_fn(tok2.raw),
                prompt=prompt,
                tool_call=tool_call,
                syntax=syntax,
            )
            combined_usage_valid = tokens.usage_valid and tok2.usage_valid
            combined_invalid_reasons = [
                reason
                for reason in (tokens.usage_invalid_reason, tok2.usage_invalid_reason)
                if reason
            ]
            combined_invalid_reason = "; ".join(combined_invalid_reasons)

            # Keep the raw totals intact; adjusted reporting is derived later.
            tokens = TokenUsage(
                input=tokens.input + tok2.input,
                input_cached=tokens.input_cached + tok2.input_cached,
                output=tokens.output + tok2.output,
                thoughts=tokens.thoughts + tok2.thoughts,
                billable=tokens.billable + tok2.billable,
                raw={
                    "run1": tokens.raw,
                    "run2": tok2.raw,
                    "tool_simulation_adjustment": asdict(simulation_adjustment),
                },
                usage_valid=combined_usage_valid,
                usage_invalid_reason=combined_invalid_reason,
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

    analysis = analyze_response_fn(question, response_text, tokens, llm, execution)

    # Grade if judge is specified and question has expected answer
    accuracy = None
    if judge and ("expected_answer" in question or "expected" in question):
        accuracy = grade_response_fn(
            judge,
            question,
            response_text,
            timeout_seconds=timeout_seconds,
            claude_model=claude_model,
            codex_model=codex_model,
        )

    # Command Verification: execute the extracted command if --execute was passed
    exec_record = None
    if execute:
        exec_record = execute_question_fn(question, response_text)

    return QuestionResult(
        id=q_id,
        llm=llm,
        model=model,
        requested_model=requested or "",
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
        question_snapshot=result_provenance["question_snapshot"],
        question_sha256=str(result_provenance["question_sha256"]),
        benchmark_data_sha256=str(result_provenance["benchmark_data_sha256"]),
        effective_prompt_sha256=str(result_provenance["effective_prompt_sha256"]),
        prompt_template_version=str(result_provenance["prompt_template_version"]),
    )


PROVIDER_CONCURRENCY = {
    "claude": 1,
    "gemini": 1,
    "codex": 1,
}

GEMINI_MIN_DELAY_SECONDS = 30

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
    *,
    run_single_fn=run_single,
    already_completed_fn=already_completed,
    load_existing_result_fn=load_existing_result,
    write_incremental_fn=write_incremental,
) -> list[QuestionResult]:
    """Run all questions for a single provider with concurrency."""
    workers = max_workers or PROVIDER_CONCURRENCY.get(llm, 1)
    results: list[QuestionResult] = []
    tasks_to_run = []

    for q, run_idx in _planned_question_runs(questions, k=k, seed=seed):
        expected_provenance = _result_provenance(
            q,
            prompt=_build_effective_prompt(q, inject_posix=inject_posix),
        )
        if already_completed_fn(llm, q["id"], run_idx):
            existing = load_existing_result_fn(
                llm,
                q,
                run_idx,
                expected_provenance=expected_provenance,
            )
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
                run_single_fn,
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
            question = next(q for q, idx in tasks_to_run if q["id"] == q_id and idx == run_idx)
            try:
                result = future.result(timeout=120)
            except Exception as e:
                result = _build_error_result(
                    llm=llm,
                    question=question,
                    run_k=run_idx,
                    message=f"{type(e).__name__}: {e}",
                    error_kind="question_exception",
                    claude_model=claude_model,
                    codex_model=codex_model,
                    result_provenance=_result_provenance(
                        question,
                        prompt=_build_effective_prompt(question, inject_posix=inject_posix),
                    ),
                )

            results.append(result)
            try:
                write_incremental_fn(result)
            except Exception as e:
                print(f"  [{q_id}] run {run_idx} — WARNING: incremental write failed: {e}")

            # Status indicator
            if result_is_report_visible(result):
                acc = ""
                if result_is_usage_valid(result) and result.accuracy and result.accuracy.score >= 0:
                    sym = "✓" if result.accuracy.score == 2 else "△" if result.accuracy.score == 1 else "✗"
                    acc = f" {sym}{result.accuracy.score}/2"
                exec_info = ""
                if result.execution_record and not result.execution_record.exec_skipped:
                    sym = "✓" if result.execution_record.exec_success else "✗"
                    exec_info = f" exec:{sym}"
                usage_info = ""
                if not result.tokens.usage_valid:
                    usage_info = f" usage:INVALID({result.tokens.usage_invalid_reason})"
                print(
                    f"  [{q_id}] run {run_idx} — "
                    f"in:{result.tokens.input} out:{result.tokens.output} "
                    f"cached:{result.tokens.input_cached} "
                    f"thoughts:{result.tokens.thoughts} "
                    f"billable:{result.tokens.billable} "
                    f"lat:{result.execution.latency_ms}ms "
                    f"mode:{result.analysis.inefficiency_mode}"
                    f"{acc}{exec_info}{usage_info}"
                )
            else:
                print(f"  [{q_id}] run {run_idx} — {result.response[:60]}")

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
    *,
    run_provider_batch_fn=run_provider_batch,
) -> dict[str, list[QuestionResult]]:
    """Run the full benchmark across all providers."""
    total_calls = len(questions) * len(llms) * k

    mode_label = "Unaided"
    if inject_posix and execute:
        mode_label = "Bridge-Aided Verification"
    elif execute:
        mode_label = "Command Verification"
    elif inject_posix:
        mode_label = "Bridge-Aided"

    manifest = execution_module.load_fixture_manifest() if execute else {}
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
            ordered = providers.shuffled_questions_for_run(questions, run_idx=run_idx, seed=seed)
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
                run_provider_batch_fn,
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
                provider_results: list[QuestionResult] = []
                for question, run_idx in _planned_question_runs(questions, k=k, seed=seed):
                    existing = None
                    expected_provenance = _result_provenance(
                        question,
                        prompt=_build_effective_prompt(question, inject_posix=inject_posix),
                    )
                    if already_completed(llm, question["id"], run_idx):
                        existing = load_existing_result(
                        llm,
                        question,
                        run_idx,
                        expected_provenance=expected_provenance,
                        )
                    if existing:
                        provider_results.append(existing)
                        continue
                    error_result = _build_error_result(
                        llm=llm,
                        question=question,
                        run_k=run_idx,
                        message=f"provider batch failed: {type(e).__name__}: {e}",
                        error_kind="provider_batch_failure",
                        claude_model=claude_model,
                        codex_model=codex_model,
                        result_provenance=expected_provenance,
                    )
                    provider_results.append(error_result)
                    try:
                        write_incremental(error_result)
                    except Exception as write_error:
                        print(
                            f"  [{question['id']}] run {run_idx} — "
                            f"WARNING: incremental write failed: {write_error}"
                        )
                all_results[llm] = provider_results

    return all_results
