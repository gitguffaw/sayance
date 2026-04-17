import argparse
import json
from pathlib import Path

from benchmark_core import __version__
from benchmark_core import config
from benchmark_core import providers
from benchmark_core import reporting
from benchmark_core import runner


def main():
    parser = argparse.ArgumentParser(
        description="Sayance Benchmark",
    )
    parser.add_argument(
        "--version", action="version", version=f"sayance {__version__}",
    )
    parser.add_argument(
        "--llms", nargs="+", default=["claude", "codex"],
        choices=["gemini", "claude", "codex"],
        help="Which LLMs to test (default: claude and codex; add gemini explicitly when API is available)",
    )
    parser.add_argument(
        "--judge", default=None,
        choices=["gemini", "claude", "codex"],
        help="Which LLM grades responses (default: none, token-only mode)",
    )
    parser.add_argument(
        "--questions", nargs="+",
        help="Specific question IDs to run (e.g. T01 T17 T30)",
    )
    parser.add_argument(
        "--k", type=int, default=1,
        help="Number of runs per question (default: 1, use 3+ for statistics)",
    )
    parser.add_argument(
        "--seed", type=int, default=providers.DEFAULT_SHUFFLE_SEED,
        help="Seed for randomized question order (default: 20260329)",
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Seconds to pause between API calls (default: 0)",
    )
    parser.add_argument(
        "--timeout", type=int, default=providers.DEFAULT_CLI_TIMEOUT_SECONDS,
        help="Abort an external CLI call if it exceeds this many seconds (default: 120)",
    )
    parser.add_argument(
        "--claude-model",
        default=providers.PINNED_CLAUDE_MODEL,
        help=f"Claude model override for benchmark runs (default: {providers.PINNED_CLAUDE_MODEL})",
    )
    parser.add_argument(
        "--codex-model",
        default=providers.PINNED_CODEX_MODEL,
        help=f"Codex model override for benchmark runs (default: {providers.PINNED_CODEX_MODEL})",
    )
    parser.add_argument(
        "--allow-unpinned-models", action="store_true",
        help="Allow Claude/Codex runs without pinned models (must pass --*-model auto/default)",
    )
    parser.add_argument(
        "--max-workers", type=int, default=None,
        help="Max concurrent calls per provider (overrides defaults)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be run without executing",
    )
    parser.add_argument(
        "--validate-bridge", action="store_true",
        help="Validate Sayance bridge completeness (core + tldr) and exit",
    )
    parser.add_argument(
        "--no-grade", action="store_true",
        help="Skip accuracy grading, measure tokens only",
    )
    parser.add_argument(
        "--inject-posix", action="store_true",
        help="Inject POSIX Step-Up Architecture for testing",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Execute extracted commands against fixtures (Command Verification)",
    )
    parser.add_argument(
        "--results-dir",
        help="Override the run directory for this invocation (absolute path, or relative path under results/)",
    )
    parser.add_argument(
        "--label",
        help="Optional human-readable run label used in the default run directory name",
    )
    parser.add_argument(
        "--compare", nargs="+", metavar="NAME=PATH",
        help='Compare multiple runs: "Raw Baseline=results/summary-1.json" "Step-Up=results/summary-2.json"',
    )
    args = parser.parse_args()

    # --- Compare mode: generate comparison report and exit ---
    if args.compare:
        named_summaries: list[tuple[str, dict]] = []
        for entry in args.compare:
            if "=" not in entry:
                parser.error(f"--compare entries must be NAME=PATH, got: {entry}")
            name, path_str = entry.split("=", 1)
            path = Path(path_str)
            if not path.exists():
                parser.error(f"Summary file not found: {path}")
            with open(path) as f:
                named_summaries.append((name.strip(), json.load(f)))
        if len(named_summaries) < 2:
            parser.error("--compare requires at least 2 summary files")
        reporting.save_comparison_report(named_summaries)
        return

    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0")

    judge = None if args.no_grade else args.judge

    # Warn if judge is also a test subject
    if judge and judge in args.llms:
        print(f"  Warning: {judge} is both test subject and judge.")
        print(f"  Results may be unreliable due to prompt injection risk.\n")

    questions = runner.load_questions(args.questions)

    if args.validate_bridge or args.inject_posix:
        bridge_errors = runner.validate_posix_bridge(questions, require_full_coverage=True)
        if bridge_errors:
            print("  ERROR: Sayance bridge validation failed:")
            for error in bridge_errors:
                print(f"    - {error}")
            raise SystemExit(1)
        print("  Sayance bridge validation passed: core + tldr cover all 142 macOS-available utilities.")
        if args.validate_bridge:
            return

    claude_model_override = providers.normalize_model_override(args.claude_model)
    codex_model_override = providers.normalize_model_override(args.codex_model)

    if (
        "claude" in args.llms
        and claude_model_override is None
        and not args.allow_unpinned_models
    ):
        parser.error(
            "Claude model is unpinned. Use --claude-model <model-id> or pass --allow-unpinned-models."
        )
    if (
        "codex" in args.llms
        and codex_model_override is None
        and not args.allow_unpinned_models
    ):
        parser.error(
            "Codex model is unpinned. Use --codex-model <model-id> or pass --allow-unpinned-models."
        )

    requested_models: dict[str, str | None] = {
        "claude": claude_model_override if "claude" in args.llms else None,
        "codex": codex_model_override if "codex" in args.llms else None,
        "gemini": None,
    }
    requested_labels = [
        f"{llm}:{model}" for llm, model in requested_models.items() if llm in args.llms and model
    ]
    default_results_root = config.mode_results_dir(
        inject_posix=args.inject_posix,
        execute=args.execute,
    )
    run_label = args.label or config.derive_run_label(
        llms=args.llms,
        requested_models=requested_models,
        timeout_seconds=args.timeout,
        default_timeout_seconds=providers.DEFAULT_CLI_TIMEOUT_SECONDS,
    )
    config.set_results_dir(config.make_run_results_dir(default_results_root, label=run_label))
    if args.results_dir:
        custom_results_dir = Path(args.results_dir)
        if not custom_results_dir.is_absolute():
            relative_parts = [part for part in custom_results_dir.parts if part not in ("", ".")]
            if not relative_parts or relative_parts[0] != "results":
                parser.error("--results-dir relative paths must start with 'results/'")
            if ".." in relative_parts:
                parser.error("--results-dir relative paths must not contain '..'")
            custom_results_dir = config.SCRIPT_DIR.joinpath(*relative_parts)
        config.set_results_dir(custom_results_dir)
    retain_latest_artifacts = bool(args.results_dir)

    if requested_labels:
        print(f"  Requested pinned models: {', '.join(requested_labels)}")
    print(f"  Results directory: {config.RESULTS_DIR}")

    all_results = runner.run_benchmark(
        llms=args.llms,
        questions=questions,
        k=args.k,
        judge=judge,
        delay=args.delay,
        timeout_seconds=args.timeout,
        max_workers=args.max_workers,
        dry_run=args.dry_run,
        seed=args.seed,
        inject_posix=args.inject_posix,
        execute=args.execute,
        claude_model=claude_model_override,
        codex_model=codex_model_override,
    )

    if all_results:
        reporting.generate_report(all_results, questions)
        reporting.save_summary(
            all_results,
            requested_models=requested_models,
            run_metadata={
                "mode": (
                    "bridge-aided-execute" if args.inject_posix and args.execute
                    else "execute" if args.execute
                    else "bridge-aided" if args.inject_posix
                    else "unaided"
                ),
                "label": config.current_run_label(),
                "slug": config.current_run_slug(),
                "llms": args.llms,
                "requested_models": requested_models,
                "timeout_seconds": args.timeout,
                "seed": args.seed,
                "k": args.k,
                "judge": judge,
            },
            retain_latest_only=retain_latest_artifacts,
        )
        reporting.save_visual_report(
            all_results,
            questions,
            retain_latest_only=retain_latest_artifacts,
        )
