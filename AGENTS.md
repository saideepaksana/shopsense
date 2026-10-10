# Copilot instructions for ShopSense

Read SPEC.md before changing anything. Follow it literally. If SPEC.md and an existing file disagree, SPEC.md wins unless the task says otherwise.

## Scope discipline

- Do only what the current task asks. No extra features, files, CLI flags, dependencies or abstractions.
- No base classes, factories, registries or plugin systems unless SPEC.md names them.
- If something is ambiguous, choose the simplest option and mention the choice in your end-of-task summary, never in a code comment.

## Code quality

The code should read like a clean production codebase at a large engineering company: simple, low complexity, every line earns its place.

Comments and docstrings:

- Default is no comment. Names and structure explain the code.
- No comments that restate the code. No section banners such as `# ---- helpers ----`. No "Step 1 / Step 2" comments. No TODO or FIXME. No commented-out code. No emojis.
- No module docstrings. No multi-line docstrings. No Args/Returns/Raises blocks.
- At most a one-line docstring on a public class or function when its name is not enough.
- A short comment is allowed only for a non-obvious reason ("why", never "what").

Structure:

- Functions do one job, stay under about 25 lines, use early returns, nest at most 2 levels.
- Type hints on every function signature. Use pydantic models or dataclasses for structured data crossing module boundaries.
- Constants and thresholds live in `config.py`; no magic numbers in logic.
- Descriptive snake_case names. Nouns for data, verbs for functions.
- No catch-all `except Exception` except at the evaluation runner and the CLI chat-loop boundary. No silent `pass`. No `print` outside `cli.py`, `scripts/` and the evaluation `__main__.py`.
- Imports sorted, none unused.
- Never print, log or store the API key or the contents of `.env`.

Tests:

- pytest, small tests, one behavior each, `parametrize` for tables of cases, no comments inside tests.
- Never weaken or delete a test to make it pass. Fix the code. If a test contradicts SPEC.md, say so in the summary.

## Architecture rules (tests enforce these)

1. `agents/triage.py` imports and mentions no gateway; its signature is `triage_message(llm, message, prior_intent)`.
2. `agents/planner.py`, `agents/verifier.py`, `agents/responder.py` and `facts.py` never mention `WriteGateway`, `write_gateway` or `write_server`.
3. Only `agents/executor.py` uses a `WriteGateway` inside `agents/`.
4. `sqlite3` is imported only in `db/connection.py` and `db/repository.py`.
5. The planner never receives raw customer text.
6. The responder is string templates only.
7. Write tools and `repository.py` enforce data integrity only. Policy checks (status, window, ceiling, ownership, confirmation) live in the verifier.
8. Confirmation, re-verification and execution run inside the LangGraph graph (`load_pending`, `reverify`, `execute`), not in `Session`. `Session` only parses yes/no and passes it into the graph.

## Workflow

- One task at a time. Run `pytest -q` before reporting done and include the pass/fail counts.
- End every task with a short summary: files created or changed, test counts, deviations from SPEC.md.
