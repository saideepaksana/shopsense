import asyncio
import json

from fastmcp import Client
from fastmcp.exceptions import ToolError


class _Gateway:
    def __init__(self, server, timeout: float = 30) -> None:
        self._server = server
        self._timeout = timeout
        self.call_count = 0

    def _parse_result(self, result):
        if result is None:
            return None
        if isinstance(result, dict):
            return result
        for parser in (
            self._data_result,
            self._structured_result,
            self._content_result,
            self._dumped_result,
        ):
            found, value = parser(result)
            if found:
                return value
        return result

    @staticmethod
    def _data_result(result):
        value = getattr(result, "data", None)
        return value is not None, value

    @staticmethod
    def _structured_result(result):
        value = getattr(result, "structured_content", None)
        return value is not None, value

    def _content_result(self, result):
        content = getattr(result, "content", None)
        if isinstance(content, list):
            return self._list_content(content)
        if isinstance(content, str):
            return True, self._parse_text(content)
        return False, None

    def _list_content(self, content):
        if not content:
            return True, {}
        first = content[0]
        if isinstance(first, dict):
            if isinstance(first.get("text"), str):
                return True, self._parse_text(first["text"])
            return True, first
        text = getattr(first, "text", None)
        return True, self._parse_text(text) if isinstance(text, str) else first

    @staticmethod
    def _parse_text(text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    @staticmethod
    def _dumped_result(result):
        dumped = result.model_dump() if hasattr(result, "model_dump") else None
        return isinstance(dumped, dict), dumped

    async def _async_call(self, tool: str, args: dict):
        async with Client(
            self._server, timeout=self._timeout, init_timeout=self._timeout
        ) as client:
            return self._parse_result(await client.call_tool(tool, args))

    def _call(self, tool: str, args: dict):
        self.call_count += 1
        try:
            return asyncio.run(self._async_call(tool, args))
        except ToolError as exc:
            return {"ok": False, "error": "invalid_arguments", "detail": str(exc)[:160]}


class ReadGateway(_Gateway):
    def __init__(self, server, timeout: float = 30) -> None:
        super().__init__(server, timeout)

    def get_order(self, customer_id: str, order_id: str):
        return self._call("get_order", {"customer_id": customer_id, "order_id": order_id})

    def list_orders(self, customer_id: str):
        return self._call("list_orders", {"customer_id": customer_id})

    def get_memory(self, customer_id: str):
        return self._call("get_memory", {"customer_id": customer_id})


class WriteGateway(_Gateway):
    def __init__(self, server, timeout: float = 30) -> None:
        super().__init__(server, timeout)

    def cancel_order(self, order_id: str, idempotency_key: str):
        return self._call(
            "cancel_order", {"order_id": order_id, "idempotency_key": idempotency_key}
        )

    def create_return(self, order_id: str, reason_code: str, idempotency_key: str):
        return self._call(
            "create_return",
            {
                "order_id": order_id,
                "reason_code": reason_code,
                "idempotency_key": idempotency_key,
            },
        )

    def issue_refund(self, order_id: str, return_id: str, amount_minor: int, idempotency_key: str):
        return self._call(
            "issue_refund",
            {
                "order_id": order_id,
                "return_id": return_id,
                "amount_minor": amount_minor,
                "idempotency_key": idempotency_key,
            },
        )
