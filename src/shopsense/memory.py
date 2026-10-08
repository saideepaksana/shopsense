from contextlib import closing

from shopsense.db import repository
from shopsense.db.connection import connect


def record_outcome(db_path: str, customer_id: str, intent, outcome: str) -> None:
    with closing(connect(db_path)) as conn:
        old = repository.get_memory(conn, customer_id)
        repository.set_memory(conn, customer_id, "last_intent", intent.intent.value)
        repository.set_memory(conn, customer_id, "last_outcome", outcome)
        repository.set_memory(
            conn,
            customer_id,
            "interaction_count",
            str(int(old.get("interaction_count", "0")) + 1),
        )
        if intent.order_id:
            repository.set_memory(conn, customer_id, "last_order_id", intent.order_id)


def increment(db_path: str, customer_id: str, key: str) -> None:
    with closing(connect(db_path)) as conn:
        old = repository.get_memory(conn, customer_id)
        value = int(old.get(key, "0")) + 1
        repository.set_memory(conn, customer_id, key, str(value))
