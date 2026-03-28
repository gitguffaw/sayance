import sys
import re

with open("run_benchmark.py", "r") as f:
    code = f.read()

# 1. Add inject_posix to run_single
code = code.replace(
    "def run_single(\n    llm: str,\n    question: dict,\n    run_k: int,\n    judge: str | None,\n    delay: float,\n) -> QuestionResult:",
    "def run_single(\n    llm: str,\n    question: dict,\n    run_k: int,\n    judge: str | None,\n    delay: float,\n    inject_posix: bool = False,\n) -> QuestionResult:"
)

# 2. Add prompt injection logic in run_single
injection_logic = """    prompt = question["question"]

    if inject_posix:
        from pathlib import Path
        import json
        core_md = Path("posix-core.md").read_text()
        prompt = f"{core_md}\\n\\nTOOL INSTRUCTION: You must use the get_posix_syntax tool for any non-trivial command. Output exactly: TOOL_CALL: get_posix_syntax(command) and stop. Do not guess syntax.\\n\\nTASK:\\n{prompt}"
"""
code = code.replace('    prompt = question["question"]', injection_logic)

# 3. Add the follow-up loop in run_single
followup_logic = """
    if inject_posix and "TOOL_CALL: get_posix_syntax(" in response_text:
        import re, json
        from pathlib import Path
        match = re.search(r"TOOL_CALL:\\s*get_posix_syntax\\((.*?)\\)", response_text)
        if match:
            cmd = match.group(1).strip("'\\\"")
            try:
                tldr = json.loads(Path("posix-tldr.json").read_text())
                syntax = tldr.get(cmd, ["Utility not found in Tier 2."])
            except:
                syntax = ["Error reading posix-tldr.json"]
            
            follow_up = f"{prompt}\\n\\nAssistant: {response_text}\\n\\nTOOL_RESULT:\\n{json.dumps(syntax)}\\nNow complete the task."
            inv2 = invoke_cli(llm, follow_up)
            resp2, tok2, _, exec2 = parse_response(llm, inv2.stdout, inv2.latency_ms)
            
            response_text = f"{response_text}\\n\\n[TOOL RESULT]: {syntax}\\n\\n{resp2}"
            
            # Simple merge of tokens/execution for tracking
            tokens = TokenUsage(
                input=tokens.input + tok2.input,
                input_cached=tokens.input_cached + tok2.input_cached,
                output=tokens.output + tok2.output,
                thoughts=tokens.thoughts + tok2.thoughts,
                billable=tokens.billable + tok2.billable,
                cost_usd=(tokens.cost_usd or 0) + (tok2.cost_usd or 0) if tokens.cost_usd else None,
                cost_source=tokens.cost_source,
                raw={"run1": tokens.raw, "run2": tok2.raw}
            )
            
            # Explicitly log the tool call success
            by_type = execution.tool_calls_by_type.copy()
            by_type["get_posix_syntax"] = by_type.get("get_posix_syntax", 0) + 1
            
            execution = ExecutionMetrics(
                latency_ms=execution.latency_ms + exec2.latency_ms,
                step_count=execution.step_count + exec2.step_count + 1,
                tool_call_count=execution.tool_call_count + exec2.tool_call_count + 1,
                tool_calls_by_type=by_type
            )
"""
code = code.replace(
    "    analysis = analyze_response(question, response_text, tokens, llm, execution)",
    followup_logic + "\n    analysis = analyze_response(question, response_text, tokens, llm, execution)"
)

# 4. Update run_provider_batch signature
code = code.replace(
    "def run_provider_batch(\n    llm: str,\n    questions: list[dict],\n    k: int,\n    judge: str | None,\n    delay: float,\n    max_workers: int | None,\n) -> list[QuestionResult]:",
    "def run_provider_batch(\n    llm: str,\n    questions: list[dict],\n    k: int,\n    judge: str | None,\n    delay: float,\n    max_workers: int | None,\n    inject_posix: bool = False,\n) -> list[QuestionResult]:"
)
code = code.replace(
    "future = pool.submit(run_single, llm, q, run_idx, judge, delay)",
    "future = pool.submit(run_single, llm, q, run_idx, judge, delay, inject_posix)"
)

# 5. Update run_benchmark signature
code = code.replace(
    "def run_benchmark(\n    llms: list[str],\n    questions: list[dict],\n    k: int,\n    judge: str | None,\n    delay: float,\n    max_workers: int | None,\n    dry_run: bool,\n) -> dict[str, list[QuestionResult]]:",
    "def run_benchmark(\n    llms: list[str],\n    questions: list[dict],\n    k: int,\n    judge: str | None,\n    delay: float,\n    max_workers: int | None,\n    dry_run: bool,\n    inject_posix: bool = False,\n) -> dict[str, list[QuestionResult]]:"
)
code = code.replace(
    "run_provider_batch, llm, questions, k, judge, delay, max_workers,",
    "run_provider_batch, llm, questions, k, judge, delay, max_workers, inject_posix,"
)

# 6. Update argparse and main
code = code.replace(
    "parser.add_argument(\n        \"--no-grade\", action=\"store_true\",\n        help=\"Skip accuracy grading, measure tokens only\",\n    )",
    "parser.add_argument(\n        \"--no-grade\", action=\"store_true\",\n        help=\"Skip accuracy grading, measure tokens only\",\n    )\n    parser.add_argument(\n        \"--inject-posix\", action=\"store_true\",\n        help=\"Inject POSIX Step-Up Architecture for testing\",\n    )"
)
code = code.replace(
    "dry_run=args.dry_run,\n    )",
    "dry_run=args.dry_run,\n        inject_posix=args.inject_posix,\n    )"
)

with open("run_benchmark.py", "w") as f:
    f.write(code)

print("Patch applied.")
