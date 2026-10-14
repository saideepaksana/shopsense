# ShopSense

ShopSense is a safety-oriented customer-care assistant for a mock online store. It can look up order status, cancel eligible orders, and process eligible return refunds. The design separates untrusted-message triage from database-writing execution.

```text
customer message -> triage -> facts -> policy retrieval -> plan -> verify -> confirmation -> execute -> audit
```

## Setup

```bash
python -m venv .venv
pip install -e ".[dev]"
cp .env.example .env
python -m shopsense.cli seed
python -m shopsense.cli --customer C1 --verbose
pytest
```

Confirmation accepts `yes`/`no` in any case, `y`/`n`, and trailing punctuation (for example, `Yes.`). Longer messages are re-prompted without an LLM call. Try C1 / `ORD-10001` for cancellation, C1 / `ORD-10003` for a return, and C3 / `ORD-10009` for an approved-return refund.

The chat CLI supports `--mode guarded` (default) and `--mode baseline`; add `--verbose` to show per-turn trace or usage details. For example, `python -m shopsense.cli --customer C1 --mode baseline --verbose` starts a verbose baseline session. In chat, `/orders` lists the signed-in customer's orders, `/db ORD-10001` displays an owned order's stored details, and `/audit` shows recent audit events for that customer. `/help` lists the available slash commands. See the [terminal demo](docs/demo.md) for a viva walkthrough.

## Architecture and design guide

For a detailed explanation of the graph, trust boundaries, verifier rules, database model, confirmation lifecycle, and evaluation, see the [PDF design guide](docs/shopsense_design.pdf) or its [LaTeX source](docs/shopsense_design.tex). The shorter [architecture overview](docs/architecture.md) is also available in Markdown. Project notes are in [understanding](docs/understanding.md), [progress](docs/progress.pdf) and [proposal](docs/proposal.pdf).

## Local scripted evaluation

Run the 32-scenario comparison with isolated seeded databases and no model or network calls:

```bash
python scripts/evaluate.py --trials 3 --output data/evaluation.json
```

The offline scripted suite measures deterministic architecture behavior; it hard-codes baseline actions and is not an LLM head-to-head. Provider-backed evaluation uses the same model for the pipeline and baseline, with scripted customer messages by default and 12 LLM-played personas available with `--user simulated`. Check provider limits and pricing before a large run; use `--only` for a small subset and `--resume` to continue a saved report.

```bash
python scripts/live_eval.py --list
python scripts/live_eval.py --system pipeline --only N1,R7,A7,I6 --trials 1
python scripts/live_eval.py --system both --trials 1
python scripts/live_eval.py --user simulated --system pipeline --only N1,R7,I6 --trials 1
```

Live evaluation (2026-10-10): the pipeline passed 41/41 valid scripted trials with no policy violations; the baseline had only 2/41 valid trials because 39 hit provider quota, so the comparison is inconclusive. Live runs support `--max-tokens N` to stop at an invocation token budget and use exit code 3 when stopped early by quota or budget; resume with the same model and user mode. See [evaluation results](docs/evaluation.md) and the [saved reports](reports/final/).

Limitations: mock payments, English only, whole-order returns only, provider rate limits, and an LLM-simulated customer instead of real users.
