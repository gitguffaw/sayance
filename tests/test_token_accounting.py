import contextlib
import json
import io
import tempfile
import unittest
from pathlib import Path

import run_benchmark as benchmark
from run_benchmark import (
    ExecutionMetrics,
    QuestionResult,
    ResponseAnalysis,
    TokenUsage,
    parse_claude_tokens,
    parse_codex_tokens,
    parse_gemini_execution,
    parse_gemini_tokens,
    raw_usage_input_billable_tokens,
    save_summary,
    save_visual_report,
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
        self.assertEqual(tokens.cost_source, "usage_invalid")
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
        self.assertEqual(tokens.cost_source, "reported")

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


class ValidityReportingTests(unittest.TestCase):
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
                cost_usd=None,
                cost_source="calculated",
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
                cost_usd=None,
                cost_source="usage_invalid",
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
                cost_usd=None,
                cost_source="error",
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
                cost_usd=None,
                cost_source="calculated",
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
                cost_usd=None,
                cost_source="usage_invalid",
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
                cost_usd=None,
                cost_source="parse_error",
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
                cost_usd=None,
                cost_source="calculated",
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
                cost_usd=None,
                cost_source="usage_invalid",
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


if __name__ == "__main__":
    unittest.main()
