from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

SCRIPT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = SCRIPT_DIR / "benchmark_data.json"
SAYANCE_CORE_FILE = SCRIPT_DIR / "sayance-core.md"
SAYANCE_TLDR_FILE = SCRIPT_DIR / "skill" / "sayance-tldr.json"
POSIX_UTILITIES_FILE = SCRIPT_DIR / "macOS-posix-utilities.txt"
POSIX_SKILL_FILE = SCRIPT_DIR / "skill" / "SKILL.md"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
FIXTURES_MANIFEST_FILE = FIXTURES_DIR / "manifest.json"

BENCHMARK_SPEC = "POSIX.1-2024 (Issue 8)"
SPEC_UTILITIES_COUNT = 155
PROMPT_TEMPLATE_VERSION = "1"
PROVENANCE_BLOCK_KEY = "provenance"
RUN_PROVENANCE_FIELDS = (
    "benchmark_data_sha256",
    "benchmark_meta_version",
    "benchmark_meta_date",
    "benchmark_question_count",
    "git_commit",
    "prompt_template_version",
    "posix_core_sha256",
    "posix_tldr_sha256",
    "fixtures_manifest_sha256",
)
RESULT_PROVENANCE_FIELDS = (
    "question_snapshot",
    "question_sha256",
    "benchmark_data_sha256",
    "effective_prompt_sha256",
    "prompt_template_version",
)
CACHE_PROVENANCE_FIELDS = (
    "benchmark_data_sha256",
    "question_sha256",
    "prompt_template_version",
    "effective_prompt_sha256",
)

# Result directories map to benchmark modes:
#   unaided/              → Unaided (no bridge)
#   bridge-aided/         → Bridge-Aided (bridge injected)
#   execute/              → Command Verification (commands run against fixtures)
#   bridge-aided-execute/ → Bridge-Aided Verification (bridge + execution)
RESULTS_ROOT = SCRIPT_DIR / "results"
RESULTS_DIR_BASE = RESULTS_ROOT / "unaided"
RESULTS_DIR_BRIDGE_AIDED = RESULTS_ROOT / "bridge-aided"
RESULTS_DIR_EXECUTE = RESULTS_ROOT / "execute"
RESULTS_DIR_BRIDGE_AIDED_EXECUTE = RESULTS_ROOT / "bridge-aided-execute"

RESULTS_DIR = RESULTS_DIR_BASE

_benchmark_payload_cache: dict | None = None


def set_results_dir(path: Path) -> None:
    global RESULTS_DIR
    RESULTS_DIR = path


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_git_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return proc.stdout.strip() or None


def load_benchmark_payload() -> dict:
    global _benchmark_payload_cache
    if _benchmark_payload_cache is None:
        _benchmark_payload_cache = json.loads(DATA_FILE.read_text())
    return _benchmark_payload_cache


def bridge_utilities_count() -> int:
    return sum(
        1
        for line in POSIX_UTILITIES_FILE.read_text().splitlines()
        if line.strip()
    )


def default_run_provenance() -> dict[str, str | int | None]:
    payload = load_benchmark_payload()
    meta = payload.get("meta", {})
    questions = payload.get("questions", [])
    return {
        "benchmark_data_sha256": sha256_file(DATA_FILE),
        "benchmark_meta_version": meta.get("version"),
        "benchmark_meta_date": meta.get("date"),
        "benchmark_question_count": len(questions),
        "git_commit": current_git_commit(),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "posix_core_sha256": sha256_file(SAYANCE_CORE_FILE),
        "posix_tldr_sha256": sha256_file(SAYANCE_TLDR_FILE),
        "fixtures_manifest_sha256": sha256_file(FIXTURES_MANIFEST_FILE),
    }


def enrich_run_metadata(run_metadata: dict | None = None) -> dict:
    normalized = dict(run_metadata or {})
    provenance = default_run_provenance()

    nested = normalized.get(PROVENANCE_BLOCK_KEY)
    if isinstance(nested, dict):
        provenance.update({key: value for key, value in nested.items() if value is not None})

    for key in RUN_PROVENANCE_FIELDS:
        value = normalized.pop(key, None)
        if value is not None:
            provenance[key] = value

    normalized[PROVENANCE_BLOCK_KEY] = provenance
    return normalized


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
        return RESULTS_DIR_BRIDGE_AIDED_EXECUTE
    if execute:
        return RESULTS_DIR_EXECUTE
    if inject_posix:
        return RESULTS_DIR_BRIDGE_AIDED
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
