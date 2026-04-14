from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum


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
    prompt_replay_input_billable: int = 0
    replayed_tool_call_input_billable: int = 0
    tool_result_input_billable: int = 0
    follow_up_instruction_input_billable: int = 0
    source: str = "none"
    integrity_violation: bool = False
    integrity_violation_reason: str = ""
    integrity_violation_amount: int = 0


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
    execution_record: ExecutionRecord | None  # Command Verification: populated when --execute is used
    cache_state: str             # "cold" or "warm"
    timestamp: str


@dataclass(frozen=True)
class CLIInvocation:
    stdout: str
    latency_ms: int


def result_is_error(result: QuestionResult) -> bool:
    return result.response.startswith("[ERROR]")


def result_is_usage_valid(result: QuestionResult) -> bool:
    return result.tokens.usage_valid and not result_is_error(result)


def result_is_report_visible(result: QuestionResult) -> bool:
    return not result_is_error(result)


def result_is_usage_invalid(result: QuestionResult) -> bool:
    return result_is_report_visible(result) and not result.tokens.usage_valid


def usage_valid_results(results: list[QuestionResult]) -> list[QuestionResult]:
    return [result for result in results if result_is_usage_valid(result)]


def report_visible_results(results: list[QuestionResult]) -> list[QuestionResult]:
    return [result for result in results if result_is_report_visible(result)]


def error_results(results: list[QuestionResult]) -> list[QuestionResult]:
    return [result for result in results if result_is_error(result)]


def usage_invalid_results(results: list[QuestionResult]) -> list[QuestionResult]:
    return [result for result in results if result_is_usage_invalid(result)]


def invalid_usage_reason_counts(results: list[QuestionResult]) -> Counter:
    return Counter(
        result.tokens.usage_invalid_reason or result.tokens.cost_source or "unknown"
        for result in usage_invalid_results(results)
    )


def first_result_model(results: list[QuestionResult]) -> str:
    if results:
        return results[0].model
    return "unknown"


def summary_error_entries(results: list[QuestionResult]) -> list[dict]:
    entries: list[dict] = []
    for result in results:
        if result_is_error(result):
            entries.append(
                {
                    "question_id": result.id,
                    "error": result.response.removeprefix("[ERROR] "),
                    "latency_ms": result.execution.latency_ms,
                    "kind": "provider_error",
                }
            )
        elif result_is_usage_invalid(result):
            entries.append(
                {
                    "question_id": result.id,
                    "error": result.tokens.usage_invalid_reason or "usage telemetry invalid",
                    "latency_ms": result.execution.latency_ms,
                    "kind": result.tokens.cost_source if result.tokens.cost_source == "parse_error" else "usage_invalid",
                }
            )
    return entries

