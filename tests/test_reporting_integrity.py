import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_benchmark as benchmark
from benchmark_core import config as benchmark_config
from benchmark_core import reporting as reporting_module
from benchmark_core.models import ExecutionMetrics, QuestionResult, ResponseAnalysis, TokenUsage
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


def make_result(
    q_id: str,
    *,
    response: str = "pax -w -f archive.pax directory/",
    usage_valid: bool = True,
) -> QuestionResult:
    return QuestionResult(
        id=q_id,
        llm="claude",
        model="claude-opus-4-7",
        requested_model="claude-opus-4-7",
        run_k=0,
        question=f"Question {q_id}",
        response=response,
        tokens=TokenUsage(
            input=10,
            input_cached=2,
            output=4,
            thoughts=0,
            billable=12,
            raw={},
            usage_valid=usage_valid,
            usage_invalid_reason="" if usage_valid else "missing usage telemetry",
        ),
        execution=ExecutionMetrics(
            latency_ms=100,
            step_count=1,
            tool_call_count=0,
            tool_calls_by_type={},
        ),
        analysis=ResponseAnalysis(
            minimal_answer="pax -w -f archive.pax directory/",
            minimal_word_count=4,
            minimal_shell_token_count=4,
            response_word_count=4,
            minimal_answer_gap_words=0,
            verbosity_ratio=1.0,
            posix_compliant=True,
            issue8_refusal=False,
            inefficiency_mode="minimal_or_near_minimal",
            estimated_excess_output_tokens=0,
        ),
        accuracy=None,
        execution_record=None,
        cache_state="cold",
        timestamp="20260416-000000",
    )


class ComparisonReportTests(unittest.TestCase):
    def test_save_comparison_report_renders_missing_metrics_as_na(self) -> None:
        unaided = make_summary(
            timestamp="20260403-100000",
            claude_payload={
                "model": "claude-opus-4-7",
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
                "model": "claude-opus-4-7",
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
                    [("Unaided", unaided), ("Experiment", experiment)]
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

            payload = collect_series(Path(tmpdir), allow_provenance_mismatch=True)

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
            payload = collect_series(Path(tmpdir), allow_provenance_mismatch=True)

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
            bridge_aided = root / "bridge-aided"
            unaided = root / "unaided"
            for series_dir in (bridge_aided, unaided):
                run_dir = series_dir / "run1"
                write_summary(run_dir / "summary-20260403-100000.json", summary)
                write_summary(run_dir / "summary-20260403-100100.json", summary)

            script = Path(__file__).resolve().parents[1] / "scripts" / "compare_series_means.py"

            failed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--bridge-aided",
                    str(bridge_aided),
                    "--unaided",
                    str(unaided),
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
                    "--bridge-aided",
                    str(bridge_aided),
                    "--unaided",
                    str(unaided),
                    "--allow-ambiguous-summaries",
                    "--allow-provenance-mismatch",
                    "--out",
                    str(out_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(succeeded.returncode, 0, succeeded.stderr)
            self.assertTrue(out_path.exists())

    def test_collect_series_rejects_missing_benchmark_hash_by_default(self) -> None:
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
            write_summary(Path(tmpdir) / "run1" / "summary-20260403-100000.json", summary)
            with self.assertRaisesRegex(ValueError, "Missing benchmark_data_sha256"):
                collect_series(Path(tmpdir))

            payload = collect_series(Path(tmpdir), allow_provenance_mismatch=True)

        self.assertEqual(payload["benchmark_data_sha256"], None)

    def test_compare_series_cli_rejects_mismatched_benchmark_hashes_by_default(self) -> None:
        bridge_summary = make_summary(
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
        bridge_summary["provenance"] = {"benchmark_data_sha256": "bridge-sha"}

        unaided_summary = make_summary(
            timestamp="20260403-100000",
            claude_payload={
                "mean_output_tokens": 11,
                "mean_latency_ms": 101,
                "total_billable_tokens": 26,
                "total_estimated_excess_output_tokens": 4,
                "total_simulation_adjusted_billable_tokens": 21,
                "posix_compliance_rate": 0.9,
            },
        )
        unaided_summary["provenance"] = {"benchmark_data_sha256": "unaided-sha"}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bridge_aided = root / "bridge-aided"
            unaided = root / "unaided"
            write_summary(bridge_aided / "run1" / "summary-20260403-100000.json", bridge_summary)
            write_summary(unaided / "run1" / "summary-20260403-100000.json", unaided_summary)

            script = Path(__file__).resolve().parents[1] / "scripts" / "compare_series_means.py"

            failed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--bridge-aided",
                    str(bridge_aided),
                    "--unaided",
                    str(unaided),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Mismatched benchmark_data_sha256", failed.stderr)

            out_path = root / "comparison.json"
            succeeded = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--bridge-aided",
                    str(bridge_aided),
                    "--unaided",
                    str(unaided),
                    "--allow-provenance-mismatch",
                    "--out",
                    str(out_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(succeeded.returncode, 0, succeeded.stderr)
            self.assertTrue(out_path.exists())


class ProvenanceReportingTests(unittest.TestCase):
    def test_enrich_run_metadata_promotes_flat_provenance_fields(self) -> None:
        metadata = benchmark_config.enrich_run_metadata(
            {
                "mode": "unaided",
                "benchmark_data_sha256": "benchmark-sha",
                "git_commit": "abc123",
            }
        )

        self.assertEqual(metadata["mode"], "unaided")
        self.assertEqual(
            metadata["provenance"]["benchmark_data_sha256"],
            "benchmark-sha",
        )
        self.assertEqual(metadata["provenance"]["git_commit"], "abc123")
        self.assertNotIn("benchmark_data_sha256", metadata)
        self.assertNotIn("git_commit", metadata)

    def test_save_summary_writes_provenance_to_summary_and_manifest(self) -> None:
        provenance = {
            "benchmark_data_sha256": "bench-sha",
            "benchmark_meta_version": "0.6",
            "benchmark_meta_date": "2026-04-09",
            "benchmark_question_count": 40,
            "git_commit": "deadbeef",
            "prompt_template_version": "7",
            "posix_core_sha256": "core-sha",
            "posix_tldr_sha256": "tldr-sha",
            "fixtures_manifest_sha256": "fixtures-sha",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark_config.RESULTS_DIR
            benchmark_config.set_results_dir(Path(tmpdir))
            try:
                with mock.patch.object(
                    benchmark_config,
                    "default_run_provenance",
                    return_value=provenance,
                ), mock.patch.object(
                    benchmark_config,
                    "current_run_slug",
                    return_value="D2026-04-16-T10-00-00",
                ):
                    summary_path = reporting_module.save_summary(
                        {"claude": [make_result("T06")]},
                        requested_models={"claude": "claude-opus-4-7"},
                        run_metadata={"mode": "unaided", "label": "test-run"},
                    )
            finally:
                benchmark_config.set_results_dir(original_results_dir)

            summary = json.loads(summary_path.read_text())
            manifest = json.loads((Path(tmpdir) / "run.json").read_text())

        self.assertEqual(summary["summary_schema_version"], "0.5")
        self.assertEqual(summary["spec"], benchmark_config.BENCHMARK_SPEC)
        self.assertEqual(summary["spec_utilities_count"], benchmark_config.SPEC_UTILITIES_COUNT)
        self.assertEqual(summary["utilities_count"], summary["bridge_utilities_count"])
        self.assertEqual(summary["provenance"], provenance)
        self.assertEqual(summary["run_metadata"]["provenance"], provenance)
        self.assertEqual(manifest["provenance"], provenance)
        self.assertEqual(manifest["mode"], "unaided")
        self.assertEqual(manifest["label"], "test-run")

    def test_save_summary_keeps_nested_provenance_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_results_dir = benchmark_config.RESULTS_DIR
            benchmark_config.set_results_dir(Path(tmpdir))
            try:
                with mock.patch.object(
                    benchmark_config,
                    "default_run_provenance",
                    return_value={"benchmark_data_sha256": "default-sha", "git_commit": "default"},
                ), mock.patch.object(
                    benchmark_config,
                    "current_run_slug",
                    return_value="D2026-04-16-T10-00-01",
                ):
                    summary_path = reporting_module.save_summary(
                        {"claude": [make_result("T25")]},
                        run_metadata={
                            "mode": "bridge-aided",
                            "provenance": {
                                "git_commit": "override-commit",
                                "prompt_template_version": "9",
                            },
                        },
                    )
            finally:
                benchmark_config.set_results_dir(original_results_dir)

            summary = json.loads(summary_path.read_text())

        self.assertEqual(summary["provenance"]["benchmark_data_sha256"], "default-sha")
        self.assertEqual(summary["provenance"]["git_commit"], "override-commit")
        self.assertEqual(summary["provenance"]["prompt_template_version"], "9")


if __name__ == "__main__":
    unittest.main()
