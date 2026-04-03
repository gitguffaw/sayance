import json
import unittest

from run_benchmark import parse_codex_tokens


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


if __name__ == "__main__":
    unittest.main()
