from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, field_validator


class IntentType(str, Enum):
    order_status = "order_status"
    cancel_order = "cancel_order"
    return_item = "return_item"
    refund_request = "refund_request"
    policy_question = "policy_question"
    unclear = "unclear"


class ReasonCode(str, Enum):
    damaged = "damaged"
    wrong_item = "wrong_item"
    not_as_described = "not_as_described"
    changed_mind = "changed_mind"
    late_delivery = "late_delivery"
    other = "other"


class PolicyTopic(str, Enum):
    general = "general"
    return_window = "return_window"
    returnability = "returnability"
    refund_limit = "refund_limit"
    refund_ceiling = "refund_ceiling"
    refund_method = "refund_method"
    cancellation = "cancellation"
    refund = "refund"
    confirmation = "confirmation"
    security = "security"


class Intent(BaseModel):
    intent: IntentType
    order_id: str | None = None
    reason_code: ReasonCode | None = None
    policy_topic: PolicyTopic = PolicyTopic.general
    list_orders: bool = False
    injection_suspected: bool = False

    @field_validator("order_id", mode="before")
    @classmethod
    def valid_order(cls, value):
        import re

        return (
            value.upper()
            if isinstance(value, str) and re.fullmatch(r"ORD-\d{5}", value, re.IGNORECASE)
            else None
        )


class Decision(str, Enum):
    approve = "approve"
    deny = "deny"
    clarify = "clarify"
    info = "info"


class ToolName(str, Enum):
    cancel_order = "cancel_order"
    create_return = "create_return"
    issue_refund = "issue_refund"


class Action(BaseModel):
    tool: ToolName
    args: dict[str, str | int]

    @field_validator("args", mode="before")
    @classmethod
    def coerce_amount(cls, value):
        args = dict(value)
        if isinstance(args.get("amount_minor"), bool):
            raise ValueError("amount_minor must be an integer")
        if isinstance(args.get("amount_minor"), str) and args["amount_minor"].isdigit():
            args["amount_minor"] = int(args["amount_minor"])
        return args


class Plan(BaseModel):
    decision: Decision
    actions: list[Action] = []
    cited_clause_ids: list[str] = []
    rationale: str = ""

    @field_validator("rationale", mode="before")
    @classmethod
    def trim(cls, value):
        return str(value or "")[:300]


@dataclass
class Reply:
    text: str
    decision: Decision | None
    outcome: str
    cited_clause_ids: list[str]
    tool_calls: int
    run_id: str


def format_inr(minor: int) -> str:
    return f"Rs {minor / 100:,.2f}"
