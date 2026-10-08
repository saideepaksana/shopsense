from dataclasses import dataclass
from datetime import date

from shopsense.clock import today
from shopsense.models import ReasonCode


@dataclass
class Facts:
    order: dict | None
    memory: dict[str, str]
    customer_orders: list[dict]


@dataclass
class Derived:
    days_since_delivery: int | None
    window_days: int
    within_window: bool
    has_nonreturnable_item: bool
    refundable_minor: int
    existing_return: dict | None
    exceeds_ceiling: bool
    refunds_last_90d: int
    over_refund_limit: bool


def load_facts(read_gateway, customer_id: str, intent) -> Facts:
    memory = read_gateway.get_memory(customer_id).get("memory", {})
    if intent.order_id:
        result = read_gateway.get_order(customer_id, intent.order_id)
        return Facts(result.get("order") if result.get("ok") else None, memory, [])
    return Facts(None, memory, read_gateway.list_orders(customer_id).get("orders", []))


def _window_days(intent, settings) -> int:
    extended_reasons = {
        ReasonCode.damaged,
        ReasonCode.wrong_item,
        ReasonCode.not_as_described,
    }
    if intent.reason_code in extended_reasons:
        return settings.extended_window_days
    return settings.return_window_days


def _delivery_days(order: dict) -> int | None:
    delivered_at = order.get("delivered_at")
    if not delivered_at:
        return None
    return (today() - date.fromisoformat(delivered_at)).days


def _refundable_amount(order: dict) -> int:
    paid_amount = (order.get("payment") or {}).get("amount_paid_minor", 0)
    refunded_amount = sum(refund["amount_minor"] for refund in order["refunds"])
    return max(0, paid_amount - refunded_amount)


def derive(facts: Facts, intent, settings) -> Derived:
    window = _window_days(intent, settings)
    refund_count = int(facts.memory.get("refunds_last_90d", "0"))
    if not facts.order:
        return _empty_derived(window, refund_count)
    order = facts.order
    days = _delivery_days(order)
    refundable = _refundable_amount(order)
    return Derived(
        days,
        window,
        days is not None and days <= window,
        any(x["returnable"] == 0 for x in order["items"]),
        refundable,
        order["returns"][-1] if order["returns"] else None,
        refundable > settings.refund_ceiling_minor,
        refund_count,
        refund_count >= settings.refund_limit_count,
    )


def _empty_derived(window: int, refund_count: int) -> Derived:
    return Derived(None, window, False, False, 0, None, False, refund_count, False)
