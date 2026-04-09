import json
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

from benchmark_core import config
from benchmark_core.models import (
    QuestionResult,
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
from benchmark_core.providers import (
    format_seconds_from_ms,
    prune_timestamped_artifacts,
    tool_simulation_adjustment,
)


def generate_report(all_results: dict[str, list[QuestionResult]], questions: list[dict]) -> None:
    """Print a formatted benchmark report with efficiency and inefficiency-mode metrics."""
    if not all_results:
        return

    q_lookup = {q["id"]: q for q in questions}

    print(f"\n{'=' * 70}")
    print(f"  POSIX TOKEN EFFICIENCY REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Spec: POSIX.1-2024 (Issue 8) — 155 utilities")
    print(f"{'=' * 70}\n")

    for llm, results in all_results.items():
        if not results:
            continue

        token_results = usage_valid_results(results)
        visible_results = report_visible_results(results)
        provider_errors = error_results(results)
        invalid_usage = usage_invalid_results(results)
        if not token_results and not visible_results and not provider_errors:
            print(f"  {llm.upper()}: No reportable results\n")
            continue

        # Detect model from first result
        model = first_result_model(token_results or visible_results or provider_errors)

        inputs = [r.tokens.input for r in token_results]
        outputs = [r.tokens.output for r in token_results]
        cached = [r.tokens.input_cached for r in token_results]
        thoughts = [r.tokens.thoughts for r in token_results]
        billable = [r.tokens.billable for r in token_results]
        latency = [r.execution.latency_ms for r in visible_results]
        steps = [r.execution.step_count for r in visible_results]
        excess = [r.analysis.estimated_excess_output_tokens for r in token_results]
        costs = [r.tokens.cost_usd for r in token_results if r.tokens.cost_usd is not None]
        compliant = [r for r in visible_results if r.analysis.posix_compliant]
        issue8_refusals = [r for r in visible_results if r.analysis.issue8_refusal]
        inefficiency_modes = Counter(r.analysis.inefficiency_mode for r in visible_results)
        adjustments = [tool_simulation_adjustment(r.tokens) for r in token_results]

        def stats(values: list[int | float]) -> str:
            if not values:
                return "n/a"
            s = sorted(values)
            n = len(s)
            mean = sum(s) / n
            median = s[n // 2]
            return f"mean={mean:.0f}  median={median:.0f}  min={s[0]:.0f}  max={s[-1]:.0f}"

        print(f"  {llm.upper()} — model: {model}")
        print(f"  {'─' * 50}")
        print(f"    Input tokens:   {stats(inputs)}")
        print(f"    Output tokens:  {stats(outputs)}")
        print(f"    Cached input:   {stats(cached)}")
        print(f"    Thoughts:       {stats(thoughts)}")
        print(f"    Billable:       {stats(billable)}")
        if costs:
            print(f"    Cost (USD):     mean={sum(costs)/len(costs):.4f}  total={sum(costs):.4f}")
        else:
            print(f"    Cost (USD):     not reported")
        print(
            "    Tool-sim adjusted billable: "
            f"{stats([adjusted.adjusted_billable for adjusted in adjustments])}"
        )
        source_counts = Counter(adjustment.source for adjustment in adjustments if adjustment.source != "none")
        if source_counts:
            source_breakdown = ", ".join(
                f"{source}={count}" for source, count in source_counts.items()
            )
            print(f"    Tool-sim adjustment sources: {source_breakdown}")
        integrity_violations = [adjustment for adjustment in adjustments if adjustment.integrity_violation]
        if integrity_violations:
            print(
                f"    Tool-sim integrity violations: {len(integrity_violations)} "
                f"(max_overflow={max(v.integrity_violation_amount for v in integrity_violations)})"
            )
        print(f"    Latency ms:     {stats(latency)}")
        print(f"    Step count:     {stats(steps)}")
        print(f"    Excess output:  {stats(excess)}")

        if visible_results:
            print(
                "    POSIX compliant:"
                f" {len(compliant)}/{len(visible_results)} ({len(compliant)/len(visible_results)*100:.1f}%)"
            )
            print(f"    Issue 8 refusals: {len(issue8_refusals)}")
            mode_str = ", ".join(f"{k}={v}" for k, v in inefficiency_modes.most_common())
            print(f"    Modes: {mode_str}")
        else:
            print("    POSIX compliant: n/a")
            print("    Issue 8 refusals: n/a")
            print("    Modes: n/a")

        total_results = len(results)
        if invalid_usage:
            print(
                f"    Usage invalid: {len(invalid_usage)}/{total_results} "
                f"(excluded from token/cost aggregates)"
            )
            reason_counts = invalid_usage_reason_counts(results)
            reason_str = ", ".join(
                f"{reason}={count}" for reason, count in reason_counts.items()
            )
            print(f"    Usage invalid reasons: {reason_str}")
        if provider_errors:
            print(
                f"    Provider errors: {len(provider_errors)}/{total_results} "
                f"(excluded from report-visible metrics)"
            )
            for error in provider_errors:
                print(
                    f"      - {error.id}: {error.response.removeprefix('[ERROR] ')} "
                    f"({error.execution.latency_ms}ms)"
                )
        print()

    print(f"{'=' * 70}")
    print("  TOP OVER-BUDGET RESPONSES (by estimated excess output tokens)")
    print(f"{'=' * 70}\n")

    all_visible = []
    for results in all_results.values():
        all_visible.extend(report_visible_results(results))

    by_excess = sorted(all_visible, key=lambda r: r.analysis.estimated_excess_output_tokens, reverse=True)
    for r in by_excess:
        tier = q_lookup.get(r.id, {}).get("tier", "?")
        compliance = "posix" if r.analysis.posix_compliant else "miss"
        print(
            f"    {r.llm:>8} [{r.id}] T{tier} "
            f"out:{r.tokens.output:>5} excess:{r.analysis.estimated_excess_output_tokens:>5} "
            f"lat:{r.execution.latency_ms:>5}ms gap:{r.analysis.minimal_answer_gap_words:>4}w "
            f"{compliance:>5} {r.analysis.inefficiency_mode}"
        )
        print(f"             {r.question[:65]}")
        print(f"             minimal: {r.analysis.minimal_answer}")

    print()


def save_summary(
    all_results: dict[str, list[QuestionResult]],
    *,
    requested_models: dict[str, str | None] | None = None,
    retain_latest_only: bool = False,
) -> Path:
    """Save a combined summary JSON file."""
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_path = config.RESULTS_DIR / f"summary-{ts}.json"

    summary = {
        "version": "0.4",
        "timestamp": ts,
        "spec": "POSIX.1-2024 (Issue 8)",
        "utilities_count": 155,
        "requested_models": requested_models or {},
        "llms": {},
    }

    for llm, results in all_results.items():
        token_results = usage_valid_results(results)
        visible_results = report_visible_results(results)
        invalid_usage = usage_invalid_results(results)
        model = first_result_model(token_results or visible_results or error_results(results))
        inefficiency_modes = Counter(r.analysis.inefficiency_mode for r in visible_results)
        adjustments = [tool_simulation_adjustment(r.tokens) for r in token_results]
        adjustment_sources = Counter(a.source for a in adjustments if a.source != "none")
        integrity_violations = [
            {
                "question_id": result.id,
                "reason": adjustment.integrity_violation_reason,
                "amount": adjustment.integrity_violation_amount,
                "source": adjustment.source,
            }
            for result, adjustment in zip(token_results, adjustments)
            if adjustment.integrity_violation
        ]
        summary["llms"][llm] = {
            "model": model,
            "requested_model": (requested_models or {}).get(llm),
            "total_results": len(results),
            "valid_results": len(token_results),
            "usage_valid_results": len(token_results),
            "report_visible_results": len(visible_results),
            "usage_invalid_results": len(invalid_usage),
            "invalid_usage_reasons": dict(invalid_usage_reason_counts(results)),
            "total_input_tokens": sum(r.tokens.input for r in token_results),
            "total_cached_tokens": sum(r.tokens.input_cached for r in token_results),
            "total_billable_tokens": sum(r.tokens.billable for r in token_results),
            "total_simulation_adjusted_billable_tokens": sum(
                adjustment.adjusted_billable for adjustment in adjustments
            ),
            "total_tool_simulation_replay_input_tokens": sum(
                adjustment.replay_input_billable for adjustment in adjustments
            ),
            "total_tool_simulation_prompt_replay_input_tokens": sum(
                adjustment.prompt_replay_input_billable for adjustment in adjustments
            ),
            "total_tool_simulation_replayed_tool_call_input_tokens": sum(
                adjustment.replayed_tool_call_input_billable for adjustment in adjustments
            ),
            "total_tool_call_stub_output_tokens": sum(
                adjustment.tool_call_output for adjustment in adjustments
            ),
            "total_tool_simulation_tool_result_input_tokens": sum(
                adjustment.tool_result_input_billable for adjustment in adjustments
            ),
            "total_tool_simulation_follow_up_instruction_input_tokens": sum(
                adjustment.follow_up_instruction_input_billable for adjustment in adjustments
            ),
            "tool_simulation_adjustment_sources": dict(adjustment_sources),
            "tool_simulation_integrity_violation_count": len(integrity_violations),
            "tool_simulation_integrity_violations": integrity_violations,
            "total_output_tokens": sum(r.tokens.output for r in token_results),
            "total_estimated_excess_output_tokens": sum(
                r.analysis.estimated_excess_output_tokens for r in token_results
            ),
            "total_cost_usd": sum(
                r.tokens.cost_usd for r in token_results if r.tokens.cost_usd is not None
            ),
            "mean_output_tokens": (
                sum(r.tokens.output for r in token_results) / len(token_results) if token_results else 0
            ),
            "mean_latency_ms": (
                sum(r.execution.latency_ms for r in visible_results) / len(visible_results) if visible_results else 0
            ),
            "mean_latency_seconds": (
                (sum(r.execution.latency_ms for r in visible_results) / len(visible_results) / 1000.0)
                if visible_results else 0
            ),
            "mean_step_count": (
                sum(r.execution.step_count for r in visible_results) / len(visible_results) if visible_results else 0
            ),
            "posix_compliance_rate": (
                sum(1 for r in visible_results if r.analysis.posix_compliant) / len(visible_results)
                if visible_results else 0
            ),
            "issue8_refusal_count": sum(1 for r in visible_results if r.analysis.issue8_refusal),
            "inefficiency_modes": dict(inefficiency_modes),
            # Back-compat for older compare/report tooling.
            "failure_modes": dict(inefficiency_modes),
            "errors": summary_error_entries(results),
        }

        # Track 3: execution validation metrics
        executed = [r for r in visible_results if r.execution_record and not r.execution_record.exec_skipped]
        if executed:
            successes = sum(1 for r in executed if r.execution_record.exec_success)
            summary["llms"][llm]["exec_success_rate"] = successes / len(executed)
            summary["llms"][llm]["exec_attempted"] = len(executed)
            summary["llms"][llm]["exec_passed"] = successes

    summary_path.write_text(json.dumps(summary, indent=2))
    if retain_latest_only:
        prune_timestamped_artifacts(config.RESULTS_DIR, "summary-*.json", summary_path)
    print(f"  Summary saved: {summary_path}")
    return summary_path


def save_visual_report(
    all_results: dict[str, list[QuestionResult]],
    questions: list[dict],
    *,
    retain_latest_only: bool = False,
) -> Path:
    """Save a self-contained HTML report with charts and task scorecards."""
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = config.RESULTS_DIR / f"report-{ts}.html"

    q_lookup = {q["id"]: q for q in questions}
    all_usage_valid = [
        result
        for results in all_results.values()
        for result in results
        if result_is_usage_valid(result)
    ]
    all_visible = [
        result
        for results in all_results.values()
        for result in results
        if result_is_report_visible(result)
    ]
    all_errors = [
        result
        for results in all_results.values()
        for result in results
        if result_is_error(result)
    ]
    all_flat = [
        result
        for results in all_results.values()
        for result in results
    ]

    def mean(values: list[int | float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def pct(value: float) -> str:
        return f"{value * 100:.0f}%"

    max_output = max((r.tokens.output for r in all_visible), default=1)
    max_excess = max((r.analysis.estimated_excess_output_tokens for r in all_visible), default=1)
    max_latency_seconds = max((r.execution.latency_ms / 1000.0 for r in all_visible), default=1.0)

    # --- Model cards ---
    model_cards = []
    for llm, results in all_results.items():
        token_results = usage_valid_results(results)
        visible_results = report_visible_results(results)
        errors = error_results(results)
        invalid_usage = usage_invalid_results(results)
        if not visible_results and not errors:
            continue
        inefficiency_modes = Counter(r.analysis.inefficiency_mode for r in visible_results)
        model_cards.append({
            "llm": llm,
            "model": first_result_model(token_results or visible_results or errors),
            "count": len(visible_results),
            "usage_valid_count": len(token_results),
            "invalid_usage_count": len(invalid_usage),
            "total": len(results),
            "error_count": len(errors),
            "compliance_rate": (
                sum(1 for r in visible_results if r.analysis.posix_compliant) / len(visible_results)
                if visible_results else 0
            ),
            "issue8_refusal_count": sum(1 for r in visible_results if r.analysis.issue8_refusal),
            "mean_output": mean([r.tokens.output for r in token_results]),
            "mean_excess": mean([r.analysis.estimated_excess_output_tokens for r in token_results]),
            "mean_latency": mean([r.execution.latency_ms / 1000.0 for r in visible_results]),
            "mean_steps": mean([r.execution.step_count for r in visible_results]),
            "tool_calls": sum(r.execution.tool_call_count for r in visible_results),
            "total_cost": sum(r.tokens.cost_usd for r in token_results if r.tokens.cost_usd is not None),
            "inefficiency_modes": inefficiency_modes,
            "errors": errors,
            "invalid_usage": invalid_usage,
        })

    # --- Tier breakdown per model ---
    tier_breakdown_rows = []
    for card in model_cards:
        llm = card["llm"]
        visible_results = report_visible_results(all_results[llm])
        for tier_num, tier_label in [(1, "Tier 1 — Common"), (2, "Tier 2 — Less common"), (3, "Tier 3 — Blind spot")]:
            tier_results = [r for r in visible_results if q_lookup.get(r.id, {}).get("tier") == tier_num]
            if not tier_results:
                continue
            compliant = sum(1 for r in tier_results if r.analysis.posix_compliant)
            tier_breakdown_rows.append({
                "llm": llm,
                "tier_label": tier_label,
                "count": len(tier_results),
                "compliant": compliant,
                "rate": compliant / len(tier_results),
                "mean_output": mean([r.tokens.output for r in tier_results]),
                "mean_excess": mean([r.analysis.estimated_excess_output_tokens for r in tier_results]),
                "mean_latency": mean([r.execution.latency_ms / 1000.0 for r in tier_results]),
            })

    top_gap_results = sorted(
        all_visible,
        key=lambda r: r.analysis.estimated_excess_output_tokens,
        reverse=True,
    )[:12]
    issue8_results = [r for r in all_visible if r.analysis.issue8_refusal][:8]

    # --- All results for full scorecard ---
    all_sorted = sorted(
        all_flat,
        key=lambda r: (r.id, r.llm),
    )

    def metric_bar(
        value: float,
        max_value: float,
        label: str,
        suffix: str = "",
        value_fmt: str = ".0f",
    ) -> str:
        width = 0 if max_value <= 0 else min(100, (value / max_value) * 100)
        return (
            "<div class='metric-row'>"
            f"<div class='metric-label'>{escape(label)}</div>"
            "<div class='metric-track'>"
            f"<div class='metric-fill' style='width:{width:.1f}%'></div>"
            "</div>"
            f"<div class='metric-value'>{value:{value_fmt}}{escape(suffix)}</div>"
            "</div>"
        )

    def result_card(result: QuestionResult) -> str:
        tier = q_lookup.get(result.id, {}).get("tier", "?")
        is_error = result_is_error(result)
        is_usage_invalid = result_is_usage_invalid(result)
        status = (
            "ERROR"
            if is_error else
            ("USAGE INVALID" if is_usage_invalid else ("POSIX" if result.analysis.posix_compliant else "MISS"))
        )
        status_class = "error" if is_error else ("bad" if is_usage_invalid else ("good" if result.analysis.posix_compliant else "bad"))
        excerpt = result.response.strip()[:480]
        return f"""
        <article class="task-card">
          <div class="task-meta">
            <span class="pill model-pill">{escape(result.llm.upper())}</span>
            <span class="pill tier-pill">T{tier}</span>
            <span class="pill mode-pill {escape(status_class)}">{escape(status)}</span>
            <span class="pill failure-pill">{escape(result.tokens.usage_invalid_reason if is_usage_invalid else (result.analysis.inefficiency_mode.replace('_', ' ') if not is_error else result.response.removeprefix('[ERROR] ')))}</span>
          </div>
          <h3>{escape(result.id)} · {escape(result.question)}</h3>
          <div class="task-stats">
            <div><strong>Output</strong><span>{result.tokens.output}</span></div>
            <div><strong>Excess</strong><span>{result.analysis.estimated_excess_output_tokens}</span></div>
            <div><strong>Latency</strong><span>{format_seconds_from_ms(result.execution.latency_ms)}</span></div>
            <div><strong>Gap</strong><span>{result.analysis.minimal_answer_gap_words} words</span></div>
          </div>
          <div class="code-pair">
            <div>
              <label>Minimal POSIX answer</label>
              <pre>{escape(result.analysis.minimal_answer)}</pre>
            </div>
            <div>
              <label>Model response{' (error)' if is_error else ' excerpt'}</label>
              <pre>{escape(excerpt)}</pre>
            </div>
          </div>
        </article>
        """

    # --- Question reference rows ---
    TIER_NAMES = {1: "Common", 2: "Less common", 3: "Blind spot"}
    question_rows = []
    for q in questions:
        traps = q.get("posix_traps", [])
        trap_html = ", ".join(escape(t) for t in traps) if traps else '<span class="no-traps">None</span>'
        cmds = q.get("expected_commands", [])
        cmds_html = " ".join(f'<code>{escape(c)}</code>' for c in cmds)
        tier = q.get("tier", "?")
        tier_name = TIER_NAMES.get(tier, "?")
        question_rows.append(f"""
        <tr>
          <td class="q-id"><strong>{escape(q['id'])}</strong></td>
          <td><span class="pill tier-pill tier-{tier}">Tier {tier}</span></td>
          <td class="q-category">{escape(q.get('category', '').replace('_', ' '))}</td>
          <td class="q-text">{escape(q['question'])}</td>
          <td class="q-cmds">{cmds_html}</td>
          <td><pre class="q-answer">{escape(q.get('expected_answer', ''))}</pre></td>
          <td class="q-traps">{trap_html}</td>
        </tr>
        """)

    # --- Model sections ---
    model_sections = []
    for card in model_cards:
        inefficiency_summary = ", ".join(
            f"{name.replace('_', ' ')}={count}"
            for name, count in card["inefficiency_modes"].most_common()
        )
        error_html = ""
        if card["errors"]:
            error_items = "".join(
                f"<li><strong>{escape(r.id)}</strong>: {escape(r.response.removeprefix('[ERROR] '))} "
                f"(after {format_seconds_from_ms(r.execution.latency_ms)})</li>"
                for r in card["errors"]
            )
            error_html = f"""
            <div class="error-list">
              <span class="error-label">Errors ({card['error_count']})</span>
              <ul>{error_items}</ul>
            </div>
            """
        invalid_usage_html = ""
        if card["invalid_usage"]:
            invalid_items = "".join(
                f"<li><strong>{escape(r.id)}</strong>: {escape(r.tokens.usage_invalid_reason)} "
                f"(after {format_seconds_from_ms(r.execution.latency_ms)})</li>"
                for r in card["invalid_usage"]
            )
            invalid_usage_html = f"""
            <div class="error-list">
              <span class="error-label">Usage Invalid ({card['invalid_usage_count']})</span>
              <ul>{invalid_items}</ul>
            </div>
            """
        cost_line = ""
        if card["total_cost"] > 0:
            cost_line = f"<div><span>Total cost</span><strong>${card['total_cost']:.4f}</strong></div>"

        model_sections.append(f"""
        <section class="model-card">
          <div class="model-heading">
            <div>
              <p class="eyebrow">{escape(card["llm"].upper())}</p>
              <h2>{escape(card["model"])}</h2>
            </div>
            <div class="compliance-badge">{pct(card["compliance_rate"])}</div>
          </div>
          <p class="caption">{card["count"]}/{card["total"]} tasks visible · {card["usage_valid_count"]} usage-valid · {card["issue8_refusal_count"]} Issue 8 refusals · {card["tool_calls"]} tool calls</p>
          {metric_bar(card["mean_output"], max(max_output, 1), "Mean output tokens")}
          {metric_bar(card["mean_excess"], max(max_excess, 1), "Mean excess output")}
          {metric_bar(card["mean_latency"], max(max_latency_seconds, 1.0), "Mean latency", " s", ".2f")}
          <div class="micro-stats">
            <div><span>Mean steps</span><strong>{card["mean_steps"]:.1f}</strong></div>
            {cost_line}
            <div><span>Inefficiency modes</span><strong>{escape(inefficiency_summary or 'none')}</strong></div>
          </div>
          {error_html}
          {invalid_usage_html}
        </section>
        """)

    # --- Tier breakdown table ---
    tier_table_rows = []
    for row in tier_breakdown_rows:
        rate_color = "good" if row["rate"] >= 0.7 else ("bad" if row["rate"] < 0.5 else "muted")
        tier_table_rows.append(f"""
        <tr>
          <td>{escape(row['llm'].upper())}</td>
          <td>{escape(row['tier_label'])}</td>
          <td class="{rate_color}">{row['compliant']}/{row['count']} ({pct(row['rate'])})</td>
          <td>{row['mean_output']:.0f}</td>
          <td>{row['mean_excess']:.0f}</td>
          <td>{row['mean_latency']:.2f}s</td>
        </tr>
        """)

    issue8_section = "".join(result_card(result) for result in issue8_results) or (
        "<p class='empty-state'>No Issue 8 refusals were detected in this run.</p>"
    )
    top_gap_section = "".join(result_card(result) for result in top_gap_results)
    all_results_section = "".join(result_card(result) for result in all_sorted)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POSIX Benchmark Report</title>
  <style>
    :root {{
      --bg: #f5f0e8;
      --paper: rgba(255, 250, 241, 0.88);
      --ink: #181512;
      --muted: #655a4d;
      --accent: #bf5b2c;
      --accent-soft: #e6b89d;
      --steel: #24464e;
      --line: rgba(24, 21, 18, 0.12);
      --good: #2f6b47;
      --bad: #8a2e2e;
      --warn: #9a6b1b;
      --shadow: 0 24px 80px rgba(43, 26, 14, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 500px at 20% -10%, #f7dbc6 0%, transparent 60%),
        radial-gradient(1000px 500px at 90% -20%, #d3e6ed 0%, transparent 58%),
        linear-gradient(180deg, #fdf8f1 0%, #f0e7da 100%);
      min-height: 100vh;
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 24px 72px;
    }}
    .hero {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 34px 36px;
      display: grid;
      gap: 20px;
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.72rem;
      margin: 0;
      color: var(--muted);
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(1.9rem, 4vw, 3rem);
      line-height: 1.04;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      max-width: 70ch;
      line-height: 1.6;
      font-size: 1rem;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
    }}
    .hero-stat {{
      background: rgba(255,255,255,0.82);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
    }}
    .hero-stat span {{
      display: block;
      font-size: 0.78rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .hero-stat strong {{
      font-size: 1.2rem;
      letter-spacing: -0.01em;
    }}
    .section {{
      margin-top: 34px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 10px 40px rgba(28, 18, 10, 0.08);
      padding: 24px;
    }}
    .section-header {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-end;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .section-header h2 {{
      margin: 0;
      font-size: 1.35rem;
      letter-spacing: -0.01em;
    }}
    .section-header p {{
      margin: 6px 0 0;
      color: var(--muted);
      max-width: 72ch;
    }}
    .model-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 18px;
    }}
    .model-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.83);
      padding: 18px;
      display: grid;
      gap: 12px;
    }}
    .model-heading {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    .model-heading h2 {{
      margin: 0;
      font-size: 1.15rem;
      line-height: 1.25;
    }}
    .compliance-badge {{
      background: rgba(47, 107, 71, 0.14);
      color: var(--good);
      border: 1px solid rgba(47, 107, 71, 0.25);
      border-radius: 999px;
      padding: 6px 12px;
      font-weight: 700;
      letter-spacing: 0.02em;
      font-size: 0.85rem;
      white-space: nowrap;
    }}
    .caption {{
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.4;
    }}
    .metric-row {{
      display: grid;
      grid-template-columns: 140px 1fr auto;
      gap: 12px;
      align-items: center;
      font-size: 0.9rem;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .metric-track {{
      background: rgba(36, 70, 78, 0.12);
      border-radius: 999px;
      height: 10px;
      position: relative;
      overflow: hidden;
    }}
    .metric-fill {{
      background: linear-gradient(90deg, var(--steel), var(--accent));
      height: 100%;
      border-radius: inherit;
    }}
    .metric-value {{
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }}
    .micro-stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 10px;
      padding-top: 8px;
      border-top: 1px dashed rgba(24, 21, 18, 0.15);
    }}
    .micro-stats div {{
      display: grid;
      gap: 3px;
    }}
    .micro-stats span {{
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      color: var(--muted);
    }}
    .micro-stats strong {{
      font-size: 0.95rem;
    }}
    .error-list {{
      background: rgba(138, 46, 46, 0.06);
      border: 1px solid rgba(138, 46, 46, 0.2);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 0.86rem;
    }}
    .error-label {{
      font-weight: 700;
      color: var(--bad);
      display: block;
      margin-bottom: 6px;
    }}
    .error-list ul {{
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 4px;
      color: #5f2f2f;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      background: rgba(36, 70, 78, 0.05);
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    td.good {{ color: var(--good); font-weight: 600; }}
    td.bad {{ color: var(--bad); font-weight: 600; }}
    td.muted {{ color: var(--muted); }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 4px 9px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-weight: 700;
      white-space: nowrap;
    }}
    .model-pill {{
      background: rgba(36, 70, 78, 0.12);
      color: var(--steel);
      border-color: rgba(36, 70, 78, 0.25);
    }}
    .tier-pill {{
      background: rgba(191, 91, 44, 0.1);
      color: var(--accent);
      border-color: rgba(191, 91, 44, 0.25);
    }}
    .tier-1 {{ background: rgba(47, 107, 71, 0.08); color: var(--good); border-color: rgba(47, 107, 71, 0.2); }}
    .tier-2 {{ background: rgba(36, 70, 78, 0.08); color: var(--steel); border-color: rgba(36, 70, 78, 0.2); }}
    .tier-3 {{ background: rgba(138, 46, 46, 0.08); color: var(--bad); border-color: rgba(138, 46, 46, 0.2); }}
    .mode-pill.good {{
      background: rgba(47, 107, 71, 0.12);
      color: var(--good);
      border-color: rgba(47, 107, 71, 0.25);
    }}
    .mode-pill.bad {{
      background: rgba(138, 46, 46, 0.1);
      color: var(--bad);
      border-color: rgba(138, 46, 46, 0.25);
    }}
    .mode-pill.error {{
      background: rgba(154, 107, 27, 0.14);
      color: var(--warn);
      border-color: rgba(154, 107, 27, 0.25);
    }}
    .failure-pill {{
      background: rgba(24, 21, 18, 0.06);
      color: var(--muted);
      border-color: rgba(24, 21, 18, 0.12);
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .task-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .task-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255,255,255,0.84);
      display: grid;
      gap: 10px;
    }}
    .task-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .task-card h3 {{
      margin: 0;
      font-size: 1rem;
      line-height: 1.35;
    }}
    .task-stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }}
    .task-stats div {{
      background: rgba(36, 70, 78, 0.06);
      border: 1px solid rgba(36, 70, 78, 0.1);
      border-radius: 10px;
      padding: 8px;
      display: grid;
      gap: 3px;
    }}
    .task-stats strong {{
      font-size: 0.66rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .task-stats span {{
      font-size: 0.92rem;
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }}
    .code-pair {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }}
    .code-pair label {{
      display: block;
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.09em;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    pre {{
      margin: 0;
      background: rgba(12, 15, 19, 0.94);
      color: #f0f2f5;
      border-radius: 10px;
      padding: 10px 11px;
      overflow-x: auto;
      font-size: 0.79rem;
      line-height: 1.45;
      font-family: "JetBrains Mono", "SFMono-Regular", Menlo, monospace;
    }}
    .empty-state {{
      margin: 0;
      color: var(--muted);
    }}
    .question-table {{
      overflow-x: auto;
    }}
    .q-id, .q-category {{
      white-space: nowrap;
    }}
    .q-text {{
      min-width: 260px;
      max-width: 460px;
    }}
    .q-cmds code {{
      background: rgba(36, 70, 78, 0.12);
      border-radius: 6px;
      padding: 2px 6px;
      font-size: 0.74rem;
      margin: 0 3px 3px 0;
      display: inline-block;
    }}
    .q-answer {{
      margin: 0;
      background: rgba(12, 15, 19, 0.9);
      border-radius: 8px;
      padding: 8px;
      max-width: 340px;
      max-height: 150px;
      overflow: auto;
    }}
    .q-traps {{
      color: #5e4646;
      min-width: 160px;
      max-width: 260px;
    }}
    .no-traps {{
      color: var(--muted);
      font-style: italic;
    }}
    @media (max-width: 820px) {{
      .shell {{
        padding: 24px 12px 40px;
      }}
      .hero {{
        padding: 24px 18px;
      }}
      .section {{
        padding: 18px 14px;
      }}
      .task-stats {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .metric-row {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">POSIX Token Efficiency Benchmark</p>
        <h1>LLM efficiency scorecard for POSIX shell tasks</h1>
        <p class="subtitle">
          Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} ·
          {len(all_flat)} total responses ·
          {len(all_visible)} report-visible ·
          {len(all_usage_valid)} usage-valid ·
          {len(all_errors)} provider errors
        </p>
      </div>
      <div class="hero-grid">
        <div class="hero-stat"><span>Models</span><strong>{len(model_cards)}</strong></div>
        <div class="hero-stat"><span>Questions</span><strong>{len(questions)}</strong></div>
        <div class="hero-stat"><span>Visible Results</span><strong>{len(all_visible)}</strong></div>
        <div class="hero-stat"><span>Usage Valid</span><strong>{len(all_usage_valid)}</strong></div>
        <div class="hero-stat"><span>Provider Errors</span><strong>{len(all_errors)}</strong></div>
      </div>
    </section>

    <section class="section" id="models">
      <div class="section-header">
        <div>
          <p class="eyebrow">Model Summary</p>
          <h2>Performance and cost profile by provider</h2>
        </div>
        <p>Compliance and efficiency are measured on report-visible records. Token and cost metrics use usage-valid records.</p>
      </div>
      <div class="model-grid">
        {''.join(model_sections) if model_sections else "<p class='empty-state'>No model data available.</p>"}
      </div>
    </section>

    <section class="section" id="tier-breakdown">
      <div class="section-header">
        <div>
          <p class="eyebrow">Tier Breakdown</p>
          <h2>Compliance and verbosity by difficulty tier</h2>
        </div>
        <p>Tier mapping comes from benchmark metadata and helps show where each model struggles.</p>
      </div>
      <div class="question-table">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Tier</th>
              <th>Compliance</th>
              <th>Mean Output</th>
              <th>Mean Excess</th>
              <th>Mean Latency</th>
            </tr>
          </thead>
          <tbody>
            {''.join(tier_table_rows) if tier_table_rows else "<tr><td colspan='6'>No tier data.</td></tr>"}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section" id="top-gap">
      <div class="section-header">
        <div>
          <p class="eyebrow">Top Excess</p>
          <h2>Most over-budget responses</h2>
        </div>
        <p>Sorted by estimated excess output tokens above each task's minimal POSIX answer.</p>
      </div>
      <div class="task-grid">
        {top_gap_section if top_gap_section else "<p class='empty-state'>No results available.</p>"}
      </div>
    </section>

    <section class="section" id="issue8">
      <div class="section-header">
        <div>
          <p class="eyebrow">Issue 8 Refusals</p>
          <h2>Where models rejected valid Issue 8 tools</h2>
        </div>
        <p>Flags stale standard knowledge for readlink/realpath/timeout class failures.</p>
      </div>
      <div class="task-grid">
        {issue8_section}
      </div>
    </section>

    <section class="section" id="questions">
      <div class="section-header">
        <div>
          <p class="eyebrow">Question Reference</p>
          <h2>Canonical task sheet</h2>
        </div>
        <p>Includes tier, category, expected commands, expected answers, and trap hints.</p>
      </div>
      <div class="question-table">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Tier</th>
              <th>Category</th>
              <th>Question</th>
              <th>Expected Commands</th>
              <th>Expected Answer</th>
              <th>POSIX Traps</th>
            </tr>
          </thead>
          <tbody>
            {''.join(question_rows)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section" id="all-results">
      <div class="section-header">
        <div>
          <p class="eyebrow">Full Results</p>
          <h2>Every question, every model</h2>
        </div>
        <p>All {len(all_flat)} responses sorted by question ID. Includes errors and timeouts.</p>
      </div>
      <div class="task-grid">
        {all_results_section}
      </div>
    </section>
  </main>
</body>
</html>
"""

    report_path.write_text(html_doc)
    if retain_latest_only:
        prune_timestamped_artifacts(config.RESULTS_DIR, "report-*.html", report_path)
    print(f"  Visual report saved: {report_path}")
    return report_path


def save_comparison_report(named_summaries: list[tuple[str, dict]]) -> Path:
    """Generate a standalone HTML report comparing multiple benchmark runs."""
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = config.RESULTS_DIR / f"comparison-{ts}.html"

    # Collect all LLM names across all runs
    all_llms: list[str] = []
    for _, summary in named_summaries:
        for llm in summary.get("llms", {}):
            if llm not in all_llms:
                all_llms.append(llm)

    run_names = [name for name, _ in named_summaries]
    num_runs = len(named_summaries)

    def fmt_pct(val: float) -> str:
        return f"{val * 100:.1f}%"

    def render_na_cell() -> str:
        return "<td class='na'>N/A</td>"

    def get_numeric_metric(payload: dict, key: str) -> int | float | None:
        if key == "__billable_minus_output__":
            billable = payload.get("total_billable_tokens")
            output = payload.get("total_output_tokens")
            if isinstance(billable, (int, float)) and isinstance(output, (int, float)):
                return billable - output
            return None
        if key == "mean_latency_seconds":
            seconds = payload.get("mean_latency_seconds")
            if isinstance(seconds, (int, float)):
                return seconds
            millis = payload.get("mean_latency_ms")
            if isinstance(millis, (int, float)):
                return float(millis) / 1000.0
            return None
        value = payload.get(key)
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        return None

    def render_string_cell(payload: dict, key: str) -> str:
        value = payload.get(key)
        if value is None:
            return render_na_cell()
        return f"<td>{escape(str(value))}</td>"

    def render_numeric_cell(
        current: int | float | None,
        baseline: int | float | None,
        *,
        fmt: str,
        prefix: str = "",
        suffix: str = "",
        invert: bool = False,
        baseline_column: bool = False,
    ) -> str:
        if current is None:
            return render_na_cell()
        formatted_value = f"{prefix}{current:{fmt}}{suffix}"
        if baseline_column or baseline is None:
            return f"<td>{formatted_value}</td>"

        diff = current - baseline
        if abs(diff) < 0.001:
            badge = ""
        else:
            is_good = (diff < 0) if not invert else (diff > 0)
            color = "good" if is_good else "bad"
            sign = "+" if diff > 0 else ""
            badge = f' <span class="delta {color}">{sign}{prefix}{diff:{fmt}}{suffix}</span>'
        return f"<td>{formatted_value}{badge}</td>"

    def render_pct_cell(
        current: int | float | None,
        baseline: int | float | None,
        *,
        invert: bool,
        baseline_column: bool = False,
    ) -> str:
        if current is None:
            return render_na_cell()
        if baseline_column or baseline is None:
            return f"<td>{fmt_pct(current)}</td>"

        diff = current - baseline
        if abs(diff) < 0.001:
            badge = ""
        else:
            color = "good" if (diff > 0 if invert else diff < 0) else "bad"
            sign = "+" if diff > 0 else ""
            badge = f' <span class="delta {color}">{sign}{diff * 100:.1f}pp</span>'
        return f"<td>{fmt_pct(current)}{badge}</td>"

    # --- Per-LLM comparison tables ---
    llm_sections = []
    for llm in all_llms:
        rows_data = []
        for name, summary in named_summaries:
            data = summary.get("llms", {}).get(llm)
            if data:
                rows_data.append((name, data))

        if not rows_data:
            continue

        baseline = rows_data[0][1]

        # Header row
        header_cells = "".join(f"<th>{escape(name)}</th>" for name, _ in rows_data)

        # Metric rows
        metrics = [
            ("Model", "model", "s", "", False),
            ("Valid Results", "valid_results", "d", "", False),
            ("Total Results", "total_results", "d", "", False),
            ("Compliance Rate", "posix_compliance_rate", ".1%", "", True),
            ("Mean Output Tokens", "mean_output_tokens", ".0f", "", False),
            ("Mean Latency (s)", "mean_latency_seconds", ".2f", "", False),
            ("Mean Steps", "mean_step_count", ".1f", "", False),
            ("Total Input Tokens", "total_input_tokens", "d", "", False),
            ("Total Cached Tokens", "total_cached_tokens", "d", "", False),
            ("Total Output Tokens", "total_output_tokens", "d", "", False),
            ("Total Excess Tokens", "total_estimated_excess_output_tokens", "d", "", False),
            ("Total Billable Tokens (provider-semantic)", "total_billable_tokens", "d", "", False),
            ("Billable - Output Tokens", "__billable_minus_output__", "d", "", False),
            ("Issue 8 Refusals", "issue8_refusal_count", "d", "", False),
        ]

        metric_rows = []
        for label, key, fmt, prefix, invert in metrics:
            cells = []
            baseline_value = get_numeric_metric(baseline, key) if fmt != "s" else None
            for i, (_, data) in enumerate(rows_data):
                if fmt == "s":
                    cells.append(render_string_cell(data, key))
                elif fmt.endswith("%"):
                    current = get_numeric_metric(data, key)
                    cells.append(
                        render_pct_cell(
                            current,
                            baseline_value,
                            invert=invert,
                            baseline_column=(i == 0),
                        )
                    )
                else:
                    current = get_numeric_metric(data, key)
                    cells.append(
                        render_numeric_cell(
                            current,
                            baseline_value,
                            fmt=fmt,
                            prefix=prefix,
                            invert=invert,
                            baseline_column=(i == 0),
                        )
                    )
            metric_rows.append(f"<tr><td class='metric-name'>{escape(label)}</td>{''.join(cells)}</tr>")

        # Failure modes rows
        all_failure_modes = []
        for _, data in rows_data:
            fm = data.get("failure_modes", {}) or data.get("inefficiency_modes", {})
            for name in fm:
                if name not in all_failure_modes:
                    all_failure_modes.append(name)

        fm_rows = []
        for mode in all_failure_modes:
            cells = []
            baseline_mode_count = (
                baseline.get("failure_modes", {}) or baseline.get("inefficiency_modes", {})
            ).get(mode)
            for i, (_, data) in enumerate(rows_data):
                fm = data.get("failure_modes", {}) or data.get("inefficiency_modes", {})
                val = fm.get(mode)
                if val is None:
                    cells.append(render_na_cell())
                    continue
                cells.append(
                    render_numeric_cell(
                        val,
                        baseline_mode_count,
                        fmt="d",
                        baseline_column=(i == 0),
                    )
                )
            fm_rows.append(f"<tr><td class='metric-name'>{escape(mode.replace('_', ' '))}</td>{''.join(cells)}</tr>")

        # Error rows
        error_rows = []
        for run_name, data in rows_data:
            errs = data.get("errors", []) or []
            if not errs:
                continue
            items = []
            for err in errs:
                qid = err.get("question_id", "?")
                kind = str(err.get("kind", "error")).replace("_", " ")
                message = err.get("error", "")
                latency_ms = err.get("latency_ms")
                latency = "n/a"
                if isinstance(latency_ms, (int, float)):
                    latency = format_seconds_from_ms(latency_ms)
                items.append(
                    f"<li><strong>{escape(str(qid))}</strong> "
                    f"<span class='kind'>{escape(kind)}</span> "
                    f"<span class='msg'>{escape(str(message))}</span> "
                    f"<span class='lat'>{escape(latency)}</span></li>"
                )
            error_rows.append(
                f"<div class='error-block'><h4>{escape(run_name)} ({len(errs)})</h4><ul>{''.join(items)}</ul></div>"
            )

        llm_sections.append(f"""
        <section class='llm-section'>
          <h2>{escape(llm.upper())}</h2>
          <table class='metrics-table'>
            <thead>
              <tr><th class='metric-col'>Metric</th>{header_cells}</tr>
            </thead>
            <tbody>
              {''.join(metric_rows)}
            </tbody>
          </table>
          <h3>Failure Modes</h3>
          <table class='metrics-table'>
            <thead>
              <tr><th class='metric-col'>Mode</th>{header_cells}</tr>
            </thead>
            <tbody>
              {''.join(fm_rows) if fm_rows else f"<tr><td class='metric-name'>None</td>{''.join(render_na_cell() for _ in rows_data)}</tr>"}
            </tbody>
          </table>
          <h3>Error Details</h3>
          <div class='error-grid'>
            {''.join(error_rows) if error_rows else "<p class='no-errors'>No errors reported.</p>"}
          </div>
        </section>
        """)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POSIX Comparison Report</title>
  <style>
    :root {{
      --bg: #f7f3ec;
      --paper: #fffdf8;
      --ink: #1d1712;
      --muted: #6d6154;
      --line: rgba(29, 23, 18, 0.12);
      --good: #2f6b47;
      --bad: #8a2e2e;
      --accent: #285b7a;
      --shadow: 0 14px 40px rgba(40, 23, 12, 0.1);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #fdf8ef 0%, #f0e7d9 100%);
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }}
    .shell {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 30px 18px 54px;
    }}
    .hero {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 22px 24px;
      margin-bottom: 22px;
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(1.5rem, 3vw, 2.2rem);
      letter-spacing: -0.01em;
    }}
    .hero p {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .run-badges {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .run-badge {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 0.8rem;
      color: var(--accent);
      background: rgba(40, 91, 122, 0.08);
    }}
    .llm-section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 8px 30px rgba(40, 23, 12, 0.07);
      padding: 18px;
      margin-bottom: 18px;
    }}
    .llm-section h2 {{
      margin: 0 0 12px;
      font-size: 1.2rem;
      letter-spacing: -0.01em;
    }}
    .llm-section h3 {{
      margin: 16px 0 10px;
      font-size: 0.95rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .metrics-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 12px;
      font-size: 0.88rem;
    }}
    .metrics-table th,
    .metrics-table td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      vertical-align: top;
      text-align: left;
      font-variant-numeric: tabular-nums;
    }}
    .metrics-table th {{
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      background: rgba(40, 91, 122, 0.05);
    }}
    .metric-col {{
      width: 240px;
    }}
    .metric-name {{
      color: #3e352b;
      font-weight: 600;
      text-transform: none;
      letter-spacing: 0.01em;
    }}
    .delta {{
      display: inline-block;
      margin-left: 8px;
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 0.74rem;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .delta.good {{
      background: rgba(47, 107, 71, 0.12);
      color: var(--good);
    }}
    .delta.bad {{
      background: rgba(138, 46, 46, 0.12);
      color: var(--bad);
    }}
    .na {{
      color: var(--muted);
      font-style: italic;
    }}
    .error-grid {{
      display: grid;
      gap: 10px;
    }}
    .error-block {{
      border: 1px solid rgba(138, 46, 46, 0.25);
      border-radius: 10px;
      background: rgba(138, 46, 46, 0.05);
      padding: 10px;
    }}
    .error-block h4 {{
      margin: 0 0 8px;
      font-size: 0.86rem;
      color: var(--bad);
      letter-spacing: 0.02em;
    }}
    .error-block ul {{
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 5px;
      font-size: 0.82rem;
      color: #5c2d2d;
    }}
    .error-block .kind {{
      display: inline-block;
      margin: 0 6px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: 0.68rem;
      color: #8e5a5a;
    }}
    .error-block .lat {{
      display: inline-block;
      margin-left: 6px;
      color: #8e5a5a;
      font-size: 0.76rem;
    }}
    .no-errors {{
      margin: 0;
      color: var(--muted);
      font-size: 0.85rem;
    }}
    @media (max-width: 860px) {{
      .shell {{
        padding: 18px 10px 36px;
      }}
      .llm-section {{
        padding: 14px;
      }}
      .metrics-table {{
        display: block;
        overflow-x: auto;
      }}
      .metric-col {{
        min-width: 170px;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>Benchmark Comparison Report</h1>
      <p>Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · {num_runs} runs compared side-by-side. Deltas are relative to the first run column.</p>
      <div class="run-badges">
        {''.join(f"<span class='run-badge'>{escape(name)}</span>" for name in run_names)}
      </div>
    </section>
    {''.join(llm_sections) if llm_sections else "<p>No overlapping model data found.</p>"}
  </main>
</body>
</html>
"""

    report_path.write_text(html_doc)
    print(f"  Comparison report saved: {report_path}")
    return report_path
