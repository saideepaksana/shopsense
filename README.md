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

## Documentation

The [project report](docs/report/shopsense_report.pdf) and [report source](docs/report/shopsense_report.tex) contain the full evaluation and discussion. The [slides](docs/slides/shopsense_slides.pdf) and [slide source](docs/slides/shopsense_slides.tex) summarize the project. The [architecture overview](docs/architecture.md) is available in Markdown.

The [design guide](docs/shopsense_design.pdf) and [source](docs/shopsense_design.tex) document an earlier Phase 2 design. The [proposal](docs/proposal.pdf) and [progress report](docs/progress.pdf) provide project background.

## Local scripted evaluation

Run the 41-scenario comparison with isolated seeded databases and no model or network calls:

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

Live evaluation (2026-10-14): on 41 scripted scenarios the pipeline passed 41/41 and the baseline passed 33/41. Both measured policy-violation and unconfirmed-write rates of 0.000 and injection resistance of 1.000; the result shows a reliability difference, not a measured safety advantage. Six of the baseline's eight failed scenarios had an `invalid_output` stop after its JSON action retries; two had only reply/loop stops. The partial simulated-customer run attempted 8 of 12 personas: each system has 7 valid trials, with 4 baseline passes, 7 pipeline passes and a pipeline R1 provider-quota error. These are single-trial results. Live runs support `--max-tokens N` to stop at an invocation token budget and use exit code 3 when stopped early by quota or budget; resume with the same model and user mode. See [evaluation results](docs/evaluation.md) and the [saved reports](reports/final/).

Limitations: mock payments, English only, whole-order returns only, provider rate limits, and an LLM-simulated customer instead of real users.
