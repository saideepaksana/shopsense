import json
from contextlib import closing

from shopsense.config import CLI_AUDIT_LIMIT
from shopsense.db import repository
from shopsense.db.connection import connect
from shopsense.models import format_inr


def handle_command(text: str, customer_id: str, db_path: str) -> str:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return "Unknown command. Type /help."
    command = parts[0]
    argument = parts[1] if len(parts) > 1 else ""
    if command == "/help":
        return _help()
    if command == "/orders":
        return _orders(customer_id, db_path)
    if command == "/db":
        return _order_details(argument, customer_id, db_path)
    if command == "/audit":
        return _audit(customer_id, db_path)
    return "Unknown command. Type /help."


def _help() -> str:
    return "/orders\n/db ORD-10001\n/audit\n/help\n/quit"


def _orders(customer_id: str, db_path: str) -> str:
    with closing(connect(db_path)) as conn:
        orders = repository.list_orders(conn, customer_id)
    if not orders:
        return "You do not have any orders on your account."
    lines = [
        f"- {order['id']} ({order['status']}, {format_inr(order['total_minor'])})"
        for order in orders
    ]
    return "Your orders:\n" + "\n".join(lines)


def _order_details(order_id: str, customer_id: str, db_path: str) -> str:
    order_id = order_id.strip()
    with closing(connect(db_path)) as conn:
        order = repository.get_order_bundle(conn, order_id) if order_id else None
    if not order or order["customer_id"] != customer_id:
        return "not found"
    return _format_order(order)


def _format_order(order: dict) -> str:
    lines = [
        f"Order {order['id']}",
        f"Status: {order['status']}",
        f"Placed: {order['placed_at']}",
        f"Shipped: {order['shipped_at'] or '-'}",
        f"Delivered: {order['delivered_at'] or '-'}",
        _format_payment(order),
        _format_returns(order["returns"]),
        _format_refunds(order["refunds"]),
    ]
    return "\n".join(lines)


def _format_payment(order: dict) -> str:
    payment = order["payment"]
    return f"Payment: {payment['status']}, {format_inr(payment['amount_paid_minor'])}"


def _format_returns(returns: list[dict]) -> str:
    if not returns:
        return "Returns: none"
    entries = ", ".join(
        f"{row['id']} ({row['status']}, {row['reason_code']}, {row['created_at']})"
        for row in returns
    )
    return "Returns: " + entries


def _format_refunds(refunds: list[dict]) -> str:
    if not refunds:
        return "Refunds: none"
    entries = ", ".join(
        f"#{row['id']} ({row['kind']}, {format_inr(row['amount_minor'])})"
        for row in refunds
    )
    return "Refunds: " + entries


def _audit(customer_id: str, db_path: str) -> str:
    with closing(connect(db_path)) as conn:
        rows = repository.list_audit_events(conn, customer_id, CLI_AUDIT_LIMIT)
    if not rows:
        return "No audit events for this customer."
    return "\n".join(_format_audit_row(row) for row in rows)


def _format_audit_row(row: dict) -> str:
    clauses = " ".join(json.loads(row["clause_ids"] or "[]")) or "-"
    return (
        f"{row['ts']} {row['event']} intent={row['intent'] or '-'} "
        f"decision={row['decision'] or '-'} clauses={clauses}"
    )
