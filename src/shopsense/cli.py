import argparse

from shopsense.config import load_settings
from shopsense.db.seed import seed
from shopsense.session import create_session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer")
    parser.add_argument("--db")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("command", nargs="?")
    args = parser.parse_args()
    settings = load_settings()
    db = args.db or settings.db_path
    if args.command == "seed":
        seed(db)
        return
    if not args.customer:
        parser.error("--customer is required in chat mode")
    session = create_session(args.customer, db_path=db, settings=settings)
    while True:
        try:
            text = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text == "/quit":
            return
        reply = session.send(text)
        print("assistant> " + reply.text)
        if args.verbose:
            print(
                f"[outcome={reply.outcome} clauses={reply.cited_clause_ids} "
                f"tool_calls={reply.tool_calls}]"
            )


if __name__ == "__main__":
    main()
