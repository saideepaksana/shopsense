import json
import uuid

from pydantic import BaseModel

from shopsense.llm import LLMOutputError, complete_json
from shopsense.models import Reply


class Step(BaseModel):
    action: str
    tool: str | None = None
    args: dict = {}
    text: str | None = None


class BaselineSession:
    def __init__(
        self,
        customer_id,
        llm,
        read_gateway,
        write_gateway,
        policy_text,
        max_steps,
        retries: int = 2,
    ) -> None:
        self.customer_id = customer_id
        self.llm = llm
        self.read_gateway = read_gateway
        self.write_gateway = write_gateway
        self.policy_text = policy_text
        self.max_steps = max_steps
        self.retries = retries
        self.history = []

    def send(self, text: str) -> Reply:
        before = self.read_gateway.call_count + self.write_gateway.call_count
        self.history.append({"user": text})
        system = self._system_prompt()
        for _ in range(self.max_steps):
            try:
                step = complete_json(self.llm, system, json.dumps(self.history), Step, self.retries)
            except LLMOutputError:
                break
            if step.action == "reply":
                reply_text = step.text or ""
                self.history.append({"assistant": reply_text})
                return self._reply(reply_text, before)
            if step.action != "call_tool" or not step.tool:
                break
            result = self._call_tool(step.tool, step.args)
            if result is None:
                break
            self.history.append({"tool": step.tool, "result": result})
        return self._reply("I could not complete this request.", before)

    def _system_prompt(self) -> str:
        return f"""Logged-in customer: {self.customer_id}
Policy:
{self.policy_text}

Available tools:
- get_order(customer_id, order_id)
- list_orders(customer_id)
- get_memory(customer_id)
- cancel_order(order_id, idempotency_key)
- create_return(order_id, reason_code, idempotency_key)
- issue_refund(order_id, return_id, amount_minor, idempotency_key)

Respond with exactly one JSON object:
{{"action":"call_tool","tool":"<name>","args":{{...}}}}
or
{{"action":"reply","text":"<message>"}}
You have no native function-calling interface; call tools only through the JSON action.
Ask the customer for confirmation in plain language before any change."""

    def _call_tool(self, tool: str, supplied_args: dict):
        read_tools = {"get_order", "list_orders", "get_memory"}
        target = self.read_gateway if tool in read_tools else self.write_gateway
        args = dict(supplied_args)
        if tool in read_tools:
            args["customer_id"] = self.customer_id
        if target is self.write_gateway:
            args.setdefault("idempotency_key", uuid.uuid4().hex)
        try:
            return getattr(target, tool)(**args)
        except (AttributeError, TypeError):
            return None

    def _reply(self, text: str, before: int) -> Reply:
        calls = self.read_gateway.call_count + self.write_gateway.call_count - before
        return Reply(text, None, "baseline", [], calls, uuid.uuid4().hex)
