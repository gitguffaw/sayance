#!/usr/bin/env python3
"""Repo structural integrity checker.

Validates that source-of-truth artifacts are internally coherent
before installation. Exits nonzero on any failure.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

pass_count = 0
fail_count = 0


def passed(msg):
    global pass_count
    print(f"  PASS: {msg}")
    pass_count += 1


def failed(msg):
    global fail_count
    print(f"  FAIL: {msg}")
    fail_count += 1


# ---------------------------------------------------------------------------
# Utility extraction from Discovery Map sections
# ---------------------------------------------------------------------------

def extract_discovery_map_utilities(text):
    """Extract utility names from a Discovery Map section.

    Handles three formatting patterns:
      1. Bullet entries:  "*   name: description"
      2. Comma-separated bare lines: "cd, ls, cat, echo, ..."
      3. Comma-separated tokens before a colon: "admin, delta, ...: SCCS"
    """
    names = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bare = re.sub(r"^\*\s+", "", line)
        # Single-utility bullet: "name: description" (no commas before colon)
        m = re.match(r"^(\w+)\s*:", bare)
        if m and "," not in bare.split(":")[0]:
            names.add(m.group(1).lower())
            continue
        # Comma-separated utility list
        if "," in bare:
            before_colon = re.split(r":", bare)[0]
            tokens = [t.strip().lower() for t in before_colon.split(",") if t.strip()]
            if tokens and all(re.fullmatch(r"[a-z][a-z0-9_]{0,11}", t) for t in tokens):
                names.update(tokens)
    return names


def load_ground_truth():
    """Load the 142 utility names from posix-utilities.txt."""
    path = REPO / "posix-utilities.txt"
    lines = [l.strip().lower() for l in path.read_text().splitlines() if l.strip()]
    return set(lines), lines


# ---------------------------------------------------------------------------
# 1. Source artifact presence
# ---------------------------------------------------------------------------

def check_source_artifacts():
    print("=== Source Artifact Presence ===")
    required = [
        "posix-utilities.txt",
        "posix-core.md",
        "skill/SKILL.md",
        "skill/posix-lookup",
        "skill/posix-tldr.json",
        "install.sh",
    ]
    for rel in required:
        p = REPO / rel
        if p.exists():
            passed(f"{rel} exists")
        else:
            failed(f"{rel} missing")


# ---------------------------------------------------------------------------
# 2. JSON validity
# ---------------------------------------------------------------------------

def check_json_validity():
    print("=== JSON Validity ===")
    json_files = [
        "benchmark_data.json",
        "fixtures/manifest.json",
        "skill/posix-tldr.json",
    ]
    for rel in json_files:
        p = REPO / rel
        try:
            json.loads(p.read_text())
            passed(f"{rel} parses as valid JSON")
        except Exception as e:
            failed(f"{rel} JSON parse error: {e}")


# ---------------------------------------------------------------------------
# 3. 142-utility count consistency
# ---------------------------------------------------------------------------

def check_utility_consistency():
    print("=== 142-Utility Count Consistency ===")
    truth_set, truth_list = load_ground_truth()

    # 3a: posix-utilities.txt count
    if len(truth_list) == 142:
        passed("posix-utilities.txt has 142 utilities")
    else:
        failed(f"posix-utilities.txt has {len(truth_list)} utilities, expected 142")

    # 3b: posix-tldr.json key count
    tldr = json.loads((REPO / "skill/posix-tldr.json").read_text())
    tldr_keys = set(k.lower() for k in tldr.keys())
    if len(tldr_keys) == 142:
        passed("posix-tldr.json has 142 keys")
    else:
        failed(f"posix-tldr.json has {len(tldr_keys)} keys, expected 142")
    diff = truth_set - tldr_keys
    if diff:
        print(f"    missing from tldr: {sorted(diff)}")
    extra = tldr_keys - truth_set
    if extra:
        print(f"    extra in tldr: {sorted(extra)}")

    # 3c: posix-core.md
    core_text = (REPO / "posix-core.md").read_text()
    core_match = re.search(r"### \[CORE_TRIVIAL\].*", core_text, re.DOTALL)
    if core_match:
        core_names = extract_discovery_map_utilities(core_match.group(0))
        if core_names == truth_set:
            passed("posix-core.md contains all 142 utilities")
        else:
            missing = truth_set - core_names
            extra = core_names - truth_set
            failed(f"posix-core.md utility mismatch ({len(core_names)} found)")
            if missing:
                print(f"    missing: {sorted(missing)}")
            if extra:
                print(f"    extra: {sorted(extra)}")
    else:
        failed("posix-core.md: could not find CORE_TRIVIAL section")

    # 3d: skill/SKILL.md Discovery Map
    skill_text = (REPO / "skill/SKILL.md").read_text()
    dm_match = re.search(
        r"## Discovery Map[^\n]*\n(.*?)## Syntax Lookup", skill_text, re.DOTALL
    )
    if dm_match:
        skill_names = extract_discovery_map_utilities(dm_match.group(1))
        if skill_names == truth_set:
            passed("skill/SKILL.md Discovery Map contains all 142 utilities")
        else:
            missing = truth_set - skill_names
            extra = skill_names - truth_set
            failed(f"skill/SKILL.md Discovery Map mismatch ({len(skill_names)} found)")
            if missing:
                print(f"    missing: {sorted(missing)}")
            if extra:
                print(f"    extra: {sorted(extra)}")
    else:
        failed("skill/SKILL.md: could not find Discovery Map section")


# ---------------------------------------------------------------------------
# 4. CLI executable sanity
# ---------------------------------------------------------------------------

def check_cli_sanity():
    print("=== CLI Executable Sanity ===")
    cli = REPO / "skill/posix-lookup"

    if os.access(cli, os.X_OK):
        passed("skill/posix-lookup is executable")
    else:
        failed("skill/posix-lookup is not executable")

    try:
        result = subprocess.run(
            ["python3", str(cli), "--list"],
            capture_output=True, text=True, timeout=10, cwd=str(REPO)
        )
        lines = [l.strip().lower() for l in result.stdout.splitlines() if l.strip()]
        if len(lines) == 142:
            passed("posix-lookup --list produces 142 lines")
        else:
            failed(f"posix-lookup --list produces {len(lines)} lines, expected 142")

        truth_set, _ = load_ground_truth()
        list_set = set(lines)
        if list_set == truth_set:
            passed("posix-lookup --list matches posix-utilities.txt")
        else:
            missing = truth_set - list_set
            extra = list_set - truth_set
            failed("posix-lookup --list does not match posix-utilities.txt")
            if missing:
                print(f"    missing: {sorted(missing)}")
            if extra:
                print(f"    extra: {sorted(extra)}")
    except Exception as e:
        failed(f"posix-lookup --list failed: {e}")


# ---------------------------------------------------------------------------
# 5. Installer sanity
# ---------------------------------------------------------------------------

def check_installer_sanity():
    print("=== Installer Sanity ===")
    installer = (REPO / "install.sh").read_text()
    expected_refs = ["SKILL.md", "posix-lookup", "posix-tldr.json"]
    all_found = True
    for ref in expected_refs:
        if ref not in installer:
            failed(f"install.sh does not reference {ref}")
            all_found = False
    if all_found:
        passed("install.sh references all expected artifacts")


# ---------------------------------------------------------------------------
# 6. Fixture directory coverage
# ---------------------------------------------------------------------------

def check_fixture_coverage():
    print("=== Fixture Directory Coverage ===")
    manifest = json.loads((REPO / "fixtures/manifest.json").read_text())
    fixtures = manifest.get("fixtures", {})
    missing_dirs = []
    for qid, spec in fixtures.items():
        fixture_dir = spec.get("fixture_dir", qid)
        if not (REPO / "fixtures" / fixture_dir).is_dir():
            missing_dirs.append(fixture_dir)
    if not missing_dirs:
        passed(f"all {len(fixtures)} fixture directories present")
    else:
        failed(f"missing fixture directories: {missing_dirs}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    check_source_artifacts()
    check_json_validity()
    check_utility_consistency()
    check_cli_sanity()
    check_installer_sanity()
    check_fixture_coverage()

    print()
    total = pass_count + fail_count
    print(f"Repo integrity: {pass_count}/{total} passed.")
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
