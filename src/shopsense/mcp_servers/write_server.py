from contextlib import closing

from fastmcp import FastMCP

from shopsense.db import repository
from shopsense.db.connection import connect


def create_write_server(db_path: str) -> FastMCP:
    server = FastMCP("shopsense-write")

    @server.tool()
    async def cancel_order(order_id: str, idempotency_key: str):
        with closing(connect(db_path)) as conn:
            return repository.cancel_order(conn, order_id, idempotency_key)

    @server.tool()
    async def create_return(order_id: str, reason_code: str, idempotency_key: str):
        with closing(connect(db_path)) as conn:
            return repository.create_return(conn, order_id, reason_code, idempotency_key)

    @server.tool()
    async def issue_refund(order_id: str, return_id: str, amount_minor: int, idempotency_key: str):
        with closing(connect(db_path)) as conn:
            return repository.issue_refund(conn, order_id, return_id, amount_minor, idempotency_key)

    return server
