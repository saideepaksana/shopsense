# Evaluation

## Benchmark setup

`scripts/evaluate.py` compares the guarded pipeline with the single-agent baseline on 32 scripted scenarios. They cover normal requests, ambiguity, refusals, authorization, and prompt injection. Each variant and trial gets a fresh seeded SQLite database.

The same scenario request and proposed action profile are used to exercise both designs. The guarded path checks plans with V0-V10 and requests a separate confirmation turn before a valid write. The baseline loop has the same MCP read/write tools and policy text, but does not get a code-enforced verifier or confirmation gate. These baseline actions are deliberately scripted to exercise the architectural difference; this is not an LLM-generated head-to-head experiment.

Return scenarios represent the generated return ID differently at each interface: the guarded planner must use the `$return_id` placeholder so the executor can pass the ID created by the first action to the refund action; the baseline calls tools directly and uses the known seeded ID returned by its scripted tool sequence. An earlier shared fixture used the baseline's concrete ID in guarded plans, causing two valid return scenarios to be rejected by verifier rule V10. The fixtures were separated and a regression test now checks the distinction.

## Metrics

| Metric | Definition |
|---|---|
| Task success | Final order status, return count, and refund count match that scenario's expected state. |
| Policy-violation rate | Rate of trials that make a database mutation different from the expected scenario result. |
| Injection resistance | Fraction of injection scenarios where the database remains unchanged. |
| pass^k | Fraction of scenarios that succeed on all `k` repeated runs. |
| Tool-call efficiency | Mean gateway calls for successful scenarios. |

## Local run

Run it without a model provider or network calls:

```bash
python scripts/evaluate.py --trials 3 --output reports/phase1-scripted-evaluation.json
```

The generated report from this Phase 2 run is [phase1-scripted-evaluation.json](../reports/phase1-scripted-evaluation.json). Current results:

| Metric | Guarded pipeline | Single-agent baseline |
|---|---:|---:|
| Task success | 100% | 46.9% |
| Policy-violation rate | 0% | 53.1% |
| Injection resistance | 100% | 0% |
| pass^3 | 100% | 46.9% |
| Mean tool calls on successful cases | 2.22 | 0.73 |

## How to read these results

The results show the current deterministic verifier and confirmation boundary behave as designed for these scripted plans. The baseline profile directly attempts the scripted actions, including actions disallowed by policy. Its lower tool-call average is partly because it fails more action scenarios and uses fewer tools; fewer calls do not indicate better efficiency when tasks fail.

Each repeated trial uses the same scripted inputs, so the benchmark does not measure natural LLM variability. In this setup, pass^3 repeats the same deterministic outcome and is expected to track task success. The suite also does not evaluate free-form response quality or whether triage correctly interprets arbitrary natural language. Treat the numbers as software regression results, not as research evidence that the architecture improves live-model reliability.

For a provider-backed smoke run, configure an OpenAI-compatible endpoint in `.env` and run `python scripts/live_smoke.py`. A Groq-backed run on 2026-10-08 completed all six scenario state assertions. The script uses fresh temporary SQLite databases and removes them after each conversation. This smoke run demonstrates basic provider integration; it is not a repeated-trial benchmark. Its assertions focus on final database state, so inspect conversation outcomes as well when interpreting a pass. The live results are not included in the deterministic offline metrics above.
