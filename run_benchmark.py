#!/usr/bin/env python3
"""POSIX Token Efficiency Benchmark v0.4

Compatibility facade for the benchmark_core package.
"""

from pathlib import Path

from benchmark_core import cli as cli_module
from benchmark_core import config
from benchmark_core import execution
from benchmark_core import providers
from benchmark_core import reporting
from benchmark_core import runner
from benchmark_core.models import (
    AccuracyGrade,
    CLIInvocation,
    CommandResult,
    ExecutionMetrics,
    ExecutionRecord,
    LLM,
    QuestionResult,
    ResponseAnalysis,
    TokenUsage,
    ToolSimulationAdjustment,
    error_results,
    first_result_model,
    invalid_usage_reason_counts,
    report_visible_results,
    result_is_error,
    result_is_report_visible,
    result_is_usage_invalid,
    result_is_usage_valid,
    summary_error_entries,
    usage_invalid_results,
    usage_valid_results,
)

# Public path/constants compatibility
SCRIPT_DIR = config.SCRIPT_DIR
DATA_FILE = config.DATA_FILE
POSIX_CORE_FILE = config.POSIX_CORE_FILE
POSIX_TLDR_FILE = config.POSIX_TLDR_FILE
POSIX_UTILITIES_FILE = config.POSIX_UTILITIES_FILE
FIXTURES_DIR = config.FIXTURES_DIR
RESULTS_DIR_BRIDGE_AIDED = config.RESULTS_DIR_BRIDGE_AIDED
RESULTS_DIR_EXECUTE = config.RESULTS_DIR_EXECUTE
RESULTS_DIR_BRIDGE_AIDED_EXECUTE = config.RESULTS_DIR_BRIDGE_AIDED_EXECUTE
RESULTS_DIR = config.RESULTS_DIR_BASE

# Public provider constants compatibility
DEFAULT_CLI_TIMEOUT_SECONDS = providers.DEFAULT_CLI_TIMEOUT_SECONDS
DEFAULT_SHUFFLE_SEED = providers.DEFAULT_SHUFFLE_SEED
MODEL_OVERRIDE_AUTO_VALUES = providers.MODEL_OVERRIDE_AUTO_VALUES
PINNED_CLAUDE_MODEL = providers.PINNED_CLAUDE_MODEL
PINNED_CODEX_MODEL = providers.PINNED_CODEX_MODEL
TOOL_CALL_PATTERN = providers.TOOL_CALL_PATTERN
UTILITY_NAME_PATTERN = providers.UTILITY_NAME_PATTERN
LLM_COMMANDS = providers.LLM_COMMANDS
NOISE_PREFIXES = providers.NOISE_PREFIXES
TRAP_PATTERNS_BY_ID = providers.TRAP_PATTERNS_BY_ID
ISSUE8_COMMANDS = providers.ISSUE8_COMMANDS


def _sync_results_dir_to_config() -> None:
    config.set_results_dir(Path(RESULTS_DIR))


# Provider/parsing compatibility exports
_load_posix_core = providers._load_posix_core
_load_posix_tldr = providers._load_posix_tldr
_load_posix_utilities = providers._load_posix_utilities
normalize_utility_name = providers.normalize_utility_name
normalize_model_override = providers.normalize_model_override
format_seconds_from_ms = providers.format_seconds_from_ms
prune_timestamped_artifacts = providers.prune_timestamped_artifacts
strip_cli_noise = providers.strip_cli_noise
count_words = providers.count_words
count_shell_tokens = providers.count_shell_tokens
flatten_numeric_metrics = providers.flatten_numeric_metrics
invoke_cli = providers.invoke_cli
parse_claude_tokens = providers.parse_claude_tokens
parse_gemini_tokens = providers.parse_gemini_tokens
invalid_token_usage = providers.invalid_token_usage
coerce_token_int = providers.coerce_token_int
parse_codex_tokens = providers.parse_codex_tokens
parse_codex_execution = providers.parse_codex_execution
parse_claude_execution = providers.parse_claude_execution
parse_gemini_execution = providers.parse_gemini_execution
parse_response = providers.parse_response
raw_usage_input_billable_tokens = providers.raw_usage_input_billable_tokens
raw_usage_output_tokens = providers.raw_usage_output_tokens
estimate_tool_call_stub_output_tokens = providers.estimate_tool_call_stub_output_tokens
captured_tool_simulation_adjustment = providers.captured_tool_simulation_adjustment
tool_simulation_adjustment = providers.tool_simulation_adjustment
shuffled_questions_for_run = providers.shuffled_questions_for_run
detect_issue8_refusal = providers.detect_issue8_refusal
analyze_response = providers.analyze_response

# Execution compatibility exports
COMMAND_TIMEOUT_SECONDS = execution.COMMAND_TIMEOUT_SECONDS
FIXTURE_MANIFEST = execution.FIXTURE_MANIFEST
load_fixture_manifest = execution.load_fixture_manifest
extract_command = execution.extract_command
setup_fixture = execution.setup_fixture
run_command = execution.run_command
validate_command_result = execution.validate_command_result
execute_question = execution.execute_question

# Runner compatibility exports
grade_response = runner.grade_response
load_questions = runner.load_questions
validate_posix_bridge = runner.validate_posix_bridge
PROVIDER_CONCURRENCY = runner.PROVIDER_CONCURRENCY


def result_path(provider: str, q_id: str, run_k: int):
    _sync_results_dir_to_config()
    return runner.result_path(provider, q_id, run_k)


def already_completed(provider: str, q_id: str, run_k: int) -> bool:
    _sync_results_dir_to_config()
    return runner.already_completed(provider, q_id, run_k)


def write_incremental(result: QuestionResult) -> None:
    _sync_results_dir_to_config()
    runner.write_incremental(result)


def load_existing_result(provider: str, question: dict, run_k: int):
    _sync_results_dir_to_config()
    return runner.load_existing_result(provider, question, run_k)


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
):
    _sync_results_dir_to_config()
    return runner.run_single(
        llm=llm,
        question=question,
        run_k=run_k,
        judge=judge,
        delay=delay,
        timeout_seconds=timeout_seconds,
        inject_posix=inject_posix,
        execute=execute,
        claude_model=claude_model,
        codex_model=codex_model,
        invoke_cli_fn=invoke_cli,
        parse_response_fn=parse_response,
        load_posix_core_fn=_load_posix_core,
        load_posix_tldr_fn=_load_posix_tldr,
        normalize_utility_name_fn=normalize_utility_name,
        estimate_tool_call_stub_output_tokens_fn=estimate_tool_call_stub_output_tokens,
        captured_tool_simulation_adjustment_fn=captured_tool_simulation_adjustment,
        raw_usage_input_billable_tokens_fn=raw_usage_input_billable_tokens,
        analyze_response_fn=analyze_response,
        already_completed_fn=already_completed,
        grade_response_fn=grade_response,
        execute_question_fn=execute_question,
    )


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
):
    _sync_results_dir_to_config()
    return runner.run_provider_batch(
        llm=llm,
        questions=questions,
        k=k,
        judge=judge,
        delay=delay,
        timeout_seconds=timeout_seconds,
        max_workers=max_workers,
        seed=seed,
        inject_posix=inject_posix,
        execute=execute,
        claude_model=claude_model,
        codex_model=codex_model,
        run_single_fn=run_single,
        already_completed_fn=already_completed,
        load_existing_result_fn=load_existing_result,
        write_incremental_fn=write_incremental,
    )


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
):
    _sync_results_dir_to_config()
    return runner.run_benchmark(
        llms=llms,
        questions=questions,
        k=k,
        judge=judge,
        delay=delay,
        timeout_seconds=timeout_seconds,
        max_workers=max_workers,
        dry_run=dry_run,
        seed=seed,
        inject_posix=inject_posix,
        execute=execute,
        claude_model=claude_model,
        codex_model=codex_model,
        run_provider_batch_fn=run_provider_batch,
    )


def generate_report(all_results: dict[str, list[QuestionResult]], questions: list[dict]) -> None:
    reporting.generate_report(all_results, questions)


def save_summary(
    all_results: dict[str, list[QuestionResult]],
    *,
    requested_models: dict[str, str | None] | None = None,
    retain_latest_only: bool = False,
):
    _sync_results_dir_to_config()
    return reporting.save_summary(
        all_results,
        requested_models=requested_models,
        retain_latest_only=retain_latest_only,
    )


def save_visual_report(
    all_results: dict[str, list[QuestionResult]],
    questions: list[dict],
    *,
    retain_latest_only: bool = False,
):
    _sync_results_dir_to_config()
    return reporting.save_visual_report(
        all_results,
        questions,
        retain_latest_only=retain_latest_only,
    )


def save_comparison_report(named_summaries: list[tuple[str, dict]]):
    _sync_results_dir_to_config()
    return reporting.save_comparison_report(named_summaries)


def main():
    _sync_results_dir_to_config()
    cli_module.main()


if __name__ == "__main__":
    main()

