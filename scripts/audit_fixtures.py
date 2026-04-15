#!/usr/bin/env python3
"""Fixture correctness audit for POSIX benchmark.

Runs the expected command from benchmark_data.json against each fixture
(T01-T30) using the existing setup_fixture / run_command / validate_command_result
functions from benchmark_core/execution.py.

No API calls.  Pure local execution.

Usage: python3 scripts/audit_fixtures.py
"""

from __future__ import annotations

import difflib
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from benchmark_core import config  # noqa: E402
from benchmark_core.execution import (  # noqa: E402
    load_fixture_manifest,
    run_command,
    setup_fixture,
    validate_command_result,
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_questions() -> dict[str, dict]:
    """Return benchmark_data questions keyed by question ID."""
    with open(config.DATA_FILE) as f:
        data = json.load(f)
    return {q["id"]: q for q in data["questions"]}


# ---------------------------------------------------------------------------
# Command adaptation — map generic expected_answer to fixture filenames
# ---------------------------------------------------------------------------

# Static overrides: the expected_answer from benchmark_data.json uses generic
# filenames ("file.csv", "/etc/passwd").  Fixtures supply concrete files.
# Each override maps the expected command into the fixture namespace.
COMMAND_OVERRIDES: dict[str, str] = {
    "T01": "sort -t',' -k2,2 data.csv",
    "T02": "find . -name '*.conf' -mtime -1",
    "T03": "sed 's/foo/bar/g' input.txt > tmp && mv tmp input.txt",
    "T04": "cut -d: -f3 passwd",
    "T05": "sort logfile.txt | uniq | wc -l",
    "T06": "pax -w -f archive.pax src/",
    "T08": "if test -r testfile; then printf 'yes\\n'; else printf 'no\\n'; fi",
    "T09": "cp -R source/ dest/",
    "T10": "comm file_a.txt file_b.txt",
    "T11": "cmp file1 file2",
    "T14": "nohup ./script.sh",  # strip trailing & for synchronous audit
    "T15": "readlink symlink",
    "T16": "realpath file.txt",
    "T17": "env MYVAR=hello ./check_env.sh",
    "T19": "echo 'true' | at now 2>/dev/null; echo done",  # at may not be running
    "T22": "pathchk -p portable_name",
    "T23": "comm -23 file1 file2",  # fixture files are pre-sorted
    "T26": "iconv -f ISO-8859-1 -t UTF-8 file_latin1",
    "T29": "expr '(' 3 + 5 ')' '*' 2",
    "T30": "uuencode file.bin file.bin",
}


def adapt_command(qid: str, question: dict) -> str:
    """Return the runnable command for this question against its fixture."""
    if qid in COMMAND_OVERRIDES:
        return COMMAND_OVERRIDES[qid]
    raw = question.get("expected_answer", "")
    # Strip em-dash commentary
    if " — " in raw:
        raw = raw.split(" — ")[0]
    # Take first alternative before " or "
    if " or " in raw:
        raw = raw.split(" or ")[0]
    return raw.strip()


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def color(status: str) -> str:
    if status == "PASS":
        return f"{GREEN}{status}{RESET}"
    if status == "FAIL":
        return f"{RED}{status}{RESET}"
    return f"{YELLOW}{status}{RESET}"


def unified_diff(expected: str, actual: str) -> str:
    lines = list(difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile="expected", tofile="actual",
    ))
    return "".join(lines) if lines else "(identical after strip)"


# ---------------------------------------------------------------------------
# Main audit loop
# ---------------------------------------------------------------------------

def main() -> int:
    manifest = load_fixture_manifest()
    questions = load_questions()

    fixture_ids = sorted(manifest.keys(), key=lambda x: int(x[1:]))

    rows: list[dict] = []
    failures: list[dict] = []

    print(f"\nFixture Correctness Audit — {len(fixture_ids)} fixtures")
    print("=" * 100)

    for qid in fixture_ids:
        spec = manifest[qid]
        question = questions.get(qid)
        vtype = spec.get("exec_validation_type", "exit_zero")

        if not question:
            rows.append({"qid": qid, "cmd": "???", "vtype": vtype,
                         "status": "SKIP", "exit": "-", "stderr": "missing from benchmark_data"})
            print(f"  {qid:4s}  {color('SKIP')}  missing from benchmark_data")
            continue

        cmd = adapt_command(qid, question)

        # Setup fixture
        temp_dir, skip_reason = setup_fixture(spec)
        if skip_reason:
            rows.append({"qid": qid, "cmd": cmd, "vtype": vtype,
                         "status": "SKIP", "exit": "-", "stderr": skip_reason})
            print(f"  {qid:4s}  {color('SKIP')}  {skip_reason}")
            continue

        try:
            result = run_command(cmd, temp_dir)
            passed = validate_command_result(result, spec, temp_dir)
            status = "PASS" if passed else "FAIL"
            stderr_short = result.stderr.strip().replace("\n", " ")[:80]

            rows.append({"qid": qid, "cmd": cmd, "vtype": vtype,
                         "status": status, "exit": str(result.exit_code),
                         "stderr": stderr_short})

            print(f"  {qid:4s}  {color(status)}  exit={result.exit_code:<3d}  {vtype:<12s}  {cmd}")
            if stderr_short:
                print(f"        stderr: {stderr_short}")

            if not passed:
                detail = {"qid": qid, "cmd": cmd, "vtype": vtype,
                          "exit_code": result.exit_code,
                          "stdout": result.stdout, "stderr": result.stderr}

                fixture_path = config.FIXTURES_DIR / spec["fixture_dir"]

                if vtype == "stdout":
                    ef = fixture_path / "expected_stdout"
                    detail["expected"] = ef.read_text() if ef.exists() else "(no expected_stdout)"
                    detail["actual"] = result.stdout

                elif vtype == "file_state":
                    expected_dir = fixture_path / "expected"
                    if expected_dir.is_dir():
                        detail["expected_files"] = sorted(
                            str(p.relative_to(expected_dir))
                            for p in expected_dir.rglob("*") if not p.is_dir()
                        )
                        detail["actual_files"] = sorted(
                            str(p.relative_to(temp_dir))
                            for p in temp_dir.rglob("*") if not p.is_dir()
                        )

                failures.append(detail)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ---- Summary table ----
    print("\n" + "=" * 100)
    print(f"\n{'QID':4s}  {'Status':6s}  {'Exit':4s}  {'ValType':<12s}  Command")
    print("-" * 100)
    for r in rows:
        print(f"{r['qid']:4s}  {r['status']:6s}  {r['exit']:<4s}  {r['vtype']:<12s}  {r['cmd']}")

    # ---- Counts ----
    total = len(rows)
    p = sum(1 for r in rows if r["status"] == "PASS")
    f = sum(1 for r in rows if r["status"] == "FAIL")
    s = sum(1 for r in rows if r["status"] == "SKIP")
    print(f"\n  PASS: {p}/{total}   FAIL: {f}/{total}   SKIP: {s}/{total}\n")

    # ---- Failure details ----
    if failures:
        print("=" * 80)
        print("FAILURE DETAILS")
        print("=" * 80)

        for d in failures:
            print(f"\n--- {d['qid']} (exit {d['exit_code']}, {d['vtype']}) ---")
            print(f"Command: {d['cmd']}")

            if d["stderr"]:
                print(f"Stderr: {d['stderr'].strip()[:200]}")

            if d["vtype"] == "stdout":
                exp = d.get("expected", "").strip()
                act = d.get("actual", "").strip()
                print(f"\nExpected stdout:\n{exp}")
                print(f"\nActual stdout:\n{act}")
                print(f"\nDiff:\n{unified_diff(exp, act)}")

            elif d["vtype"] == "file_state":
                print(f"Expected files: {d.get('expected_files', [])}")
                print(f"Actual files: {d.get('actual_files', [])}")

            elif d["vtype"] == "exit_zero":
                print(f"Expected exit 0, got {d['exit_code']}")
                if d.get("stdout"):
                    print(f"Stdout: {d['stdout'][:300]}")

    return 1 if f > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
