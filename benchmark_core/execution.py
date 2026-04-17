import filecmp
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from benchmark_core import config
from benchmark_core.models import CommandResult, ExecutionRecord

COMMAND_TIMEOUT_SECONDS = 30
FIXTURE_MANIFEST = config.FIXTURES_DIR / "manifest.json"

_fixture_manifest_cache: dict | None = None


def load_fixture_manifest() -> dict[str, dict]:
    """Load fixture metadata from fixtures/manifest.json.

    Returns a dict keyed by question ID (e.g. "T01") with fixture_dir,
    exec_validation_type, and exec_setup_note. Keeps benchmark_data.json
    as a frozen dataset — execution metadata lives separately.
    """
    global _fixture_manifest_cache
    if _fixture_manifest_cache is not None:
        return _fixture_manifest_cache
    if not FIXTURE_MANIFEST.exists():
        _fixture_manifest_cache = {}
        return _fixture_manifest_cache
    with open(FIXTURE_MANIFEST) as f:
        data = json.load(f)
    _fixture_manifest_cache = data.get("fixtures", {})
    return _fixture_manifest_cache


def extract_command(response: str, expected_commands: list[str]) -> str:
    """Extract a runnable shell command from LLM prose output.

    Strategy in priority order:
    1. Single short line starting with an expected utility -> return as-is
    2. Fenced code block (``` or `) -> extract contents
    3. Lines starting with $ -> strip $ prefix
    4. Lines starting with an expected utility name
    5. Fallback: return the full response stripped

    Extraction failures surface as exec_exit_code 127 (command not found)
    rather than crashing the run.
    """
    text = response.strip()

    # 1. Single short line starting with an expected utility
    if "\n" not in text and len(text) < 200:
        if any(text.startswith(cmd) for cmd in expected_commands):
            return text

    # 2. Fenced code block — filter by expected_commands to avoid executing
    #    arbitrary code (e.g., "pip install ..." in an earlier code block).
    fenced = re.findall(r"```(?:\w*)\n(.*?)```", text, re.DOTALL)
    if fenced:
        for block_raw in fenced:
            block = block_raw.strip()
            lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith("#")]
            matched = [l for l in lines if any(l.strip().startswith(cmd) for cmd in expected_commands)]
            if matched:
                return "\n".join(matched) if len(matched) > 1 else matched[0]

    # Also check single backtick inline code
    inline = re.findall(r"`([^`]+)`", text)
    for candidate in inline:
        candidate = candidate.strip()
        if any(candidate.startswith(cmd) for cmd in expected_commands):
            return candidate

    # 3. Lines starting with $ (filtered to expected commands only)
    dollar_lines = [l.lstrip("$ ").strip() for l in text.splitlines() if l.strip().startswith("$")]
    for dl in dollar_lines:
        if any(dl.startswith(cmd) for cmd in expected_commands):
            return dl

    # 4. Lines starting with an expected utility
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(cmd) for cmd in expected_commands):
            return stripped

    # 5. Fallback — returns full text; will fail as exit_code 127 if not a valid command
    return text


def setup_fixture(fixture_spec: dict) -> tuple[Path | None, str]:
    """Copy fixture files into a temp directory for isolated execution.

    Returns (temp_dir_path, skip_reason). If skip_reason is non-empty,
    execution should be skipped.
    """
    fixture_name = fixture_spec.get("fixture_dir")
    if not fixture_name:
        return None, "no fixture_dir in spec"
    if not re.match(r'^[A-Za-z0-9_-]+$', fixture_name):
        return None, f"invalid fixture_dir name: {fixture_name}"

    fixture_path = config.FIXTURES_DIR / fixture_name
    if not fixture_path.is_dir():
        return None, f"fixture directory not found: {fixture_path}"

    temp_dir = Path(tempfile.mkdtemp(prefix=f"sayance_exec_{fixture_name}_"))

    # If there's a setup/ subdir, copy its contents; otherwise copy everything
    # except expected_stdout and expected/
    setup_dir = fixture_path / "setup"
    if setup_dir.is_dir():
        shutil.copytree(setup_dir, temp_dir, symlinks=True, dirs_exist_ok=True)
    else:
        for item in fixture_path.iterdir():
            if item.name in ("expected_stdout", "expected", "setup_timestamps.sh"):
                continue
            if item.is_symlink():
                link_target = os.readlink(item)
                (temp_dir / item.name).symlink_to(link_target)
            elif item.is_dir():
                shutil.copytree(item, temp_dir / item.name, symlinks=True)
            else:
                shutil.copy2(item, temp_dir / item.name)

    # Run setup script if present (e.g., for timestamp manipulation).
    # These scripts are part of the trusted fixture corpus, not LLM output.
    setup_script = fixture_path / "setup_timestamps.sh"
    if setup_script.exists():
        proc = subprocess.run(
            ["sh", str(setup_script)],
            cwd=str(temp_dir),
            timeout=5,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, f"setup script failed (exit {proc.returncode}): {proc.stderr[:200]}"

    return temp_dir, ""


def run_command(command: str, cwd: Path, timeout: int = COMMAND_TIMEOUT_SECONDS) -> CommandResult:
    """Execute a shell command in the given working directory.

    Uses shell=True because LLM responses may include pipelines.
    Timeout enforces a 30-second ceiling — slow commands are wrong commands.
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = (time.monotonic() - start) * 1000
        return CommandResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed_ms=round(elapsed, 1),
        )
    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return CommandResult(
            exit_code=124,  # standard timeout exit code
            stdout="",
            stderr=f"TIMEOUT: command exceeded {timeout}s",
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return CommandResult(
            exit_code=127,
            stdout="",
            stderr=str(e),
            elapsed_ms=round(elapsed, 1),
        )


def validate_command_result(
    result: CommandResult, fixture_spec: dict, temp_dir: Path
) -> bool:
    """Validate command output against expected results.

    Validation types:
    - stdout: compare stdout against expected_stdout file (stripped)
    - exit_zero: command exits with code 0
    - file_state: files in temp_dir match expected/ directory
    """
    validation_type = fixture_spec.get("exec_validation_type", "exit_zero")
    fixture_path = config.FIXTURES_DIR / fixture_spec["fixture_dir"]

    if validation_type == "stdout":
        expected_file = fixture_path / "expected_stdout"
        if not expected_file.exists():
            return False
        expected = expected_file.read_text().strip()
        actual = result.stdout.strip()
        if fixture_spec.get("exec_stdout_unordered", False):
            return sorted(actual.splitlines()) == sorted(expected.splitlines())
        return actual == expected

    elif validation_type == "exit_zero":
        return result.exit_code == 0

    elif validation_type == "file_state":
        expected_dir = fixture_path / "expected"
        if not expected_dir.is_dir():
            return False
        for expected_file in expected_dir.rglob("*"):
            if expected_file.is_dir():
                continue
            rel = expected_file.relative_to(expected_dir)
            actual_file = temp_dir / rel
            if not actual_file.exists():
                return False
            if not filecmp.cmp(str(expected_file), str(actual_file), shallow=False):
                return False
        return True

    return False


def _skip_record(validation_type: str, reason: str) -> ExecutionRecord:
    """Return an ExecutionRecord for a skipped question."""
    return ExecutionRecord(
        command_extracted="",
        exec_success=False,
        exec_attempts=0,  # 0 = skipped, 1 = single attempt
        exec_exit_code=-1,
        exec_stdout="",
        exec_stderr="",
        exec_elapsed_ms=0,
        exec_validation_type=validation_type,
        exec_skipped=True,
        exec_skip_reason=reason,
    )


def execute_question(question: dict, response: str) -> ExecutionRecord:
    """Execute the command from an LLM response against the question's fixture.

    Looks up fixture metadata from fixtures/manifest.json by question ID.
    Phase 1: single-attempt execution only (no retry loop).
    """
    manifest = load_fixture_manifest()
    fixture_spec = manifest.get(question["id"])

    if not fixture_spec:
        return _skip_record("exit_zero", f"no fixture for {question['id']}")

    validation_type = fixture_spec.get("exec_validation_type", "exit_zero")

    temp_dir, skip_reason = setup_fixture(fixture_spec)
    if skip_reason:
        return _skip_record(validation_type, skip_reason)

    try:
        command = extract_command(response, question.get("expected_commands", []))
        result = run_command(command, temp_dir)
        success = validate_command_result(result, fixture_spec, temp_dir)

        return ExecutionRecord(
            command_extracted=command,
            exec_success=success,
            exec_attempts=1,
            exec_exit_code=result.exit_code,
            exec_stdout=result.stdout[:2000] + ("\n[TRUNCATED]" if len(result.stdout) > 2000 else ""),
            exec_stderr=result.stderr[:2000] + ("\n[TRUNCATED]" if len(result.stderr) > 2000 else ""),
            exec_elapsed_ms=result.elapsed_ms,
            exec_validation_type=validation_type,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
