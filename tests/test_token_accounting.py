import json
import unittest

from run_benchmark import (
    parse_claude_tokens,
    parse_codex_tokens,
    parse_gemini_execution,
    parse_gemini_tokens,
    raw_usage_input_billable_tokens,
)


def jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(event) for event in events)


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


if __name__ == "__main__":
    unittest.main()
