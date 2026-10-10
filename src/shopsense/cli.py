import argparse
import os
from contextlib import closing
from typing import Any

os.environ.setdefault("FASTMCP_LOG_LEVEL", "ERROR")

from shopsense import cli_commands
from shopsense.config import Settings, load_settings
from shopsense.db import repository
from shopsense.db.connection import connect
from shopsense.db.seed import seed
from shopsense.models import Reply
from shopsense.session import create_baseline_session, create_session
from shopsense.trace import render_trace


def main() -> None:
    args = _parse_args()
    settings = load_settings()
    db_path = args.db or settings.db_path
    if args.command == "seed":
        seed(db_path)
        return
    customer = _get_customer(args.customer, db_path)
    if not customer:
        print(f"Unknown customer: {args.customer}")
        raise SystemExit(2)
    session = _create_session(args.mode, args.customer, db_path, settings)
    _chat_loop(session, args, settings.llm_api_key, db_path, customer["name"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer")
    parser.add_argument("--db")
    parser.add_argument("--mode", choices=("guarded", "baseline"), default="guarded")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("command", nargs="?")
    args = parser.parse_args()
    if args.command != "seed" and not args.customer:
        parser.error("--customer is required in chat mode")
    return args


def _get_customer(customer_id: str, db_path: str) -> dict | None:
    with closing(connect(db_path)) as conn:
        return repository.get_customer(conn, customer_id)


def _create_session(mode: str, customer_id: str, db_path: str, settings: Settings) -> Any:
    if mode == "baseline":
        return create_baseline_session(customer_id, db_path, settings=settings)
    return create_session(customer_id, db_path, settings=settings)


def _chat_loop(
    session: Any, args: argparse.Namespace, api_key: str, db_path: str, customer_name: str
) -> None:
    _print_banner(args.customer, customer_name, args.mode)
    while True:
        try:
            text = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.strip() == "/quit":
            return
        try:
            if text.lstrip().startswith("/"):
                print("assistant> " + cli_commands.handle_command(text, args.customer, db_path))
                continue
            usage_before = _usage(session)
            reply = session.send(text)
            print("assistant> " + reply.text)
            if args.verbose:
                _print_trace(reply, args.mode, usage_before, session)
        except Exception as exc:
            detail = str(exc)
            if api_key:
                detail = detail.replace(api_key, "[redacted]")
            print(f"internal error: {type(exc).__name__}: {detail}")


def _print_banner(customer_id: str, customer_name: str, mode: str) -> None:
    label = "guarded" if mode == "guarded" else "baseline: no verifier, no confirmation gate"
    print(f"Logged in as {customer_id} ({customer_name}) [{label}]. Type /help.")


def _usage(session: Any) -> dict[str, int | float]:
    llm = session.deps.llm if hasattr(session, "deps") else session.llm
    return llm.usage()


def _print_trace(
    reply: Reply, mode: str, usage_before: dict, session: Any
) -> None:
    if mode == "guarded":
        print(render_trace(reply.trace))
        return
    usage = _usage(session)
    delta = {key: usage.get(key, 0) - usage_before.get(key, 0) for key in usage}
    print(
        f"[outcome={reply.outcome} tool_calls={reply.tool_calls} "
        f"llm_calls={delta['calls']} llm_ms={delta['llm_milliseconds']:.0f} "
        f"tokens={delta['prompt_tokens']}/{delta['completion_tokens']}]"
    )


if __name__ == "__main__":
    main()
