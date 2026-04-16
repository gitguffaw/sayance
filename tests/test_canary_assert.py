"""Unit tests for scripts/canary_assert.py evaluate()."""

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_module():
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo))
    spec = importlib.util.spec_from_file_location(
        "canary_assert", repo / "scripts" / "canary_assert.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


canary_assert = _load_module()


class CanaryAssertTests(unittest.TestCase):
    def _assert_pass(self, response: str, expected: str, trap: str) -> None:
        passed, reason = canary_assert.evaluate(response, expected, trap)
        self.assertTrue(passed, msg=reason)

    def _assert_fail(self, response: str, expected: str, trap: str, *, reason_substr: str) -> None:
        passed, reason = canary_assert.evaluate(response, expected, trap)
        self.assertFalse(passed)
        self.assertIn(reason_substr, reason)

    def test_expected_present_no_trap(self):
        self._assert_pass("Use pax -w -f archive.pax ./dir", "pax", "tar")

    def test_expected_present_trap_negated_do_not_use(self):
        self._assert_pass("Use pax. DO NOT USE tar — it is not POSIX.", "pax", "tar")

    def test_expected_present_trap_negated_avoid(self):
        self._assert_pass("Use pax -w -f out.pax ./dir. Avoid tar; it is not POSIX.", "pax", "tar")

    def test_expected_present_trap_negated_instead_of(self):
        self._assert_pass("Use pax instead of tar for portable archives.", "pax", "tar")

    def test_hexdump_canary_compliant(self):
        self._assert_pass("od -A x -t x1 file. xxd is not POSIX-standard.", "od", "xxd")

    def test_expected_absent(self):
        self._assert_fail(
            "Use tar -czf archive.tar ./dir", "pax", "tar",
            reason_substr="not recommended",
        )

    def test_trap_taken_without_negation(self):
        self._assert_fail(
            "Use tar -czf archive.tar ./dir (pax also works if needed).",
            "pax",
            "tar",
            reason_substr="took the trap",
        )

    def test_ambiguous_both_fine(self):
        self._assert_fail(
            "pax and tar are both fine here",
            "pax",
            "tar",
            reason_substr="took the trap",
        )

    def test_case_insensitive_expected(self):
        self._assert_pass("Use PAX -w -f archive.pax ./dir", "pax", "tar")

    def test_case_insensitive_trap_negated(self):
        self._assert_pass("Use pax. Avoid TAR.", "pax", "tar")

    def test_word_boundary_expected_not_substring(self):
        # "paxton" should not count as a pax hit; only whole-word "pax" does.
        self._assert_fail(
            "Just use paxton instead of tar",
            "pax",
            "tar",
            reason_substr="not recommended",
        )

    def test_word_boundary_trap_not_substring(self):
        # "tarball" should not count as a trap hit; only whole-word "tar" does.
        self._assert_pass("Use pax to build a tarball-style portable archive", "pax", "tar")


if __name__ == "__main__":
    unittest.main()
