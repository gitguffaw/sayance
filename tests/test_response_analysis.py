import json
import shlex
import unittest

import run_benchmark as benchmark
from run_benchmark import (
    ExecutionMetrics,
    TokenUsage,
    analyze_response,
    detect_issue8_refusal,
)


def make_tokens(*, output: int) -> TokenUsage:
    return TokenUsage(
        input=0,
        input_cached=0,
        output=output,
        thoughts=0,
        billable=output,
        raw={},
    )


def make_execution(
    *,
    step_count: int = 1,
    tool_call_count: int = 0,
) -> ExecutionMetrics:
    return ExecutionMetrics(
        latency_ms=1,
        step_count=step_count,
        tool_call_count=tool_call_count,
        tool_calls_by_type={},
    )


class ResponseAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(benchmark.DATA_FILE.read_text())
        cls.questions = {
            question["id"]: question
            for question in payload["questions"]
            if question["id"] in {"T03", "T06", "T15", "T25", "T29"}
        }

    def analyze(
        self,
        question_id: str,
        response: str,
        *,
        output: int = 10,
        llm: str = "claude",
        execution: ExecutionMetrics | None = None,
    ):
        return analyze_response(
            self.questions[question_id],
            response,
            make_tokens(output=output),
            llm,
            execution or make_execution(),
        )

    def test_analyze_response_marks_expected_posix_command_compliant(self) -> None:
        question = self.questions["T03"]
        response = (
            "Use sed s///g with no -i flag; do redirect and mv: "
            "sed 's/foo/bar/g' file > tmp && mv tmp file"
        )

        analysis = self.analyze("T03", response, output=24)

        self.assertTrue(analysis.posix_compliant)
        self.assertEqual(analysis.expected_command_hits, ["sed"])
        self.assertEqual(analysis.trap_hits, [])
        self.assertEqual(analysis.missing_required_concepts, [])
        self.assertEqual(
            analysis.minimal_shell_token_count,
            len(shlex.split(question["expected_answer"])),
        )

    def test_analyze_response_records_known_trap_hits(self) -> None:
        cases = [
            (
                "T06",
                "Use tar -cf archive.tar directory/",
                benchmark.TRAP_PATTERNS_BY_ID["T06"][0].pattern,
            ),
            (
                "T03",
                "Use sed -i 's/foo/bar/g' file",
                benchmark.TRAP_PATTERNS_BY_ID["T03"][0].pattern,
            ),
            (
                "T25",
                "Use md5sum file",
                benchmark.TRAP_PATTERNS_BY_ID["T25"][0].pattern,
            ),
            (
                "T29",
                "Use let result=(3 + 5) * 2",
                benchmark.TRAP_PATTERNS_BY_ID["T29"][0].pattern,
            ),
        ]

        for question_id, response, expected_pattern in cases:
            with self.subTest(question_id=question_id):
                analysis = self.analyze(question_id, response, output=18)

                self.assertIn(expected_pattern, analysis.trap_hits)
                self.assertFalse(analysis.posix_compliant)
                self.assertEqual(analysis.inefficiency_mode, "non_posix_substitution")

    def test_analyze_response_tracks_missing_required_concepts(self) -> None:
        analysis = self.analyze("T06", "pax -w -f archive.pax directory/", output=8)

        self.assertEqual(analysis.expected_command_hits, ["pax"])
        self.assertEqual(analysis.missing_required_concepts, ["not tar"])

    def test_analyze_response_ignores_warning_only_trap_mentions(self) -> None:
        cases = [
            (
                "T03",
                (
                    "Use sed s///g with no -i flag and redirect and mv: "
                    "sed 's/foo/bar/g' file > tmp && mv tmp file. "
                    "Do not use sed -i because it is not POSIX."
                ),
                [],
                [],
                ["sed"],
            ),
            (
                "T06",
                "Use pax -w -f archive.pax directory/. Avoid tar because it is not POSIX.",
                [],
                [],
                ["pax"],
            ),
            (
                "T25",
                "Use cksum file. md5sum and sha256sum are not POSIX utilities.",
                [],
                [],
                ["cksum"],
            ),
            (
                "T29",
                "$(( (3 + 5) * 2 )) is POSIX sh arithmetic. Avoid let because it is a bashism.",
                ["quoting"],
                [],
                ["$(( ))"],
            ),
        ]

        for question_id, response, expected_missing, forbidden_missing, expected_hits in cases:
            with self.subTest(question_id=question_id):
                analysis = self.analyze(question_id, response, output=24)

                self.assertTrue(analysis.posix_compliant)
                self.assertEqual(analysis.trap_hits, [])
                for concept in expected_missing:
                    self.assertIn(concept, analysis.missing_required_concepts)
                for concept in forbidden_missing:
                    self.assertNotIn(concept, analysis.missing_required_concepts)
                for hit in expected_hits:
                    self.assertIn(hit, analysis.expected_command_hits)

    def test_analyze_response_accepts_t29_posix_arithmetic_without_expr(self) -> None:
        response = (
            "$(( (3 + 5) * 2 )) is POSIX sh arithmetic. "
            "Do not use let because it is a bashism."
        )

        analysis = self.analyze("T29", response, output=16)

        self.assertTrue(analysis.posix_compliant)
        self.assertIn("$(( ))", analysis.expected_command_hits)
        self.assertNotIn("expr or $(())", analysis.missing_required_concepts)
        self.assertNotIn("no let", analysis.missing_required_concepts)

    def test_analyze_response_marks_issue8_refusal(self) -> None:
        response = (
            "There is no dedicated POSIX utility for this. "
            "readlink is not POSIX-compliant, so use ls -l symlink."
        )

        analysis = self.analyze("T15", response, output=28)

        self.assertTrue(analysis.issue8_refusal)
        self.assertFalse(analysis.posix_compliant)
        self.assertEqual(analysis.inefficiency_mode, "issue8_stale_knowledge")

    def test_analyze_response_marks_minimal_responses(self) -> None:
        analysis = self.analyze("T06", "pax -w -f archive.pax directory/", output=8)

        self.assertEqual(analysis.inefficiency_mode, "minimal_or_near_minimal")

    def test_analyze_response_marks_verbose_responses(self) -> None:
        response = " ".join(
            ["Use pax -w -f archive.pax directory/."] +
            ["This remains portable across Unix systems."] * 40
        )

        analysis = self.analyze("T06", response, output=200)

        self.assertEqual(analysis.expected_command_hits, ["pax"])
        self.assertEqual(analysis.trap_hits, [])
        self.assertEqual(analysis.inefficiency_mode, "over_explaining")

    def test_analyze_response_marks_workarounds_without_expected_commands(self) -> None:
        response = "Use a shell loop to concatenate files into a single stream."

        analysis = self.analyze("T06", response, output=20)

        self.assertEqual(analysis.expected_command_hits, [])
        self.assertEqual(analysis.inefficiency_mode, "workaround_instead_of_native_utility")

    def test_analyze_response_calculates_verbosity_ratio(self) -> None:
        analysis = self.analyze(
            "T06",
            "pax -w -f archive.pax directory/ now",
            output=9,
        )

        self.assertEqual(analysis.minimal_word_count, 5)
        self.assertEqual(analysis.response_word_count, 6)
        self.assertEqual(analysis.minimal_answer_gap_words, 1)
        self.assertEqual(analysis.verbosity_ratio, 1.2)


class DetectIssue8RefusalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(benchmark.DATA_FILE.read_text())
        cls.question = next(
            question for question in payload["questions"] if question["id"] == "T15"
        )

    def test_detect_issue8_refusal_matches_dedicated_utility_claim(self) -> None:
        response = "there is no dedicated posix utility for this"

        self.assertTrue(detect_issue8_refusal(self.question, response))

    def test_detect_issue8_refusal_matches_current_non_posix_patterns(self) -> None:
        response = "readlink is not posix-compliant, so use ls -l instead"

        self.assertTrue(detect_issue8_refusal(self.question, response))

    def test_detect_issue8_refusal_ignores_normal_posix_mentions(self) -> None:
        response = "readlink is posix issue 8, so use readlink symlink"

        self.assertFalse(detect_issue8_refusal(self.question, response))

    def test_detect_issue8_refusal_ignores_posix_in_command_explanations(self) -> None:
        response = "use ls -l symlink; posix issue 8 also added readlink"

        self.assertFalse(detect_issue8_refusal(self.question, response))


if __name__ == "__main__":
    unittest.main()
