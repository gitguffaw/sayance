#!/usr/bin/env python3
"""Compare aggregate means across benchmark series directories.

Example:
  python3 scripts/compare_series_means.py \
    --bridge-aided results/bridge-aided-scheduled-5h \
    --unaided results/unaided-scheduled-5h \
    --out results/series-comparison.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


METRICS = [
    "mean_output_tokens",
    "mean_latency_ms",
    "total_billable_tokens",
    "total_estimated_excess_output_tokens",
    "total_simulation_adjusted_billable_tokens",
    "posix_compliance_rate",
]


def summary_benchmark_hash(summary: dict) -> str | None:
    provenance = summary.get("provenance")
    if isinstance(provenance, dict):
        value = provenance.get("benchmark_data_sha256")
        if isinstance(value, str) and value:
            return value

    run_metadata = summary.get("run_metadata")
    if isinstance(run_metadata, dict):
        nested = run_metadata.get("provenance")
        if isinstance(nested, dict):
            value = nested.get("benchmark_data_sha256")
            if isinstance(value, str) and value:
                return value

    return None


def find_latest_summary(run_dir: Path, *, allow_ambiguous_summaries: bool = False) -> Path | None:
    summaries = sorted(run_dir.glob("summary-*.json"))
    if not summaries:
        return None
    if len(summaries) > 1 and not allow_ambiguous_summaries:
        raise ValueError(
            f"Ambiguous summaries in {run_dir}: "
            + ", ".join(summary.name for summary in summaries)
        )
    return summaries[-1]


def collect_series(
    series_dir: Path,
    *,
    allow_ambiguous_summaries: bool = False,
    allow_provenance_mismatch: bool = False,
) -> dict:
    run_summaries: list[dict] = []
    benchmark_hashes: set[str] = set()
    for run_dir in sorted(series_dir.glob("run*")):
        if not run_dir.is_dir():
            continue
        summary_path = find_latest_summary(
            run_dir,
            allow_ambiguous_summaries=allow_ambiguous_summaries,
        )
        if summary_path is None:
            continue
        summary = json.loads(summary_path.read_text())
        benchmark_hash = summary_benchmark_hash(summary)
        if not benchmark_hash and not allow_provenance_mismatch:
            raise ValueError(f"Missing benchmark_data_sha256 in {summary_path}")
        if benchmark_hash:
            benchmark_hashes.add(benchmark_hash)
        run_summaries.append(summary)

    if len(benchmark_hashes) > 1 and not allow_provenance_mismatch:
        raise ValueError(
            f"Mismatched benchmark_data_sha256 values in {series_dir}: "
            + ", ".join(sorted(benchmark_hashes))
        )

    llm_data: dict[str, dict[str, list[float]]] = {}
    llm_runs_count: dict[str, int] = {}
    for summary in run_summaries:
        for llm, payload in summary.get("llms", {}).items():
            llm_runs_count[llm] = llm_runs_count.get(llm, 0) + 1
            llm_bucket = llm_data.setdefault(llm, {metric: [] for metric in METRICS})
            for metric in METRICS:
                value = payload.get(metric)
                if isinstance(value, (int, float)):
                    llm_bucket[metric].append(float(value))

    aggregated: dict[str, dict[str, float | int]] = {}
    for llm, metric_values in llm_data.items():
        aggregated[llm] = {
            "runs_count": llm_runs_count.get(llm, 0),
            "metric_sample_counts": {
                metric: len(values)
                for metric, values in metric_values.items()
                if values
            },
            **{
                f"avg_{metric}": mean(values)
                for metric, values in metric_values.items()
                if values
            },
        }

    return {
        "series_dir": str(series_dir.resolve()),
        "runs_found": len(run_summaries),
        "benchmark_data_sha256": next(iter(benchmark_hashes), None),
        "llms": aggregated,
    }


def build_delta(
    bridge_aided: dict,
    unaided: dict,
) -> dict[str, dict[str, float]]:
    delta: dict[str, dict[str, float]] = {}
    common_llms = set(bridge_aided.get("llms", {}).keys()) & set(unaided.get("llms", {}).keys())
    for llm in sorted(common_llms):
        delta[llm] = {}
        ba_payload = bridge_aided["llms"][llm]
        ua_payload = unaided["llms"][llm]
        for metric in METRICS:
            k = f"avg_{metric}"
            if k not in ba_payload or k not in ua_payload:
                continue
            # Positive means unaided > bridge-aided.
            delta[llm][f"unaided_minus_bridge_aided_{metric}"] = ua_payload[k] - ba_payload[k]
    return delta


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare unaided vs bridge-aided series means")
    parser.add_argument("--bridge-aided", required=True, help="Bridge-aided series directory")
    parser.add_argument("--unaided", required=True, help="Unaided series directory")
    parser.add_argument("--out", required=False, help="Optional JSON output path")
    parser.add_argument(
        "--allow-ambiguous-summaries",
        action="store_true",
        help="Use the latest summary in run directories that contain multiple summary-*.json files",
    )
    parser.add_argument(
        "--allow-provenance-mismatch",
        action="store_true",
        help="Allow comparisons when summaries are missing or disagree on benchmark_data_sha256",
    )
    args = parser.parse_args()

    bridge_aided = collect_series(
        Path(args.bridge_aided),
        allow_ambiguous_summaries=args.allow_ambiguous_summaries,
        allow_provenance_mismatch=args.allow_provenance_mismatch,
    )
    unaided = collect_series(
        Path(args.unaided),
        allow_ambiguous_summaries=args.allow_ambiguous_summaries,
        allow_provenance_mismatch=args.allow_provenance_mismatch,
    )
    if (
        not args.allow_provenance_mismatch
        and bridge_aided.get("benchmark_data_sha256")
        and unaided.get("benchmark_data_sha256")
        and bridge_aided["benchmark_data_sha256"] != unaided["benchmark_data_sha256"]
    ):
        parser.error(
            "Mismatched benchmark_data_sha256 between series: "
            f"{bridge_aided['benchmark_data_sha256']} vs {unaided['benchmark_data_sha256']}"
        )
    delta = build_delta(bridge_aided, unaided)

    report = {
        "bridge_aided": bridge_aided,
        "unaided": unaided,
        "delta": delta,
    }

    rendered = json.dumps(report, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n")
        print(f"Saved comparison: {out_path}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
