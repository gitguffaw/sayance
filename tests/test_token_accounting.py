import contextlib
import json
import io
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import run_benchmark as benchmark
from benchmark_core.models import (
    dropped_results_count,
    planned_posix_compliance_rate,
    planned_results_count,
    provider_error_results_count,
)
from run_benchmark import (
    ExecutionMetrics,
    QuestionResult,
    ResponseAnalysis,
    TokenUsage,
    captured_tool_simulation_adjustment,
    parse_claude_tokens,
    parse_codex_tokens,
    parse_gemini_execution,
    parse_gemini_tokens,
    raw_usage_input_billable_tokens,
    save_summary,
    save_visual_report,
    tool_simulation_adjustment,
)


def jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(event) for event in events)


def make_result(
    q_id: str,
    *,
    response: str,
    tokens: TokenUsage,
    latency_ms: int,
    posix_compliant: bool = False,
    issue8_refusal: bool = False,
    inefficiency_mode: str = "minimal_or_near_minimal",
) -> QuestionResult:
    return QuestionResult(
        id=q_id,
        llm="claude",
        model="claude-opus-4-6",
        requested_model="claude-opus-4-6",
        run_k=0,
        question=f"Question {q_id}",
        response=response,
        tokens=tokens,
        execution=ExecutionMetrics(
            latency_ms=latency_ms,
            step_count=1,
            tool_call_count=0,
            tool_calls_by_type={},
        ),
        analysis=ResponseAnalysis(
            minimal_answer="od file",
            minimal_word_count=2,
            minimal_shell_token_count=2,
            response_word_count=max(len(response.split()), 1),
            minimal_answer_gap_words=0,
            verbosity_ratio=1.0,
            posix_compliant=posix_compliant,
            issue8_refusal=issue8_refusal,
            inefficiency_mode=inefficiency_mode,
            estimated_excess_output_tokens=1,
        ),
        accuracy=None,
        execution_record=None,
        cache_state="cold",
        timestamp="20260403-000000",
    )


class CodexTokenParsingTests(unittest.TestCase):
    def test_parse_codex_tokens_accepts_top_level_usage(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 120,
                        "cached_input_tokens": 20,
                        "output_tokens": 12,
                    },
                }
            )
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 120)
        self.assertEqual(tokens.input_cached, 20)
        self.assertEqual(tokens.output, 12)
        self.assertEqual(tokens.billable, 112)

    def test_parse_codex_tokens_accepts_nested_usage(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "turn.completed",
                    "result": {
                        "usage": {
                            "input_tokens": "42",
                            "cached_input_tokens": "2",
                            "output_tokens": "7",
                        }
                    },
                }
            )
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 42)
        self.assertEqual(tokens.input_cached, 2)
        self.assertEqual(tokens.output, 7)
        self.assertEqual(tokens.billable, 47)

    def test_parse_codex_tokens_marks_malformed_usage_invalid(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": "nope",
                        "cached_input_tokens": 4,
                        "output_tokens": 9,
                    },
                }
            )
        )

        self.assertFalse(tokens.usage_valid)
        self.assertIn("input_tokens", tokens.usage_invalid_reason)

    def test_parse_codex_tokens_marks_missing_usage_invalid(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {"type": "turn.started", "item": {"type": "message"}},
                {"type": "item.completed", "item": {"text": "answer"}},
            )
        )

        self.assertFalse(tokens.usage_valid)
        self.assertEqual(tokens.usage_invalid_reason, "missing Codex usage telemetry")

    def test_parse_codex_tokens_uses_largest_snapshot_not_sum(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 10,
                        "output_tokens": 20,
                    },
                },
                {
                    "type": "usage.reported",
                    "result": {
                        "usage": {
                            "input_tokens": 120,
                            "cached_input_tokens": 15,
                            "output_tokens": 25,
                        }
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 120,
                        "cached_input_tokens": 15,
                        "output_tokens": 25,
                    },
                },
            )
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 120)
        self.assertEqual(tokens.input_cached, 15)
        self.assertEqual(tokens.output, 25)
        self.assertEqual(tokens.billable, 130)
        self.assertIn("usage_snapshots", tokens.raw)
        self.assertEqual(len(tokens.raw["usage_snapshots"]), 2)

    def test_parse_codex_tokens_handles_out_of_order_duplicate_cumulative(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 120,
                        "cached_input_tokens": 15,
                        "output_tokens": 25,
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 10,
                        "output_tokens": 20,
                    },
                },
                {
                    "type": "usage.reported",
                    "result": {
                        "usage": {
                            "input_tokens": 120,
                            "cached_input_tokens": 15,
                            "output_tokens": 25,
                        }
                    },
                },
            )
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 120)
        self.assertEqual(tokens.input_cached, 15)
        self.assertEqual(tokens.output, 25)
        self.assertEqual(tokens.billable, 130)
        self.assertIn("usage_snapshots", tokens.raw)
        self.assertEqual(len(tokens.raw["usage_snapshots"]), 2)

    def test_parse_codex_tokens_uses_largest_snapshot_for_mixed_event_cumulative_usage(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "usage.reported",
                    "result": {
                        "usage": {
                            "input_tokens": 120,
                            "cached_input_tokens": 15,
                            "output_tokens": 25,
                        }
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 10,
                        "output_tokens": 20,
                    },
                },
            )
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 120)
        self.assertEqual(tokens.input_cached, 15)
        self.assertEqual(tokens.output, 25)
        self.assertEqual(tokens.billable, 130)
        self.assertIn("usage_snapshots", tokens.raw)
        self.assertEqual(len(tokens.raw["usage_snapshots"]), 2)

    def test_parse_codex_tokens_sums_independent_snapshots(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 40,
                        "cached_input_tokens": 5,
                        "output_tokens": 10,
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 20,
                        "cached_input_tokens": 0,
                        "output_tokens": 4,
                    },
                },
            )
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 60)
        self.assertEqual(tokens.input_cached, 5)
        self.assertEqual(tokens.output, 14)
        self.assertEqual(tokens.billable, 69)
        self.assertIn("usage_snapshots", tokens.raw)
        self.assertEqual(len(tokens.raw["usage_snapshots"]), 2)

    def test_parse_codex_tokens_sums_duplicate_independent_turn_completed_snapshots(self) -> None:
        tokens = parse_codex_tokens(
            jsonl(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 1,
                        "output_tokens": 2,
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 10,
                        "cached_input_tokens": 1,
                        "output_tokens": 2,
                    },
                },
            )
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 20)
        self.assertEqual(tokens.input_cached, 2)
        self.assertEqual(tokens.output, 4)
        self.assertEqual(tokens.billable, 22)
        self.assertIn("usage_snapshots", tokens.raw)
        self.assertEqual(len(tokens.raw["usage_snapshots"]), 2)


class GeminiTokenParsingTests(unittest.TestCase):
    def test_parse_gemini_tokens_aggregates_multiple_models(self) -> None:
        tokens = parse_gemini_tokens(
            {
                "stats": {
                    "models": {
                        "gemini-a": {
                            "tokens": {
                                "input": 10,
                                "prompt": 12,
                                "candidates": 4,
                                "cached": 2,
                                "thoughts": 1,
                            }
                        },
                        "gemini-b": {
                            "tokens": {
                                "input": 20,
                                "prompt": 25,
                                "candidates": 5,
                                "cached": 3,
                                "thoughts": 2,
                            }
                        },
                    }
                }
            }
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 30)
        self.assertEqual(tokens.input_cached, 5)
        self.assertEqual(tokens.output, 9)
        self.assertEqual(tokens.thoughts, 3)
        self.assertEqual(tokens.billable, 41)
        self.assertIn("models", tokens.raw)

    def test_parse_gemini_tokens_supports_key_aliases(self) -> None:
        tokens = parse_gemini_tokens(
            {
                "stats": {
                    "models": {
                        "gemini-a": {
                            "tokens": {
                                "input_tokens": "8",
                                "prompt_tokens": "11",
                                "output_tokens": "3",
                                "cached_input_tokens": "2",
                                "reasoning_tokens": "4",
                            }
                        }
                    }
                }
            }
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 8)
        self.assertEqual(tokens.input_cached, 2)
        self.assertEqual(tokens.output, 3)
        self.assertEqual(tokens.thoughts, 4)
        self.assertEqual(tokens.billable, 12)

    def test_parse_gemini_tokens_marks_missing_prompt_invalid(self) -> None:
        tokens = parse_gemini_tokens(
            {
                "stats": {
                    "models": {
                        "gemini-a": {
                            "tokens": {
                                "input": 8,
                                "candidates": 3,
                                "cached": 2,
                            }
                        }
                    }
                }
            }
        )

        self.assertFalse(tokens.usage_valid)
        self.assertIn("prompt", tokens.usage_invalid_reason.lower())

    def test_parse_gemini_tokens_marks_negative_billable_invalid(self) -> None:
        tokens = parse_gemini_tokens(
            {
                "stats": {
                    "models": {
                        "gemini-a": {
                            "tokens": {
                                "input": 8,
                                "prompt": 2,
                                "candidates": 1,
                                "cached": 5,
                            }
                        }
                    }
                }
            }
        )

        self.assertFalse(tokens.usage_valid)
        self.assertIn("negative", tokens.usage_invalid_reason.lower())

    def test_parse_gemini_execution_counts_only_count_like_metrics(self) -> None:
        execution = parse_gemini_execution(
            {
                "stats": {
                    "tools": {
                        "shell": {
                            "call_count": 2,
                            "latency_ms": 120,
                            "token_estimate": 40,
                            "result_count": 99,
                        },
                        "search": {
                            "calls": 3.0,
                            "duration_ms": 80,
                            "token_count": 41,
                        },
                        "planner": {
                            "count": 1,
                            "avg_latency_ms": 15,
                        },
                    }
                }
            },
            latency_ms=250,
        )

        self.assertEqual(execution.tool_call_count, 6)
        self.assertEqual(
            execution.tool_calls_by_type,
            {
                "shell.call_count": 2,
                "search.calls": 3,
                "planner.count": 1,
            },
        )
        self.assertNotIn("shell.result_count", execution.tool_calls_by_type)
        self.assertNotIn("search.token_count", execution.tool_calls_by_type)


class ClaudeTokenParsingTests(unittest.TestCase):
    def test_parse_claude_tokens_uses_cache_read_for_input_cached(self) -> None:
        tokens = parse_claude_tokens(
            {
                "usage": {
                    "input_tokens": 100,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 7,
                    "output_tokens": 11,
                },
                "total_cost_usd": 0.12,
            }
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 100)
        self.assertEqual(tokens.input_cached, 7)
        self.assertEqual(tokens.billable, 148)

    def test_parse_claude_tokens_accepts_string_fields(self) -> None:
        tokens = parse_claude_tokens(
            {
                "usage": {
                    "input_tokens": "10",
                    "cache_creation_input_tokens": "2",
                    "cache_read_input_tokens": "3",
                    "output_tokens": "4",
                }
            }
        )

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 10)
        self.assertEqual(tokens.input_cached, 3)
        self.assertEqual(tokens.billable, 19)

    def test_parse_claude_tokens_treats_null_usage_as_zero_usage(self) -> None:
        tokens = parse_claude_tokens({"usage": None})

        self.assertTrue(tokens.usage_valid)
        self.assertEqual(tokens.input, 0)
        self.assertEqual(tokens.input_cached, 0)
        self.assertEqual(tokens.output, 0)
        self.assertEqual(tokens.billable, 0)

    def test_parse_claude_tokens_marks_invalid_field_types(self) -> None:
        tokens = parse_claude_tokens(
            {
                "usage": {
                    "input_tokens": [],
                    "output_tokens": 4,
                }
            }
        )

        self.assertFalse(tokens.usage_valid)
        self.assertIn("Claude input_tokens", tokens.usage_invalid_reason)

    def test_raw_usage_input_billable_tokens_handles_omitted_claude_cache_keys(self) -> None:
        self.assertEqual(
            raw_usage_input_billable_tokens({"input_tokens": 12}),
            12,
        )

    def test_raw_usage_input_billable_tokens_handles_cache_creation_without_read(self) -> None:
        self.assertEqual(
            raw_usage_input_billable_tokens(
                {
                    "input_tokens": 12,
                    "cache_creation_input_tokens": 5,
                }
            ),
            17,
        )

    def test_raw_usage_input_billable_tokens_preserves_cached_input_semantics(self) -> None:
        self.assertEqual(
            raw_usage_input_billable_tokens(
                {
                    "input_tokens": 10,
                    "cached_input_tokens": 4,
                }
            ),
            6,
        )


class ToolSimulationAdjustmentTests(unittest.TestCase):
    def test_tool_simulation_adjustment_uses_captured_components(self) -> None:
        tokens = TokenUsage(
            input=0,
            input_cached=0,
            output=0,
            thoughts=0,
            billable=70,
            raw={
                "tool_simulation_adjustment": {
                    "replay_input_billable": 20,
                    "tool_call_output": 6,
                    "adjusted_billable": 44,
                    "prompt_replay_input_billable": 14,
                    "replayed_tool_call_input_billable": 6,
                    "tool_result_input_billable": 8,
                    "follow_up_instruction_input_billable": 2,
                    "source": "captured_estimate",
                }
            },
        )

        adjustment = tool_simulation_adjustment(tokens)
        self.assertEqual(adjustment.replay_input_billable, 20)
        self.assertEqual(adjustment.tool_call_output, 6)
        self.assertEqual(adjustment.adjusted_billable, 44)
        self.assertEqual(adjustment.prompt_replay_input_billable, 14)
        self.assertEqual(adjustment.replayed_tool_call_input_billable, 6)
        self.assertEqual(adjustment.tool_result_input_billable, 8)
        self.assertEqual(adjustment.follow_up_instruction_input_billable, 2)
        self.assertEqual(adjustment.source, "captured_estimate")

    def test_tool_simulation_adjustment_flags_negative_integrity_violation(self) -> None:
        adjustment = captured_tool_simulation_adjustment(
            total_billable=10,
            tool_call_output=6,
            run2_input_billable=11,
            prompt="P" * 10,
            tool_call="sayance-lookup od",
            syntax=["od -An -tx1 file"],
        )

        self.assertTrue(adjustment.integrity_violation)
        self.assertLess(adjustment.adjusted_billable, 0)
        self.assertEqual(
            adjustment.integrity_violation_amount,
            -adjustment.adjusted_billable,
        )
        self.assertIn("negative adjusted billable", adjustment.integrity_violation_reason)

    def test_tool_simulation_adjustment_legacy_fallback_remains_compatible(self) -> None:
        tokens = TokenUsage(
            input=0,
            input_cached=0,
            output=0,
            thoughts=0,
            billable=30,
            raw={
                "run1": {"output_tokens": 4},
                "run2": {"prompt": 18, "cached": 2, "candidates": 6},
            },
        )

        adjustment = tool_simulation_adjustment(tokens)
        self.assertEqual(adjustment.replay_input_billable, 16)
        self.assertEqual(adjustment.tool_call_output, 4)
        self.assertEqual(adjustment.adjusted_billable, 10)
        self.assertEqual(adjustment.source, "legacy_derived")
        self.assertFalse(adjustment.integrity_violation)

    def test_captured_tool_simulation_adjustment_keeps_non_replay_context_separate(self) -> None:
        adjustment = captured_tool_simulation_adjustment(
            total_billable=80,
            tool_call_output=5,
            run2_input_billable=40,
            prompt="P" * 20,
            tool_call="sayance-lookup od",
            syntax=["od -An -tx1 file"],
        )

        self.assertEqual(
            adjustment.replay_input_billable,
            adjustment.prompt_replay_input_billable + adjustment.replayed_tool_call_input_billable,
        )
        self.assertEqual(
            adjustment.replay_input_billable
            + adjustment.tool_result_input_billable
            + adjustment.follow_up_instruction_input_billable,
            40,
        )
        self.assertEqual(adjustment.source, "captured_estimate")

    @mock.patch.object(benchmark, "already_completed", return_value=False)
    @mock.patch.object(benchmark, "_load_posix_core", return_value="POSIX CORE")
    @mock.patch.object(benchmark, "_load_posix_tldr", return_value={"od": ["od -An -tx1 file"]})
    @mock.patch.object(benchmark, "invoke_cli")
    @mock.patch.object(benchmark, "parse_response")
    def test_run_single_captures_stub_output_not_full_run1_output(
        self,
        parse_response_mock: mock.Mock,
        invoke_cli_mock: mock.Mock,
        _load_posix_tldr_mock: mock.Mock,
        _load_posix_core_mock: mock.Mock,
        _already_completed_mock: mock.Mock,
    ) -> None:
        invoke_cli_mock.side_effect = [
            benchmark.CLIInvocation(stdout="run1", latency_ms=10),
            benchmark.CLIInvocation(stdout="run2", latency_ms=20),
        ]
        run1_tokens = TokenUsage(
            input=20,
            input_cached=0,
            output=24,
            thoughts=0,
            billable=30,
            raw={"input_tokens": 20, "cached_input_tokens": 0, "output_tokens": 24},
        )
        run2_tokens = TokenUsage(
            input=12,
            input_cached=0,
            output=6,
            thoughts=0,
            billable=18,
            raw={"prompt": 12, "cached": 0, "candidates": 6},
        )
        parse_response_mock.side_effect = [
            (
                "sayance-lookup od\nHere is extra explanatory text.",
                run1_tokens,
                "claude-opus-4-6",
                ExecutionMetrics(latency_ms=10, step_count=1, tool_call_count=0, tool_calls_by_type={}),
            ),
            (
                "od -An -tx1 file",
                run2_tokens,
                "claude-opus-4-6",
                ExecutionMetrics(latency_ms=20, step_count=1, tool_call_count=0, tool_calls_by_type={}),
            ),
        ]

        question = {
            "id": "T10",
            "question": "Hex dump this file",
            "expected_commands": ["od"],
            "required_concepts": [],
            "minimal_answer": "od -An -tx1 file",
            "tier": 2,
        }
        result = benchmark.run_single(
            "claude",
            question,
            run_k=0,
            judge=None,
            delay=0.0,
            timeout_seconds=120,
            inject_posix=True,
            execute=False,
        )
        adjustment = result.tokens.raw.get("tool_simulation_adjustment", {})
        self.assertTrue(adjustment)
        self.assertGreater(adjustment["tool_call_output"], 0)
        self.assertLess(adjustment["tool_call_output"], run1_tokens.output)


class ValidityReportingTests(unittest.TestCase):
    def test_save_summary_includes_tool_simulation_integrity_diagnostics(self) -> None:
        simulated = make_result(
            "T10",
            response="sayance-lookup od\n\n[TOOL RESULT]: ['od -An -tx1 file']\n\nod -An -tx1 file",
            tokens=TokenUsage(
                input=20,
                input_cached=0,
                output=8,
                thoughts=0,
                billable=10,
                raw={
                    "tool_simulation_adjustment": {
                        "replay_input_billable": 7,
                        "tool_call_output": 5,
                        "adjusted_billable": -2,
                        "prompt_replay_input_billable": 4,
                        "replayed_tool_call_input_billable": 3,
                        "tool_result_input_billable": 2,
                        "follow_up_instruction_input_billable": 1,
                        "source": "captured_estimate",
                        "integrity_violation": True,
                        "integrity_violation_reason": "captured tool-simulation adjustment produced negative adjusted billable",
                        "integrity_violation_amount": 2,
                    }
                },
            ),
            latency_ms=120,
            posix_compliant=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark.RESULTS_DIR
            benchmark.RESULTS_DIR = Path(tmpdir)
            try:
                summary_path = save_summary({"claude": [simulated]})
                payload = json.loads(summary_path.read_text())["llms"]["claude"]
            finally:
                benchmark.RESULTS_DIR = original_results_dir

        self.assertEqual(payload["total_simulation_adjusted_billable_tokens"], -2)
        self.assertEqual(payload["tool_simulation_adjustment_sources"], {"captured_estimate": 1})
        self.assertEqual(payload["tool_simulation_integrity_violation_count"], 1)
        self.assertEqual(payload["tool_simulation_integrity_violations"][0]["question_id"], "T10")
        self.assertEqual(payload["tool_simulation_integrity_violations"][0]["amount"], 2)

    def test_save_summary_uses_usage_valid_for_tokens_and_visible_for_latency(self) -> None:
        valid = make_result(
            "T01",
            response="od file",
            tokens=TokenUsage(
                input=10,
                input_cached=0,
                output=4,
                thoughts=0,
                billable=14,
                raw={},
            ),
            latency_ms=100,
            posix_compliant=True,
        )
        usage_invalid = make_result(
            "T02",
            response="fallback explanation",
            tokens=TokenUsage(
                input=0,
                input_cached=0,
                output=0,
                thoughts=0,
                billable=0,
                raw={},
                usage_valid=False,
                usage_invalid_reason="missing usage telemetry",
            ),
            latency_ms=300,
        )
        provider_error = make_result(
            "T03",
            response="[ERROR] timeout",
            tokens=TokenUsage(
                input=0,
                input_cached=0,
                output=0,
                thoughts=0,
                billable=0,
                raw={},
            ),
            latency_ms=500,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark.RESULTS_DIR
            benchmark.RESULTS_DIR = Path(tmpdir)
            try:
                summary_path = save_summary({"claude": [valid, usage_invalid, provider_error]})
                payload = json.loads(summary_path.read_text())["llms"]["claude"]
            finally:
                benchmark.RESULTS_DIR = original_results_dir

        self.assertEqual(payload["total_results"], 3)
        self.assertEqual(payload["valid_results"], 1)
        self.assertEqual(payload["usage_valid_results"], 1)
        self.assertEqual(payload["report_visible_results"], 2)
        self.assertEqual(payload["usage_invalid_results"], 1)
        self.assertEqual(payload["invalid_usage_reasons"], {"missing usage telemetry": 1})
        self.assertEqual(payload["total_billable_tokens"], 14)
        self.assertEqual(payload["total_output_tokens"], 4)
        self.assertEqual(payload["mean_output_tokens"], 4)
        self.assertEqual(payload["mean_latency_ms"], 200)
        self.assertEqual(
            {(entry["question_id"], entry["kind"]) for entry in payload["errors"]},
            {("T02", "usage_invalid"), ("T03", "provider_error")},
        )

    def test_save_visual_report_keeps_usage_invalid_non_error_results_visible(self) -> None:
        valid = make_result(
            "T01",
            response="od file",
            tokens=TokenUsage(
                input=10,
                input_cached=0,
                output=4,
                thoughts=0,
                billable=14,
                raw={},
            ),
            latency_ms=100,
            posix_compliant=True,
        )
        usage_invalid = make_result(
            "T02",
            response="fallback explanation",
            tokens=TokenUsage(
                input=0,
                input_cached=0,
                output=0,
                thoughts=0,
                billable=0,
                raw={},
                usage_valid=False,
                usage_invalid_reason="missing usage telemetry",
            ),
            latency_ms=300,
        )

        questions = [
            {"id": "T01", "tier": 1, "question": "Question T01", "expected_answer": "od file"},
            {"id": "T02", "tier": 2, "question": "Question T02", "expected_answer": "cksum file"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark.RESULTS_DIR
            benchmark.RESULTS_DIR = Path(tmpdir)
            try:
                report_path = save_visual_report({"claude": [valid, usage_invalid]}, questions)
                report_html = report_path.read_text()
            finally:
                benchmark.RESULTS_DIR = original_results_dir

        self.assertIn("2/2 tasks visible", report_html)
        self.assertIn("1 usage-valid", report_html)
        self.assertIn("Usage Invalid (1)", report_html)
        self.assertIn("missing usage telemetry", report_html)

    def test_save_summary_records_parse_error_entries(self) -> None:
        parse_invalid = make_result(
            "T09",
            response="non-json output",
            tokens=TokenUsage(
                input=0,
                input_cached=0,
                output=0,
                thoughts=0,
                billable=0,
                raw={},
                usage_valid=False,
                usage_invalid_reason="response JSON parse failed",
            ),
            latency_ms=220,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark.RESULTS_DIR
            benchmark.RESULTS_DIR = Path(tmpdir)
            try:
                summary_path = save_summary({"claude": [parse_invalid]})
                payload = json.loads(summary_path.read_text())["llms"]["claude"]
            finally:
                benchmark.RESULTS_DIR = original_results_dir

        self.assertEqual(payload["usage_invalid_results"], 1)
        self.assertEqual(payload["errors"][0]["kind"], "parse_error")
        self.assertEqual(payload["errors"][0]["error"], "response JSON parse failed")

    def test_generate_report_mentions_usage_invalid_results(self) -> None:
        valid = make_result(
            "T01",
            response="od file",
            tokens=TokenUsage(
                input=10,
                input_cached=0,
                output=4,
                thoughts=0,
                billable=14,
                raw={},
            ),
            latency_ms=100,
            posix_compliant=True,
        )
        usage_invalid = make_result(
            "T02",
            response="fallback explanation",
            tokens=TokenUsage(
                input=0,
                input_cached=0,
                output=0,
                thoughts=0,
                billable=0,
                raw={},
                usage_valid=False,
                usage_invalid_reason="missing usage telemetry",
            ),
            latency_ms=300,
        )

        questions = [
            {"id": "T01", "tier": 1, "question": "Question T01"},
            {"id": "T02", "tier": 2, "question": "Question T02"},
        ]

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            benchmark.generate_report({"claude": [valid, usage_invalid]}, questions)
        rendered = output.getvalue()

        self.assertIn("Usage invalid: 1/2", rendered)
        self.assertIn("Latency ms:     mean=200", rendered)

    def test_generate_report_mentions_tool_simulation_integrity_violations(self) -> None:
        simulated = make_result(
            "T10",
            response="sayance-lookup od\n\n[TOOL RESULT]: ['od -An -tx1 file']\n\nod -An -tx1 file",
            tokens=TokenUsage(
                input=20,
                input_cached=0,
                output=8,
                thoughts=0,
                billable=10,
                raw={
                    "tool_simulation_adjustment": {
                        "replay_input_billable": 7,
                        "tool_call_output": 5,
                        "adjusted_billable": -2,
                        "prompt_replay_input_billable": 4,
                        "replayed_tool_call_input_billable": 3,
                        "tool_result_input_billable": 2,
                        "follow_up_instruction_input_billable": 1,
                        "source": "captured_estimate",
                        "integrity_violation": True,
                        "integrity_violation_reason": "captured tool-simulation adjustment produced negative adjusted billable",
                        "integrity_violation_amount": 2,
                    }
                },
            ),
            latency_ms=120,
            posix_compliant=True,
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            benchmark.generate_report({"claude": [simulated]}, [{"id": "T10", "tier": 2, "question": "Question T10"}])
        rendered = output.getvalue()

        self.assertIn("Tool-sim integrity violations: 1", rendered)
        self.assertIn("Tool-sim adjustment sources: captured_estimate=1", rendered)


class ResultPreservationTests(unittest.TestCase):
    def test_run_provider_batch_emits_error_row_for_question_exception(self) -> None:
        questions = [
            {
                "id": "T01",
                "question": "Question T01",
                "expected_commands": ["od"],
                "required_concepts": [],
                "minimal_answer": "od file",
                "tier": 1,
            },
            {
                "id": "T02",
                "question": "Question T02",
                "expected_commands": ["cksum"],
                "required_concepts": [],
                "minimal_answer": "cksum file",
                "tier": 1,
            },
        ]
        written: list[QuestionResult] = []

        def fake_run_single(
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
            context_mode: str = benchmark.CONTEXT_MODE_AMBIENT,
        ) -> QuestionResult:
            del llm, judge, delay, timeout_seconds, inject_posix, execute, claude_model, codex_model, context_mode
            if question["id"] == "T02":
                raise RuntimeError("boom")
            return make_result(
                question["id"],
                response="od file",
                tokens=TokenUsage(
                    input=10,
                    input_cached=0,
                    output=3,
                    thoughts=0,
                    billable=13,
                    raw={},
                ),
                latency_ms=100,
                posix_compliant=True,
            )

        def fake_write_incremental(result: QuestionResult) -> None:
            written.append(result)

        results = benchmark.runner.run_provider_batch(
            llm="claude",
            questions=questions,
            k=1,
            judge=None,
            delay=0.0,
            timeout_seconds=30,
            max_workers=1,
            seed=123,
            run_single_fn=fake_run_single,
            already_completed_fn=lambda *_args, **_kwargs: False,
            load_existing_result_fn=lambda *_args, **_kwargs: None,
            write_incremental_fn=fake_write_incremental,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(len(written), 2)
        self.assertEqual({result.id for result in results}, {"T01", "T02"})
        error = next(result for result in results if result.id == "T02")
        self.assertTrue(error.response.startswith("[ERROR] RuntimeError: boom"))
        self.assertEqual(error.tokens.raw["error_kind"], "question_exception")
        self.assertEqual(error.execution.latency_ms, 0)
        self.assertEqual(error.analysis.inefficiency_mode, "provider_error")

    def test_run_benchmark_emits_provider_error_rows_instead_of_empty_bucket(self) -> None:
        questions = [
            {
                "id": "T01",
                "question": "Question T01",
                "expected_commands": ["od"],
                "required_concepts": [],
                "minimal_answer": "od file",
                "tier": 1,
            },
            {
                "id": "T02",
                "question": "Question T02",
                "expected_commands": ["cksum"],
                "required_concepts": [],
                "minimal_answer": "cksum file",
                "tier": 1,
            },
        ]

        def raising_batch(*_args, **_kwargs) -> list[QuestionResult]:
            raise RuntimeError("provider offline")

        with mock.patch.object(benchmark.runner, "already_completed", return_value=False), \
                mock.patch.object(benchmark.runner, "load_existing_result", return_value=None), \
                mock.patch.object(benchmark.runner, "write_incremental") as write_incremental_mock:
            results = benchmark.runner.run_benchmark(
                llms=["claude"],
                questions=questions,
                k=2,
                judge=None,
                delay=0.0,
                timeout_seconds=30,
                max_workers=1,
                dry_run=False,
                seed=123,
                inject_posix=False,
                execute=False,
                claude_model="claude-opus-4-6",
                run_provider_batch_fn=raising_batch,
            )

        self.assertIn("claude", results)
        self.assertEqual(len(results["claude"]), 4)
        self.assertTrue(all(result.response.startswith("[ERROR] provider batch failed: RuntimeError: provider offline") for result in results["claude"]))
        self.assertTrue(all(result.tokens.raw["error_kind"] == "provider_batch_failure" for result in results["claude"]))
        self.assertEqual({result.id for result in results["claude"]}, {"T01", "T02"})
        self.assertEqual({result.run_k for result in results["claude"]}, {0, 1})
        self.assertEqual(write_incremental_mock.call_count, 4)

    def test_planned_result_helpers_support_denominator_metrics(self) -> None:
        valid = make_result(
            "T01",
            response="od file",
            tokens=TokenUsage(
                input=10,
                input_cached=0,
                output=4,
                thoughts=0,
                billable=14,
                raw={},
            ),
            latency_ms=100,
            posix_compliant=True,
        )
        provider_error = make_result(
            "T02",
            response="[ERROR] timeout",
            tokens=TokenUsage(
                input=0,
                input_cached=0,
                output=0,
                thoughts=0,
                billable=0,
                raw={"error_kind": "provider_batch_failure"},
            ),
            latency_ms=500,
        )
        results = [valid, provider_error]

        self.assertEqual(planned_results_count(results, planned_total=3), 3)
        self.assertEqual(provider_error_results_count(results), 1)
        self.assertEqual(dropped_results_count(results, planned_total=3), 1)
        self.assertAlmostEqual(planned_posix_compliance_rate(results, planned_total=3), 1 / 3)

    def test_load_existing_result_rejects_missing_or_mismatched_provenance(self) -> None:
        question = {
            "id": "T29",
            "question": "Portable arithmetic",
            "expected_commands": ["expr"],
            "required_concepts": ["expr or $(())"],
            "minimal_answer": "expr '(' 3 + 5 ')' '*' 2",
            "acceptable_answer_patterns": [{"label": "$(( ))", "pattern": r"\$\(\("}],
            "required_concept_groups": [{"label": "expr or $(())", "patterns": [r"\bexpr\b", r"\$\(\("]}],
            "tier": 1,
        }
        prompt = benchmark.runner._build_effective_prompt(question, llm="claude", inject_posix=False)
        expected_provenance = benchmark.runner._result_provenance(question, prompt=prompt)

        result = make_result(
            "T29",
            response="$(( (3 + 5) * 2 ))",
            tokens=TokenUsage(
                input=10,
                input_cached=0,
                output=4,
                thoughts=0,
                billable=14,
                raw={},
            ),
            latency_ms=100,
            posix_compliant=True,
        )
        payload = asdict(result)
        payload.update(expected_provenance)

        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark.config.RESULTS_DIR
            benchmark.config.set_results_dir(Path(tmpdir))
            try:
                path = benchmark.runner.result_path("claude", "T29", 0)
                path.parent.mkdir(parents=True, exist_ok=True)

                path.write_text(json.dumps(payload, indent=2))
                loaded = benchmark.runner.load_existing_result(
                    "claude",
                    question,
                    0,
                    expected_provenance=expected_provenance,
                )
                self.assertIsNotNone(loaded)

                stale_payload = dict(payload)
                stale_payload.pop("benchmark_data_sha256")
                path.write_text(json.dumps(stale_payload, indent=2))
                self.assertIsNone(
                    benchmark.runner.load_existing_result(
                        "claude",
                        question,
                        0,
                        expected_provenance=expected_provenance,
                    )
                )

                mismatch_payload = dict(payload)
                mismatch_payload["question_sha256"] = "deadbeef"
                path.write_text(json.dumps(mismatch_payload, indent=2))
                self.assertIsNone(
                    benchmark.runner.load_existing_result(
                        "claude",
                        question,
                        0,
                        expected_provenance=expected_provenance,
                    )
                )
            finally:
                benchmark.config.set_results_dir(original_results_dir)


class GradeResponsePromptTests(unittest.TestCase):
    def test_grade_response_prompt_includes_alternates_and_warning_guidance(self) -> None:
        payload = json.loads(benchmark.DATA_FILE.read_text())
        question = next(item for item in payload["questions"] if item["id"] == "T29")
        captured: dict[str, str] = {}

        def fake_invoke_cli(
            judge: str,
            prompt: str,
            *,
            timeout_seconds: int,
            claude_model: str | None = None,
            codex_model: str | None = None,
            context_mode: str = benchmark.CONTEXT_MODE_AMBIENT,
        ) -> benchmark.CLIInvocation:
            del judge, timeout_seconds, claude_model, codex_model, context_mode
            captured["prompt"] = prompt
            return benchmark.CLIInvocation(
                stdout='{"score": 2, "reason": "ok", "used_posix": true, "traps_hit": []}',
                latency_ms=1,
            )

        with mock.patch.object(benchmark.runner.providers, "invoke_cli", side_effect=fake_invoke_cli):
            grade = benchmark.runner.grade_response(
                "claude",
                question,
                "$(( (3 + 5) * 2 ))",
                timeout_seconds=30,
            )

        self.assertEqual(grade.score, 2)
        self.assertIn("Acceptable alternate POSIX answers/patterns", captured["prompt"])
        self.assertIn("$(( ))", captured["prompt"])
        self.assertIn("Required concept groups", captured["prompt"])
        self.assertIn("warnings or rejections do NOT count as suggesting them", captured["prompt"])


class InvokeCliBytesRegressionTests(unittest.TestCase):
    """Regression: subprocess.TimeoutExpired.stderr can be bytes even when
    text=True was passed, which previously caused json.dumps to raise
    'Object of type bytes is not JSON serializable' inside invoke_cli."""

    def test_invoke_cli_handles_bytes_stderr_from_timeout(self) -> None:
        import subprocess
        from benchmark_core import providers as providers_module

        timeout_exc = subprocess.TimeoutExpired(cmd=["codex"], timeout=1)
        timeout_exc.stderr = b"partial stderr \xff\xfe bytes"
        timeout_exc.stdout = None

        with mock.patch.object(providers_module.subprocess, "run", side_effect=timeout_exc):
            invocation = benchmark.invoke_cli("codex", "prompt", timeout_seconds=1)

        # Must not raise, and stdout must be valid JSON parseable text.
        payload = json.loads(invocation.stdout)
        self.assertEqual(payload["error"], "timeout")
        self.assertIsInstance(payload["stderr"], str)

    def test_invoke_cli_handles_str_stderr_from_timeout(self) -> None:
        import subprocess
        from benchmark_core import providers as providers_module

        timeout_exc = subprocess.TimeoutExpired(cmd=["codex"], timeout=1)
        timeout_exc.stderr = "normal text stderr"
        timeout_exc.stdout = None

        with mock.patch.object(providers_module.subprocess, "run", side_effect=timeout_exc):
            invocation = benchmark.invoke_cli("codex", "prompt", timeout_seconds=1)

        payload = json.loads(invocation.stdout)
        self.assertEqual(payload["error"], "timeout")
        self.assertEqual(payload["stderr"], "normal text stderr")

    def test_invoke_cli_closes_stdin_for_subprocess(self) -> None:
        from benchmark_core import providers as providers_module

        captured_kwargs: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            del args
            captured_kwargs.update(kwargs)
            return providers_module.subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"status":"ok"}',
                stderr="",
            )

        with mock.patch.object(providers_module.subprocess, "run", side_effect=fake_run):
            benchmark.invoke_cli("codex", "prompt", timeout_seconds=1)

        self.assertIs(captured_kwargs["stdin"], providers_module.subprocess.DEVNULL)

    def test_invoke_cli_isolated_context_scrubs_cwd_flags_and_host_agent_env(self) -> None:
        from benchmark_core import providers as providers_module

        calls: list[tuple[list[str], dict[str, object]]] = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return providers_module.subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout='{"ok": true}',
                stderr="",
            )

        host_env = {
            "HOME": "/tmp/ambient-home-leak",
            "CODEX_THREAD_ID": "thread-leak",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "codex-app",
            "CODEX_HOME": "/tmp/codex-home-is-auth",
            "CLAUDE_CODE_SHELL": "1",
            "ANTHROPIC_API_KEY": "preserve-claude-auth",
            "GEMINI_API_KEY": "preserve-gemini-auth",
            "GEMINI_CLI_IDE_WORKSPACE_PATH": "/repo/leak",
        }

        with mock.patch.dict(providers_module.os.environ, host_env, clear=True), \
                mock.patch.object(providers_module.subprocess, "run", side_effect=fake_run):
            benchmark.invoke_cli(
                "claude",
                "prompt",
                timeout_seconds=1,
                claude_model="claude-opus-4-6",
                context_mode=benchmark.CONTEXT_MODE_ISOLATED,
            )
            benchmark.invoke_cli(
                "codex",
                "prompt",
                timeout_seconds=1,
                codex_model="gpt-5.4",
                context_mode=benchmark.CONTEXT_MODE_ISOLATED,
            )
            benchmark.invoke_cli(
                "gemini",
                "prompt",
                timeout_seconds=1,
                context_mode=benchmark.CONTEXT_MODE_ISOLATED,
            )

        claude_cmd, claude_kwargs = calls[0]
        codex_cmd, codex_kwargs = calls[1]
        gemini_cmd, gemini_kwargs = calls[2]

        self.assertIn("--setting-sources", claude_cmd)
        self.assertIn("--bare", claude_cmd)
        self.assertIn("--disable-slash-commands", claude_cmd)
        self.assertIn("--strict-mcp-config", claude_cmd)
        self.assertIn("--tools", claude_cmd)
        self.assertNotEqual(Path(claude_kwargs["cwd"]).resolve(), benchmark.SCRIPT_DIR.resolve())

        self.assertIn("--ignore-user-config", codex_cmd)
        self.assertIn("--ignore-rules", codex_cmd)
        self.assertIn("--ephemeral", codex_cmd)
        self.assertIn("--sandbox", codex_cmd)
        self.assertIn("read-only", codex_cmd)
        self.assertIn("--cd", codex_cmd)
        self.assertIn("-c", codex_cmd)
        self.assertIn("shell_environment_policy.inherit=none", codex_cmd)
        self.assertNotEqual(Path(codex_kwargs["cwd"]).resolve(), benchmark.SCRIPT_DIR.resolve())

        self.assertIn("--extensions", gemini_cmd)
        self.assertIn("none", gemini_cmd)
        self.assertIn("--allowed-mcp-server-names", gemini_cmd)
        gemini_home_settings = Path(gemini_kwargs["env"]["HOME"]) / ".gemini" / "settings.json"
        self.assertTrue(gemini_home_settings.exists())
        self.assertFalse(json.loads(gemini_home_settings.read_text())["skills"]["enabled"])
        gemini_settings = Path(gemini_kwargs["cwd"]) / ".gemini" / "settings.json"
        self.assertTrue(gemini_settings.exists())
        self.assertFalse(json.loads(gemini_settings.read_text())["skills"]["enabled"])

        for _, kwargs in calls:
            env = kwargs["env"]
            self.assertNotEqual(env["HOME"], "/tmp/ambient-home-leak")
            self.assertIn("sayance-", Path(env["HOME"]).name)
            self.assertEqual(env["XDG_CONFIG_HOME"], str(Path(env["HOME"]) / ".config"))
            self.assertEqual(env["XDG_DATA_HOME"], str(Path(env["HOME"]) / ".local" / "share"))
            self.assertEqual(env["XDG_CACHE_HOME"], str(Path(env["HOME"]) / ".cache"))
            self.assertNotIn("CODEX_THREAD_ID", env)
            self.assertNotIn("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", env)
            self.assertNotIn("CLAUDE_CODE_SHELL", env)
            self.assertNotIn("GEMINI_CLI_IDE_WORKSPACE_PATH", env)
            self.assertEqual(env["ANTHROPIC_API_KEY"], "preserve-claude-auth")
            self.assertEqual(env["GEMINI_API_KEY"], "preserve-gemini-auth")

        self.assertNotEqual(codex_kwargs["env"]["CODEX_HOME"], "/tmp/codex-home-is-auth")
        self.assertEqual(codex_kwargs["env"]["CODEX_HOME"], str(Path(codex_kwargs["env"]["HOME"]) / ".codex"))
        self.assertNotIn("CODEX_HOME", claude_kwargs["env"])
        self.assertNotIn("CODEX_HOME", gemini_kwargs["env"])


class PromptConstructionTests(unittest.TestCase):
    def test_build_effective_prompt_wraps_codex_in_benchmark_mode(self) -> None:
        from benchmark_core import runner as runner_module

        question = {
            "id": "T02",
            "question": "I need to know which `.conf` files anywhere on the system have changed since yesterday.",
        }

        prompt = runner_module._build_effective_prompt(question, llm="codex", inject_posix=False)

        self.assertIn("BENCHMARK MODE", prompt)
        self.assertIn("Do not inspect the local filesystem", prompt)
        self.assertIn(question["question"], prompt)

    def test_build_effective_prompt_wraps_codex_bridge_mode_without_direct_answer_instruction(self) -> None:
        from benchmark_core import runner as runner_module

        question = {"id": "T02", "question": "raw prompt"}

        prompt = runner_module._build_effective_prompt(
            question,
            llm="codex",
            inject_posix=True,
            load_posix_core_fn=lambda: "CORE",
        )

        self.assertIn("CORE", prompt)
        self.assertIn("TOOL INSTRUCTION", prompt)
        self.assertIn("`sayance-lookup <utility>`", prompt)
        self.assertIn("Exception: if this prompt's TOOL INSTRUCTION asks you to invoke", prompt)
        self.assertNotIn("Respond with the POSIX command you would recommend", prompt)
        self.assertIn("TASK:\nraw prompt", prompt)

    def test_build_effective_prompt_leaves_non_codex_unaided_prompt_raw(self) -> None:
        from benchmark_core import runner as runner_module

        question = {"id": "T01", "question": "raw prompt"}

        prompt = runner_module._build_effective_prompt(question, llm="claude", inject_posix=False)

        self.assertEqual(prompt, "raw prompt")

    def test_build_effective_prompt_bridge_mode_uses_real_task_newline_for_non_codex(self) -> None:
        from benchmark_core import runner as runner_module

        question = {"id": "T01", "question": "raw prompt"}

        prompt = runner_module._build_effective_prompt(
            question,
            llm="claude",
            inject_posix=True,
            load_posix_core_fn=lambda: "CORE",
        )

        self.assertIn("CORE", prompt)
        self.assertIn("TASK:\nraw prompt", prompt)
        self.assertNotIn(r"TASK:\nraw prompt", prompt)

    def test_result_provenance_distinguishes_context_mode_from_same_prompt(self) -> None:
        from benchmark_core import runner as runner_module

        question = {"id": "T01", "question": "raw prompt"}

        ambient = runner_module._result_provenance(
            question,
            prompt="raw prompt",
            context_mode=benchmark.CONTEXT_MODE_AMBIENT,
        )
        isolated = runner_module._result_provenance(
            question,
            prompt="raw prompt",
            context_mode=benchmark.CONTEXT_MODE_ISOLATED,
        )

        self.assertEqual(ambient["effective_prompt_sha256"], isolated["effective_prompt_sha256"])
        self.assertEqual(ambient["context_mode"], benchmark.CONTEXT_MODE_AMBIENT)
        self.assertEqual(isolated["context_mode"], benchmark.CONTEXT_MODE_ISOLATED)


if __name__ == "__main__":
    unittest.main()
