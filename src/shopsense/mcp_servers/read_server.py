from contextlib import closing
from datetime import timedelta

from fastmcp import FastMCP

from shopsense.clock import today
from shopsense.db import repository
from shopsense.db.connection import connect


def create_read_server(db_path: str, refund_limit_days: int = 90) -> FastMCP:
    server = FastMCP("shopsense-read")

    @server.tool()
    async def get_order(customer_id: str, order_id: str):
        with closing(connect(db_path)) as conn:
            order = repository.get_order_bundle(conn, order_id)
            return (
                {"ok": True, "order": order}
                if order and order["customer_id"] == customer_id
                else {"ok": False, "error": "not_found"}
            )

    @server.tool()
    async def list_orders(customer_id: str):
        with closing(connect(db_path)) as conn:
            return {"ok": True, "orders": repository.list_orders(conn, customer_id)}

    @server.tool()
    async def get_memory(customer_id: str):
        with closing(connect(db_path)) as conn:
            return {
                "ok": True,
                "memory": _build_memory(conn, customer_id, refund_limit_days),
            }

    return server


def _build_memory(conn, customer_id: str, refund_limit_days: int = 90) -> dict[str, str]:
    memory = repository.get_memory(conn, customer_id)
    since = (today() - timedelta(days=refund_limit_days)).isoformat()
    count = repository.count_return_refunds_since(conn, customer_id, since)
    memory["refunds_last_90d"] = str(count)
    return memory
