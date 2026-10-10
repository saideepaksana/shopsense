import re
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("intent", "policy_topic", mode="before")
    @classmethod
    def normalize_intent_fields(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("reason_code", mode="before")
    @classmethod
    def normalize_reason(cls, value):
        return _normalize_optional_enum(value)

    @field_validator("order_id", mode="before")
    @classmethod
    def valid_order(cls, value):
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
        amount = args.get("amount_minor")
        if isinstance(amount, str) and amount.isdigit():
            amount = int(amount)
            args["amount_minor"] = amount
        if "amount_minor" in args and type(amount) is not int:
            raise ValueError("amount_minor must be an integer paise value")
        return args

    @field_validator("tool", mode="before")
    @classmethod
    def normalize_tool(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Plan(BaseModel):
    decision: Decision
    actions: list[Action] = Field(default_factory=list)
    cited_clause_ids: list[str] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("decision", mode="before")
    @classmethod
    def normalize_decision(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

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
    error: str | None = None
    trace: dict = field(default_factory=dict)


def _normalize_optional_enum(value):
    if isinstance(value, str):
        normalized = value.strip().lower()
        return None if normalized in {"", "null", "none", "n/a"} else normalized
    return value


def format_inr(minor: int) -> str:
    return f"Rs {minor / 100:,.2f}"
