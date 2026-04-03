import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import run_benchmark as benchmark
from run_benchmark import save_comparison_report
from scripts.compare_series_means import collect_series


def make_summary(
    *,
    timestamp: str,
    claude_payload: dict,
) -> dict:
    return {
        "timestamp": timestamp,
        "llms": {
            "claude": claude_payload,
        },
    }


def write_summary(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


class ComparisonReportTests(unittest.TestCase):
    def test_save_comparison_report_renders_missing_metrics_as_na(self) -> None:
        baseline = make_summary(
            timestamp="20260403-100000",
            claude_payload={
                "model": "claude-opus-4-6",
                "valid_results": 1,
                "total_results": 1,
                "posix_compliance_rate": 1.0,
                "mean_output_tokens": 10,
                "mean_latency_ms": 100,
                "mean_latency_seconds": 0.1,
                "mean_step_count": 1.0,
                "total_input_tokens": 50,
                "total_cached_tokens": 10,
                "total_output_tokens": 10,
                "total_estimated_excess_output_tokens": 3,
                "total_billable_tokens": 25,
                "issue8_refusal_count": 0,
                "inefficiency_modes": {"minimal_or_near_minimal": 1},
                "errors": [
                    {
                        "question_id": "T02",
                        "error": "missing usage telemetry",
                        "latency_ms": 120,
                        "kind": "usage_invalid",
                    }
                ],
            },
        )
        experiment = make_summary(
            timestamp="20260403-110000",
            claude_payload={
                "model": "claude-opus-4-6",
                "valid_results": 1,
                "total_results": 1,
                "posix_compliance_rate": 0.5,
                "mean_latency_ms": 90,
                "mean_latency_seconds": 0.09,
                "mean_step_count": 1.2,
                "total_input_tokens": 60,
                "total_cached_tokens": 11,
                "total_output_tokens": 12,
                "total_estimated_excess_output_tokens": 5,
                "total_cost_usd": 1.2345,
                "issue8_refusal_count": 1,
                "inefficiency_modes": {"over_explaining": 1},
                "errors": [],
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark.RESULTS_DIR
            benchmark.RESULTS_DIR = Path(tmpdir)
            try:
                report_path = save_comparison_report(
                    [("Baseline", baseline), ("Experiment", experiment)]
                )
                html = report_path.read_text()
            finally:
                benchmark.RESULTS_DIR = original_results_dir

        self.assertIn("Total Billable Tokens (provider-semantic)", html)
        self.assertIn("usage invalid", html)

        mean_output_row = re.search(
            r"<tr><td class='metric-name'>Mean Output Tokens</td>(.*?)</tr>",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(mean_output_row)
        self.assertIn(">10<", mean_output_row.group(1))
        self.assertIn("class='na'>N/A</td>", mean_output_row.group(1))
        self.assertNotIn("delta", mean_output_row.group(1))

        self.assertNotIn("Total Cost (USD)", html)


class SeriesComparisonTests(unittest.TestCase):
    def test_collect_series_rejects_ambiguous_summaries_by_default(self) -> None:
        summary = make_summary(
            timestamp="20260403-100000",
            claude_payload={
                "mean_output_tokens": 10,
                "mean_latency_ms": 100,
                "total_billable_tokens": 25,
                "total_estimated_excess_output_tokens": 3,
                "total_simulation_adjusted_billable_tokens": 20,
                "posix_compliance_rate": 1.0,
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run1"
            write_summary(run_dir / "summary-20260403-100000.json", summary)
            write_summary(run_dir / "summary-20260403-100100.json", summary)

            with self.assertRaisesRegex(ValueError, "Ambiguous summaries"):
                collect_series(Path(tmpdir))

    def test_collect_series_tracks_metric_sample_counts(self) -> None:
        run1 = make_summary(
            timestamp="20260403-100000",
            claude_payload={
                "mean_output_tokens": 10,
                "mean_latency_ms": 100,
                "total_billable_tokens": 25,
                "total_estimated_excess_output_tokens": 3,
                "total_simulation_adjusted_billable_tokens": 20,
                "posix_compliance_rate": 1.0,
            },
        )
        run2 = make_summary(
            timestamp="20260403-110000",
            claude_payload={
                "mean_output_tokens": 20,
                "total_billable_tokens": 35,
                "total_estimated_excess_output_tokens": 4,
                "total_simulation_adjusted_billable_tokens": 28,
                "posix_compliance_rate": 0.5,
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            write_summary(Path(tmpdir) / "run1" / "summary-20260403-100000.json", run1)
            write_summary(Path(tmpdir) / "run2" / "summary-20260403-110000.json", run2)

            payload = collect_series(Path(tmpdir))

        claude = payload["llms"]["claude"]
        self.assertEqual(claude["runs_count"], 2)
        self.assertEqual(claude["metric_sample_counts"]["mean_output_tokens"], 2)
        self.assertEqual(claude["metric_sample_counts"]["mean_latency_ms"], 1)
        self.assertEqual(claude["avg_mean_output_tokens"], 15.0)
        self.assertEqual(claude["avg_mean_latency_ms"], 100.0)

    def test_collect_series_uses_llm_specific_runs_count(self) -> None:
        run1 = {
            "timestamp": "20260403-100000",
            "llms": {
                "claude": {
                    "mean_output_tokens": 10,
                    "mean_latency_ms": 100,
                    "total_billable_tokens": 25,
                    "total_estimated_excess_output_tokens": 3,
                    "total_simulation_adjusted_billable_tokens": 20,
                    "posix_compliance_rate": 1.0,
                }
            },
        }
        run2 = {
            "timestamp": "20260403-110000",
            "llms": {
                "gemini": {
                    "mean_output_tokens": 12,
                    "mean_latency_ms": 80,
                    "total_billable_tokens": 22,
                    "total_estimated_excess_output_tokens": 2,
                    "total_simulation_adjusted_billable_tokens": 19,
                    "posix_compliance_rate": 0.8,
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            write_summary(Path(tmpdir) / "run1" / "summary-20260403-100000.json", run1)
            write_summary(Path(tmpdir) / "run2" / "summary-20260403-110000.json", run2)
            payload = collect_series(Path(tmpdir))

        claude = payload["llms"]["claude"]
        gemini = payload["llms"]["gemini"]
        self.assertEqual(claude["runs_count"], 1)
        self.assertEqual(gemini["runs_count"], 1)
        self.assertEqual(claude["metric_sample_counts"]["mean_output_tokens"], 1)
        self.assertEqual(gemini["metric_sample_counts"]["mean_output_tokens"], 1)

    def test_compare_series_cli_allows_ambiguous_override_flag(self) -> None:
        summary = make_summary(
            timestamp="20260403-100000",
            claude_payload={
                "mean_output_tokens": 10,
                "mean_latency_ms": 100,
                "total_billable_tokens": 25,
                "total_estimated_excess_output_tokens": 3,
                "total_simulation_adjusted_billable_tokens": 20,
                "posix_compliance_rate": 1.0,
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            injected = root / "injected"
            baseline = root / "baseline"
            for series_dir in (injected, baseline):
                run_dir = series_dir / "run1"
                write_summary(run_dir / "summary-20260403-100000.json", summary)
                write_summary(run_dir / "summary-20260403-100100.json", summary)

            script = Path(__file__).resolve().parents[1] / "scripts" / "compare_series_means.py"

            failed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--injected",
                    str(injected),
                    "--baseline",
                    str(baseline),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Ambiguous summaries", failed.stderr)

            out_path = root / "comparison.json"
            succeeded = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--injected",
                    str(injected),
                    "--baseline",
                    str(baseline),
                    "--allow-ambiguous-summaries",
                    "--out",
                    str(out_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(succeeded.returncode, 0, succeeded.stderr)
            self.assertTrue(out_path.exists())


if __name__ == "__main__":
    unittest.main()
