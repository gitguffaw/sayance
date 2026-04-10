from datetime import datetime
from pathlib import Path
import re

SCRIPT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = SCRIPT_DIR / "benchmark_data.json"
POSIX_CORE_FILE = SCRIPT_DIR / "posix-core.md"
POSIX_TLDR_FILE = SCRIPT_DIR / "posix-tldr.json"
POSIX_UTILITIES_FILE = SCRIPT_DIR / "posix-utilities.txt"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"

RESULTS_ROOT = SCRIPT_DIR / "results"
RESULTS_DIR_BASE = RESULTS_ROOT / "baseline"
RESULTS_DIR_STEPUP = RESULTS_ROOT / "stepup"
RESULTS_DIR_EXECUTE = RESULTS_ROOT / "execute"
RESULTS_DIR_STEPUP_EXECUTE = RESULTS_ROOT / "stepup-execute"

RESULTS_DIR = RESULTS_DIR_BASE


def set_results_dir(path: Path) -> None:
    global RESULTS_DIR
    RESULTS_DIR = path


def slugify_label(raw: str) -> str:
    label = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return label or "run"


def timestamp_slug(*, now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("D%Y-%m-%d-T%H-%M-%S")


def current_run_slug() -> str:
    return RESULTS_DIR.name


def current_run_label() -> str:
    match = re.fullmatch(r"(.+)-(D\d{4}-\d{2}-\d{2}-T\d{2}-\d{2}-\d{2})", RESULTS_DIR.name)
    if match:
        return match.group(1)
    return RESULTS_DIR.name


def mode_results_dir(*, inject_posix: bool, execute: bool) -> Path:
    if inject_posix and execute:
        return RESULTS_DIR_STEPUP_EXECUTE
    if execute:
        return RESULTS_DIR_EXECUTE
    if inject_posix:
        return RESULTS_DIR_STEPUP
    return RESULTS_DIR_BASE


def provider_model_label(provider: str, model: str | None) -> str | None:
    if not model:
        return None
    fragment = model
    provider_prefix = f"{provider}-"
    if fragment.startswith(provider_prefix):
        fragment = fragment[len(provider_prefix):]
    return slugify_label(f"{provider}-{fragment}")


def derive_run_label(
    *,
    llms: list[str],
    requested_models: dict[str, str | None],
    timeout_seconds: int,
    default_timeout_seconds: int,
) -> str:
    if len(llms) == 1:
        provider = llms[0]
        label = provider_model_label(provider, requested_models.get(provider)) or f"{provider}-only"
    else:
        label = "-".join(llms)
    if timeout_seconds != default_timeout_seconds:
        label = f"{label}-timeout-{timeout_seconds}"
    return slugify_label(label)


def make_run_results_dir(base_dir: Path, *, label: str, now: datetime | None = None) -> Path:
    return base_dir / f"{slugify_label(label)}-{timestamp_slug(now=now)}"
