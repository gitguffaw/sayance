#!/usr/bin/env python3
"""Canary assertion: require word-boundary hit on expected utility AND no
non-negated mention of the trap utility.

Reads the provider response (JSON or plain text, any wrapper) from stdin
and exits 0 on PASS, 1 on FAIL. One-line reason is printed to stderr.

Reuses benchmark_core.providers._trap_match_is_negated so phrases like
"Use pax. Avoid tar." count as a correct answer instead of a trap hit.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from benchmark_core.providers import _trap_match_is_negated  # noqa: E402


def evaluate(response: str, expected: str, trap: str) -> tuple[bool, str]:
    response_lower = response.lower()
    expected_lower = expected.lower()
    trap_lower = trap.lower()

    expected_re = re.compile(rf"\b{re.escape(expected_lower)}\b")
    if not expected_re.search(response_lower):
        return False, f"expected utility '{expected}' not recommended"

    trap_re = re.compile(rf"\b{re.escape(trap_lower)}\b")
    for match in trap_re.finditer(response_lower):
        if _trap_match_is_negated(response_lower, match):
            continue
        return False, f"took the trap '{trap}' without negating it"

    return True, f"recommended '{expected}' and did not take the trap '{trap}'"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True, help="POSIX utility the model should recommend (e.g. pax)")
    parser.add_argument("--trap", required=True, help="Non-POSIX / wrong utility that should not appear un-negated (e.g. tar)")
    args = parser.parse_args()

    response = sys.stdin.read()
    passed, reason = evaluate(response, args.expected, args.trap)
    print(f"{'PASS' if passed else 'FAIL'}: {reason}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
