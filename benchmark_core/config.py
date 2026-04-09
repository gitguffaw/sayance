from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = SCRIPT_DIR / "benchmark_data.json"
POSIX_CORE_FILE = SCRIPT_DIR / "posix-core.md"
POSIX_TLDR_FILE = SCRIPT_DIR / "posix-tldr.json"
POSIX_UTILITIES_FILE = SCRIPT_DIR / "posix-utilities.txt"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"

RESULTS_DIR_BASE = SCRIPT_DIR / "results"
RESULTS_DIR_STEPUP = RESULTS_DIR_BASE / "stepup"
RESULTS_DIR_EXECUTE = RESULTS_DIR_BASE / "execute"
RESULTS_DIR_STEPUP_EXECUTE = RESULTS_DIR_BASE / "stepup-execute"

RESULTS_DIR = RESULTS_DIR_BASE


def set_results_dir(path: Path) -> None:
    global RESULTS_DIR
    RESULTS_DIR = path

