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
python -m shopsense.cli --customer C1
pytest
```

Confirmation accepts `yes`/`no` in any case, `y`/`n`, and trailing punctuation (for example, `Yes.`). Longer messages are re-prompted without an LLM call. Try C1 / `ORD-10001` for cancellation, C1 / `ORD-10003` for a return, and C3 / `ORD-10009` for an approved-return refund.

## Architecture and design guide

For a detailed explanation of the graph, trust boundaries, verifier rules, database model, confirmation lifecycle, and evaluation, see the [PDF design guide](docs/shopsense_design.pdf) or its [LaTeX source](docs/shopsense_design.tex). The shorter [architecture overview](docs/architecture.md) is also available in Markdown. Project notes are in [understanding](docs/understanding.md), [progress](docs/progress.pdf) and [proposal](docs/proposal.pdf).

## Local scripted evaluation

Run the 32-scenario comparison with isolated seeded databases and no model or network calls:

```bash
python scripts/evaluate.py --trials 3 --output data/evaluation.json
```

The scripted suite measures deterministic architecture behavior. Use `python scripts/live_eval.py` for provider-backed pipeline and baseline evaluation; check your provider's usage limits before running all scenarios.

Limitations: mock payments, English only, whole-order returns only, and LLM behavior must be evaluated with scripted scenarios.
