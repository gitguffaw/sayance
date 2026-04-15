# Benchmark Evidence

This page documents the canonical benchmark results behind the numbers in the README. Raw result directories are gitignored — this curated summary provides the provenance and reproducibility details a reviewer needs.

## Baseline Comparison (30 questions, k=1)

**Run date:** 2026-03-28  
**Corpus:** 30 intent-based questions (pre-expansion to 40)  
**Mode:** Unaided (no bridge injection) vs. Bridge-Aided (Discovery Map + Syntax Lookup)

### Models Tested

| Provider | Model | Version |
|----------|-------|---------|
| Claude | claude-sonnet-4-20250514 | Baseline era |
| Codex | codex-mini-latest | Baseline era |
| Gemini | gemini-2.5-pro-preview-03-25 | Baseline era |

### POSIX Compliance

| Provider | Unaided | Bridge-Aided | Delta |
|----------|---------|-------------|-------|
| Claude | 63.3% | 76.7% | +13.4 pts |
| Codex | 58.6% | 86.7% | +28.1 pts |
| Gemini | 65.4% | 86.7% | +21.3 pts |

### Token Efficiency

| | Claude | Codex | Gemini |
|---|---|---|---|
| Output tokens (unaided) | 228 | 930 | 215 |
| Output tokens (bridge-aided) | 374 | 1,289 | 105 |
| Non-POSIX substitutions (unaided) | 6 | 9 | 7 |
| Non-POSIX substitutions (bridge-aided) | 7 | 1 | 3 |

Gemini's output tokens dropped 51% while compliance rose 21 points — the strongest efficiency gain. Codex's token increase reflects verbose tool narration, not worse answers.

### Commands Used

```bash
# Unaided baselines
python3 run_benchmark.py --llms claude --questions T01-T30
python3 run_benchmark.py --llms codex --questions T01-T30
python3 run_benchmark.py --llms gemini --max-workers 1 --delay 30 --questions T01-T30

# Bridge-Aided runs
python3 run_benchmark.py --llms claude --inject-posix --questions T01-T30
python3 run_benchmark.py --llms codex --inject-posix --questions T01-T30
python3 run_benchmark.py --llms gemini --inject-posix --max-workers 1 --delay 30 --questions T01-T30
```

## Current Corpus

The benchmark corpus has been expanded to **40 questions** covering Common, Uncommon, and Obscure POSIX utilities. The 30-question baseline above is preserved as a historical before/after reference. New baseline runs on the 40-question corpus with pinned models (`claude-opus-4-6`, `gpt-5.4`) are planned.

## Reproducing These Results

1. Clone the repo and confirm the bridge is complete:
   ```bash
   python3 run_benchmark.py --validate-bridge
   ```

2. Run an unaided baseline:
   ```bash
   python3 run_benchmark.py --llms claude --claude-model claude-opus-4-6
   ```

3. Run a bridge-aided comparison:
   ```bash
   python3 run_benchmark.py --llms claude --claude-model claude-opus-4-6 --inject-posix
   ```

4. Compare summaries in `results/summary-*.json`.

API keys for Claude, Codex, and Gemini are required. Gemini runs should use `--max-workers 1 --delay 30` to stay within quota.

## What the Benchmark Measures

- **POSIX compliance rate:** Did the LLM recommend the correct POSIX utility?
- **Non-POSIX substitutions:** How often did the LLM suggest a non-standard tool (tar, xxd, md5sum)?
- **Output tokens:** How concise was the response?
- **Issue 8 refusals:** Did the LLM incorrectly reject `readlink`, `realpath`, or `timeout` as non-POSIX?

The benchmark does not execute commands. It measures whether the LLM reaches for the right tool, not whether the generated command runs correctly. Command Verification (`--execute`) is a separate mode for that.

## Limitations

- Results are non-deterministic — LLM outputs vary between runs even with identical prompts.
- Token counts differ across providers due to different tokenizers.
- Cache state (cold vs. warm) creates significant cost differences on Anthropic.
- The 30-question baseline used pre-pinning model versions; exact reproducibility requires matching the model versions listed above.

## Update Policy

This evidence page is updated when new canonical baseline runs are performed at project milestones. It is not updated for every development run. The run date and model versions above identify exactly which results are cited in the README.
