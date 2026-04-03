#!/usr/bin/env python3
"""Compare aggregate means across benchmark series directories.

Example:
  python3 scripts/compare_series_means.py \
    --injected results/stepup-scheduled-5h \
    --baseline results/baseline-scheduled-5h \
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


def find_latest_summary(run_dir: Path) -> Path | None:
    summaries = sorted(run_dir.glob("summary-*.json"))
    if not summaries:
        return None
    return summaries[-1]


def collect_series(series_dir: Path) -> dict:
    run_summaries: list[dict] = []
    for run_dir in sorted(series_dir.glob("run*")):
        if not run_dir.is_dir():
            continue
        summary_path = find_latest_summary(run_dir)
        if summary_path is None:
            continue
        run_summaries.append(json.loads(summary_path.read_text()))

    llm_data: dict[str, dict[str, list[float]]] = {}
    for summary in run_summaries:
        for llm, payload in summary.get("llms", {}).items():
            llm_bucket = llm_data.setdefault(llm, {metric: [] for metric in METRICS})
            for metric in METRICS:
                value = payload.get(metric)
                if isinstance(value, (int, float)):
                    llm_bucket[metric].append(float(value))

    aggregated: dict[str, dict[str, float | int]] = {}
    for llm, metric_values in llm_data.items():
        aggregated[llm] = {
            "runs_count": len(run_summaries),
            **{
                f"avg_{metric}": mean(values)
                for metric, values in metric_values.items()
                if values
            },
        }

    return {
        "series_dir": str(series_dir.resolve()),
        "runs_found": len(run_summaries),
        "llms": aggregated,
    }


def build_delta(
    injected: dict,
    baseline: dict,
) -> dict[str, dict[str, float]]:
    delta: dict[str, dict[str, float]] = {}
    common_llms = set(injected.get("llms", {}).keys()) & set(baseline.get("llms", {}).keys())
    for llm in sorted(common_llms):
        delta[llm] = {}
        inj_payload = injected["llms"][llm]
        base_payload = baseline["llms"][llm]
        for metric in METRICS:
            k = f"avg_{metric}"
            if k not in inj_payload or k not in base_payload:
                continue
            # Positive means baseline > injected.
            delta[llm][f"baseline_minus_injected_{metric}"] = base_payload[k] - inj_payload[k]
    return delta


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline vs injected series means")
    parser.add_argument("--injected", required=True, help="Injected series directory")
    parser.add_argument("--baseline", required=True, help="Baseline series directory")
    parser.add_argument("--out", required=False, help="Optional JSON output path")
    args = parser.parse_args()

    injected = collect_series(Path(args.injected))
    baseline = collect_series(Path(args.baseline))
    delta = build_delta(injected, baseline)

    report = {
        "injected": injected,
        "baseline": baseline,
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
