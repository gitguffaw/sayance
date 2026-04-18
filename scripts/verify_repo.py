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
    """Load the 142 utility names from macOS-posix-utilities.txt."""
    path = REPO / "macOS-posix-utilities.txt"
    lines = [l.strip().lower() for l in path.read_text().splitlines() if l.strip()]
    return set(lines), lines


# ---------------------------------------------------------------------------
# 1. Source artifact presence
# ---------------------------------------------------------------------------

def check_source_artifacts():
    print("=== Source Artifact Presence ===")
    required = [
        "macOS-posix-utilities.txt",
        "sayance-core.md",
        "skill/SKILL.md",
        "skill/sayance-lookup",
        "skill/sayance-tldr.json",
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
        "skill/sayance-tldr.json",
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

    # 3a: macOS-posix-utilities.txt count
    if len(truth_list) == 142:
        passed("macOS-posix-utilities.txt has 142 utilities")
    else:
        failed(f"macOS-posix-utilities.txt has {len(truth_list)} utilities, expected 142")

    # 3b: sayance-tldr.json key count
    tldr = json.loads((REPO / "skill/sayance-tldr.json").read_text())
    tldr_keys = set(k.lower() for k in tldr.keys())
    if len(tldr_keys) == 142:
        passed("sayance-tldr.json has 142 keys")
    else:
        failed(f"sayance-tldr.json has {len(tldr_keys)} keys, expected 142")
    diff = truth_set - tldr_keys
    if diff:
        print(f"    missing from tldr: {sorted(diff)}")
    extra = tldr_keys - truth_set
    if extra:
        print(f"    extra in tldr: {sorted(extra)}")

    # 3c: sayance-core.md
    core_text = (REPO / "sayance-core.md").read_text()
    core_match = re.search(r"### \[CORE_TRIVIAL\].*", core_text, re.DOTALL)
    if core_match:
        core_names = extract_discovery_map_utilities(core_match.group(0))
        if core_names == truth_set:
            passed("sayance-core.md contains all 142 utilities")
        else:
            missing = truth_set - core_names
            extra = core_names - truth_set
            failed(f"sayance-core.md utility mismatch ({len(core_names)} found)")
            if missing:
                print(f"    missing: {sorted(missing)}")
            if extra:
                print(f"    extra: {sorted(extra)}")
    else:
        failed("sayance-core.md: could not find CORE_TRIVIAL section")

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
# 4. Dead tool reference drift
# ---------------------------------------------------------------------------

def check_no_dead_tool_refs():
    """Fail if dead/retired tool names appear in *active* product or runner code.

    Scope: shipped skill artifacts, source-of-truth Discovery Map, and the
    benchmark runner/providers (the previous bug site). Excluded: README.md,
    docs/*.md, CHANGELOG.md — those legitimately discuss the retired contract
    in historical/design-rationale context. "MCP" is not forbidden; the
    architecture docs explain why we *don't* use it.
    """
    print("=== Dead Tool Reference Check ===")
    forbidden = ["get_posix_syntax"]
    scan_targets = [
        REPO / "skill/SKILL.md",
        REPO / "skill/sayance-lookup",
        REPO / "skill/sayance-tldr.json",
        REPO / "sayance-core.md",
        REPO / "install.sh",
        REPO / "Makefile",
        REPO / "benchmark_core" / "runner.py",
        REPO / "benchmark_core" / "providers.py",
    ]

    findings = []
    for path in scan_targets:
        if path == Path(__file__).resolve():
            continue
        if not path.exists():
            failed(f"{path.relative_to(REPO)} missing")
            continue
        try:
            for idx, line in enumerate(path.read_text().splitlines(), start=1):
                for pattern in forbidden:
                    if pattern.lower() in line.lower():
                        findings.append((path, idx, pattern, line.strip()))
        except Exception as e:
            failed(f"unable to scan {path.relative_to(REPO)}: {e}")

    if not findings:
        passed("no dead tool references in active product/runner code")
        return

    failed("dead tool references found in active artifacts")
    for path, line_no, pattern, text in findings:
        print(f"    {path.relative_to(REPO)}:{line_no}: {pattern} ({text})")


# ---------------------------------------------------------------------------
# 5. Discovery Map text parity
# ---------------------------------------------------------------------------

def _extract_section_lines(text, start_marker, end_marker=None):
    """Return lines from start_marker through end_marker (exclusive) if given."""
    lines = text.splitlines()
    try:
        start_idx = next(i for i, line in enumerate(lines) if start_marker in line)
    except StopIteration:
        return None

    if end_marker:
        end_idx = None
        for i in range(start_idx + 1, len(lines)):
            if end_marker in lines[i]:
                end_idx = i
                break
        end_idx = end_idx if end_idx is not None else len(lines)
        return [(i + 1, line) for i, line in enumerate(lines[start_idx:end_idx], start=start_idx)]
    return [(i + 1, line) for i, line in enumerate(lines[start_idx:], start=start_idx)]


def _normalize_discovery_lines(lines_with_no):
    normalized = []
    prev_blank = False
    for line_no, line in lines_with_no:
        normalized_line = line.rstrip()
        if not normalized_line.strip():
            if prev_blank:
                continue
            normalized.append((line_no, ""))
            prev_blank = True
            continue
        prev_blank = False
        if normalized_line.startswith("*   "):
            normalized_line = normalized_line[4:]
        if normalized_line.startswith("#"):
            normalized_line = normalized_line.lower()
        normalized.append((line_no, normalized_line))
    return normalized


def check_discovery_map_text_parity():
    print("=== Discovery Map Text Parity ===")
    core_lines = _extract_section_lines(
        (REPO / "sayance-core.md").read_text(), "### [CORE_TRIVIAL]"
    )
    if core_lines is None:
        failed("could not find sayance-core.md Discovery Map start marker")
        return

    # Anchor on the same `### [CORE_TRIVIAL]` marker to skip SKILL.md's
    # wrapper "## Discovery Map" header (which sayance-core.md does not have).
    skill_lines = _extract_section_lines(
        (REPO / "skill/SKILL.md").read_text(),
        "### [CORE_TRIVIAL]",
        "## Syntax Lookup",
    )
    if skill_lines is None:
        failed("could not find skill/SKILL.md Discovery Map section")
        return

    core_norm = _normalize_discovery_lines(core_lines)
    skill_norm = _normalize_discovery_lines(skill_lines)

    # Strip trailing blank entries — sayance-core.md ends at the last bullet
    # while SKILL.md keeps a blank before the next `## Syntax Lookup` header.
    while core_norm and core_norm[-1][1] == "":
        core_norm.pop()
    while skill_norm and skill_norm[-1][1] == "":
        skill_norm.pop()

    i = 0
    j = 0
    diffs = []
    while i < len(core_norm) and j < len(skill_norm):
        core_line_no, core_line = core_norm[i]
        skill_line_no, skill_line = skill_norm[j]
        if core_line != skill_line:
            diffs.append(
                (
                    core_line_no,
                    core_line,
                    skill_line_no,
                    skill_line,
                )
            )
        i += 1
        j += 1

    if len(core_norm) > len(skill_norm):
        for core_line_no, core_line in core_norm[len(skill_norm) :]:
            diffs.append((core_line_no, core_line, None, None))
    elif len(skill_norm) > len(core_norm):
        for skill_line_no, skill_line in skill_norm[len(core_norm) :]:
            diffs.append((None, None, skill_line_no, skill_line))

    if not diffs:
        passed("Discovery Map text parity OK")
        return

    failed("Discovery Map text parity failed")
    for core_line_no, core_line, skill_line_no, skill_line in diffs[:5]:
        if core_line is not None:
            print(f"    sayance-core.md:{core_line_no}: {core_line}")
        else:
            print("    sayance-core.md:<missing>")
        if skill_line is not None:
            print(f"    SKILL.md:{skill_line_no}: {skill_line}")
        else:
            print("    SKILL.md:<missing>")


# ---------------------------------------------------------------------------
# 6. CLI executable sanity
# ---------------------------------------------------------------------------

def check_cli_sanity():
    print("=== CLI Executable Sanity ===")
    cli = REPO / "skill/sayance-lookup"

    if os.access(cli, os.X_OK):
        passed("skill/sayance-lookup is executable")
    else:
        failed("skill/sayance-lookup is not executable")

    try:
        result = subprocess.run(
            ["python3", str(cli), "--list"],
            capture_output=True, text=True, timeout=10, cwd=str(REPO)
        )
        lines = [l.strip().lower() for l in result.stdout.splitlines() if l.strip()]
        if len(lines) == 142:
            passed("sayance-lookup --list produces 142 lines")
        else:
            failed(f"sayance-lookup --list produces {len(lines)} lines, expected 142")

        truth_set, _ = load_ground_truth()
        list_set = set(lines)
        if list_set == truth_set:
            passed("sayance-lookup --list matches macOS-posix-utilities.txt")
        else:
            missing = truth_set - list_set
            extra = list_set - truth_set
            failed("sayance-lookup --list does not match macOS-posix-utilities.txt")
            if missing:
                print(f"    missing: {sorted(missing)}")
            if extra:
                print(f"    extra: {sorted(extra)}")
    except Exception as e:
        failed(f"sayance-lookup --list failed: {e}")


# ---------------------------------------------------------------------------
# 5. Installer sanity
# ---------------------------------------------------------------------------

def check_installer_sanity():
    print("=== Installer Sanity ===")
    installer = (REPO / "install.sh").read_text()
    expected_refs = ["SKILL.md", "sayance-lookup", "sayance-tldr.json"]
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
    check_no_dead_tool_refs()
    check_discovery_map_text_parity()
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
