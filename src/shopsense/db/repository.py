from shopsense.clock import today

ORDER_ITEMS_QUERY = """
    SELECT oi.id, oi.product_id, p.name, p.category, p.returnable,
           oi.qty, oi.unit_price_minor
    FROM order_items oi
    JOIN products p ON p.id = oi.product_id
    WHERE oi.order_id=?
"""
REFUNDS_INSERT = """
    INSERT INTO refunds(
        order_id, return_id, amount_minor, kind, created_at, idempotency_key
    ) VALUES(?,?,?,?,?,?)
"""


def snapshot_state(conn) -> dict:
    return {
        "orders": [dict(row) for row in conn.execute("SELECT id,status FROM orders ORDER BY id")],
        "returns": [
            dict(row) for row in conn.execute("SELECT id,order_id,status FROM returns ORDER BY id")
        ],
        "refunds": [
            dict(row)
            for row in conn.execute(
                "SELECT order_id,return_id,kind,amount_minor FROM refunds ORDER BY id"
            )
        ],
        "payments": [
            dict(row)
            for row in conn.execute("SELECT order_id,status FROM payments ORDER BY order_id")
        ],
    }


def _one(conn, query, parameters=()):
    row = conn.execute(query, parameters).fetchone()
    return dict(row) if row else None


def get_customer(conn, customer_id: str) -> dict | None:
    return _one(conn, "SELECT id,name FROM customers WHERE id=?", (customer_id,))


def list_audit_events(conn, customer_id: str, limit: int = 10) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT ts,event,intent,decision,clause_ids FROM audit_log "
            "WHERE customer_id=? ORDER BY id DESC LIMIT ?",
            (customer_id, limit),
        )
    ]


def get_order_bundle(conn, order_id):
    order = _one(conn, "SELECT * FROM orders WHERE id=?", (order_id,))
    if not order:
        return None
    order["items"] = [dict(x) for x in conn.execute(ORDER_ITEMS_QUERY, (order_id,))]
    order["payment"] = _one(conn, "SELECT * FROM payments WHERE order_id=?", (order_id,))
    order["returns"] = [
        dict(x)
        for x in conn.execute("SELECT * FROM returns WHERE order_id=? ORDER BY id", (order_id,))
    ]
    order["refunds"] = [
        dict(x)
        for x in conn.execute("SELECT * FROM refunds WHERE order_id=? ORDER BY id", (order_id,))
    ]
    return order


def list_orders(conn, customer_id):
    return [
        dict(x)
        for x in conn.execute(
            """
            SELECT id,status,total_minor,placed_at
            FROM orders
            WHERE customer_id=?
            ORDER BY placed_at DESC
            """,
            (customer_id,),
        )
    ]


def count_return_refunds_since(conn, customer_id, since_iso):
    return conn.execute(
        """
        SELECT count(*)
        FROM refunds r
        JOIN orders o ON o.id=r.order_id
        WHERE o.customer_id=? AND r.kind='return' AND r.created_at>=?
        """,
        (customer_id, since_iso),
    ).fetchone()[0]


def get_memory(conn, customer_id):
    return {
        r["key"]: r["value"]
        for r in conn.execute(
            "SELECT key,value FROM customer_memory WHERE customer_id=?", (customer_id,)
        )
    }


def get_pending_plan(conn, plan_id):
    return _one(conn, "SELECT * FROM pending_plans WHERE plan_id=?", (plan_id,))


def cancel_order(conn, order_id, idempotency_key):
    with conn:
        existing_refund = _existing_refund(conn, idempotency_key)
        if existing_refund:
            return _cancel_replay(existing_refund)
        order = get_order_bundle(conn, order_id)
        if not order or order["status"] == "cancelled":
            return {"ok": False, "error": "invalid_state"}
        amount = _refundable_amount(order)
        if amount <= 0:
            return {"ok": False, "error": "exceeds_refundable"}
        _insert_refund(conn, order_id, None, amount, "cancellation", idempotency_key)
        conn.execute("UPDATE payments SET status='refunded' WHERE order_id=?", (order_id,))
        conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
        return {
            "ok": True,
            "order_id": order_id,
            "status": "cancelled",
            "refund_amount_minor": amount,
            "replayed": False,
        }


def create_return(conn, order_id, reason_code, idempotency_key):
    with conn:
        existing_return = _one(
            conn, "SELECT * FROM returns WHERE idempotency_key=?", (idempotency_key,)
        )
        if existing_return:
            return {"ok": True, "return_id": existing_return["id"], "replayed": True}
        if not _one(conn, "SELECT id FROM orders WHERE id=?", (order_id,)):
            return {"ok": False, "error": "not_found"}
        next_number = conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(id,5) AS INTEGER)),9000)+1 FROM returns"
        ).fetchone()[0]
        return_id = f"RET-{next_number}"
        conn.execute(
            "INSERT INTO returns VALUES(?,?,?,?,?,?)",
            (
                return_id,
                order_id,
                reason_code,
                "approved",
                today().isoformat(),
                idempotency_key,
            ),
        )
        conn.execute("UPDATE orders SET status='return_requested' WHERE id=?", (order_id,))
        return {"ok": True, "return_id": return_id, "replayed": False}


def issue_refund(conn, order_id, return_id, amount_minor, idempotency_key):
    with conn:
        existing_refund = _existing_refund(conn, idempotency_key)
        if existing_refund:
            return _refund_replay(existing_refund)
        order = get_order_bundle(conn, order_id)
        error, remaining = _validate_refund(conn, order, order_id, return_id, amount_minor)
        if error:
            return {"ok": False, "error": error}
        result = _insert_refund(conn, order_id, return_id, amount_minor, "return", idempotency_key)
        remain = remaining - amount_minor
        conn.execute(
            "UPDATE payments SET status=? WHERE order_id=?",
            ("refunded" if remain == 0 else "partially_refunded", order_id),
        )
        if order["status"] == "return_requested" and remain == 0:
            conn.execute("UPDATE orders SET status='returned' WHERE id=?", (order_id,))
        return {
            "ok": True,
            "refund_id": result.lastrowid,
            "amount_minor": amount_minor,
            "replayed": False,
        }


def set_memory(conn, customer_id, key, value):
    with conn:
        conn.execute(
            """
            INSERT INTO customer_memory VALUES(?,?,?,?)
            ON CONFLICT(customer_id,key)
            DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
            """,
            (customer_id, key, value, today().isoformat()),
        )


def insert_audit(conn, run_id, customer_id, event, intent, decision, clause_ids, detail_json):
    with conn:
        conn.execute(
            """
            INSERT INTO audit_log(
                run_id,ts,customer_id,event,intent,decision,clause_ids,detail_json
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                today().isoformat(),
                customer_id,
                event,
                intent,
                decision,
                clause_ids,
                detail_json,
            ),
        )


def save_pending_plan(conn, plan_id, customer_id, payload_json, plan_hash):
    with conn:
        conn.execute(
            "INSERT INTO pending_plans VALUES(?,?,?,?,?,?)",
            (
                plan_id,
                customer_id,
                payload_json,
                plan_hash,
                "pending",
                today().isoformat(),
            ),
        )


def set_pending_status(conn, plan_id, status):
    with conn:
        conn.execute("UPDATE pending_plans SET status=? WHERE plan_id=?", (status, plan_id))


def _refundable_amount(order):
    refunded = sum(refund["amount_minor"] for refund in order["refunds"])
    return order["payment"]["amount_paid_minor"] - refunded


def _existing_refund(conn, idempotency_key):
    return _one(conn, "SELECT * FROM refunds WHERE idempotency_key=?", (idempotency_key,))


def _insert_refund(conn, order_id, return_id, amount, kind, idempotency_key):
    return conn.execute(
        REFUNDS_INSERT,
        (order_id, return_id, amount, kind, today().isoformat(), idempotency_key),
    )


def _cancel_replay(refund):
    return {
        "ok": True,
        "order_id": refund["order_id"],
        "status": "cancelled",
        "refund_amount_minor": refund["amount_minor"],
        "replayed": True,
    }


def _refund_replay(refund):
    return {
        "ok": True,
        "refund_id": refund["id"],
        "amount_minor": refund["amount_minor"],
        "replayed": True,
    }


def _validate_refund(conn, order, order_id, return_id, amount_minor):
    if not order:
        return "not_found", 0
    if not _one(
        conn,
        "SELECT id FROM returns WHERE id=? AND order_id=?",
        (return_id, order_id),
    ):
        return "return_not_found", 0
    if amount_minor <= 0:
        return "invalid_amount", 0
    remaining = _refundable_amount(order)
    if amount_minor > remaining:
        return "exceeds_refundable", 0
    return None, remaining
