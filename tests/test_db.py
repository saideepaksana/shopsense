from shopsense.db import repository
from shopsense.db.connection import connect


def test_seed_counts_and_bundle(db_path):
    with connect(db_path) as conn:
        assert conn.execute("select count(*) from customers").fetchone()[0] == 6
        assert conn.execute("select count(*) from products").fetchone()[0] == 9
        assert conn.execute("select count(*) from orders").fetchone()[0] == 17
        order = repository.get_order_bundle(conn, "ORD-10009")
        assert order["returns"][0]["id"] == "RET-9001"
        assert repository.get_order_bundle(conn, "ORD-10010")["refunds"][0]["kind"] == "goodwill"
        assert repository.get_order_bundle(conn, "ORD-10013")["refunds"][0]["amount_minor"] == 79900


def test_write_integrity_and_idempotency(db_path):
    with connect(db_path) as conn:
        first = repository.cancel_order(conn, "ORD-10001", "key-1")
        replay = repository.cancel_order(conn, "ORD-10001", "key-1")
        assert first["ok"] and replay["replayed"] is True
        assert repository.cancel_order(conn, "ORD-10001", "key-2")["error"] == "invalid_state"


def test_full_refund_updates_payment_and_order(db_path):
    with connect(db_path) as conn:
        result = repository.issue_refund(conn, "ORD-10009", "RET-9001", 349900, "full-refund")
        assert result["ok"]
        assert (
            conn.execute("select status from payments where order_id='ORD-10009'").fetchone()[0]
            == "refunded"
        )
        assert (
            conn.execute("select status from orders where id='ORD-10009'").fetchone()[0]
            == "returned"
        )


def test_partial_refund_updates_payment(db_path):
    with connect(db_path) as conn:
        result = repository.issue_refund(conn, "ORD-10009", "RET-9001", 100, "partial-refund")
        assert result["ok"]
        assert (
            conn.execute("select status from payments where order_id='ORD-10009'").fetchone()[0]
            == "partially_refunded"
        )
        assert (
            repository.issue_refund(conn, "ORD-10009", "RET-9002", 100, "key-2")["error"]
            == "return_not_found"
        )
        assert (
            repository.issue_refund(conn, "ORD-10009", "RET-9001", 400000, "key-3")["error"]
            == "exceeds_refundable"
        )
