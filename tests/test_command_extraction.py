import unittest

import run_benchmark as benchmark


class ExtractCommandTests(unittest.TestCase):
    def test_extract_command_returns_single_short_expected_line_as_is(self) -> None:
        response = "grep -n TODO src/app.py"

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, "grep -n TODO src/app.py")

    def test_extract_command_extracts_expected_utility_from_fenced_code_block(self) -> None:
        response = """Use `find` to locate the rotated logs:

```sh
find . -type f -name '*.log'
```"""

        extracted = benchmark.extract_command(response, ["find"])

        self.assertEqual(extracted, "find . -type f -name '*.log'")

    def test_extract_command_skips_fenced_code_block_with_non_expected_utility(self) -> None:
        response = """Install ripgrep first if it is missing:

```sh
pip install ripgrep
```"""

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, response.strip())
        self.assertNotEqual(extracted, "pip install ripgrep")

    def test_extract_command_uses_second_fenced_block_when_first_does_not_match(self) -> None:
        response = """The first snippet is setup, the second is the actual answer.

```sh
pip install ripgrep
```

```sh
grep -n TODO src/app.py
```"""

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, "grep -n TODO src/app.py")

    def test_extract_command_extracts_expected_utility_from_inline_backticks(self) -> None:
        response = "Use `grep -n TODO src/app.py` to print line numbers for each match."

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, "grep -n TODO src/app.py")

    def test_extract_command_extracts_dollar_prefixed_expected_line(self) -> None:
        response = """Run this from the repo root:
$ grep -n TODO src/app.py"""

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, "grep -n TODO src/app.py")

    def test_extract_command_finds_expected_line_buried_in_prose(self) -> None:
        response = """You can do this in one pass.

grep -n TODO src/app.py

That prints each matching line with its number."""

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, "grep -n TODO src/app.py")

    def test_extract_command_returns_full_text_when_no_expected_utility_is_found(self) -> None:
        response = "I would use Python here because there is no simple one-liner."

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, response)

    def test_extract_command_returns_all_matching_lines_from_multiline_fenced_block(self) -> None:
        response = """Use both commands:

```sh
# show TODOs
grep -n TODO src/app.py
grep -n FIXME src/app.py
```"""

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, "grep -n TODO src/app.py\ngrep -n FIXME src/app.py")

    def test_extract_command_returns_empty_string_for_empty_response(self) -> None:
        extracted = benchmark.extract_command("", ["grep"])

        self.assertEqual(extracted, "")

    def test_extract_command_returns_full_text_when_code_block_only_contains_comments(self) -> None:
        response = """```sh
# grep -n TODO src/app.py
# grep -n FIXME src/app.py
```"""

        extracted = benchmark.extract_command(response, ["grep"])

        self.assertEqual(extracted, response.strip())


class StripCliNoiseTests(unittest.TestCase):
    def test_strip_cli_noise_leaves_clean_json_unchanged(self) -> None:
        clean_json = '{\n  "session_id": "sess_123",\n  "stdout": "ok"\n}'

        stripped = benchmark.strip_cli_noise(clean_json)

        self.assertEqual(stripped, clean_json)

    def test_strip_cli_noise_strips_each_known_prefix_when_it_is_a_full_line_before_json(self) -> None:
        json_output = '{"session_id":"sess_123","stdout":"ok"}'

        for prefix in benchmark.NOISE_PREFIXES:
            with self.subTest(prefix=prefix):
                noisy_output = f"{prefix} diagnostic message\n{json_output}"

                stripped = benchmark.strip_cli_noise(noisy_output)

                self.assertEqual(stripped, json_output)

    def test_strip_cli_noise_extracts_json_when_noise_prefix_shares_the_same_line(self) -> None:
        output = 'MCP issues detected. Run /mcp list for status.{"session_id":"sess_123","stdout":"ok"}'

        stripped = benchmark.strip_cli_noise(output)

        self.assertEqual(stripped, '{"session_id":"sess_123","stdout":"ok"}')

    def test_strip_cli_noise_strips_multiple_noise_lines_before_json(self) -> None:
        output = """Loading extension: github
Registering notification handler
Executing MCP tool sayance-lookup
{"session_id":"sess_123","stdout":"ok"}"""

        stripped = benchmark.strip_cli_noise(output)

        self.assertEqual(stripped, '{"session_id":"sess_123","stdout":"ok"}')

    def test_strip_cli_noise_returns_empty_string_for_pure_noise(self) -> None:
        output = """Warning: local config missing
Loaded cached credentials from keychain
[MCP error] transient failure"""

        stripped = benchmark.strip_cli_noise(output)

        self.assertEqual(stripped, "")

    def test_strip_cli_noise_preserves_non_noise_output_while_removing_noise(self) -> None:
        output = """Scheduling MCP bridge startup
Connected to cached session
{"session_id":"sess_123","stdout":"ok"}"""

        stripped = benchmark.strip_cli_noise(output)

        self.assertEqual(stripped, 'Connected to cached session\n{"session_id":"sess_123","stdout":"ok"}')


if __name__ == "__main__":
    unittest.main()
