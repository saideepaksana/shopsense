import re

from pydantic import BaseModel

from shopsense.llm import LLM, LLMOutputError, complete_json
from shopsense.models import Intent, IntentType, PolicyTopic, ReasonCode
from shopsense.prompts import TRIAGE_SYSTEM

TRIAGE_RETRIES = 2


class TriageOutput(BaseModel):
    intent: IntentType
    reason_code: ReasonCode | None = None
    list_orders: bool = False
    injection_suspected: bool = False


def _is_order_list_request(message: str) -> bool:
    normalized = message.lower()
    return ("order" in normalized or "orders" in normalized) and any(
        phrase in normalized
        for phrase in (
            "all orders",
            "my orders",
            "orders i",
            "orders placed",
            "order history",
        )
    )


def _is_order_id_only(message: str) -> bool:
    return bool(re.fullmatch(r"\s*ORD-\d{5}\s*", message, re.IGNORECASE))


def _should_restore_prior_intent(
    prior_intent: Intent | None, output: TriageOutput, message: str
) -> bool:
    if (
        not prior_intent
        or prior_intent.intent == IntentType.unclear
        or prior_intent.order_id is not None
    ):
        return False
    if prior_intent.intent not in {
        IntentType.cancel_order,
        IntentType.return_item,
        IntentType.refund_request,
    }:
        return False
    return output.intent in {
        IntentType.unclear,
        IntentType.order_status,
    } or _is_order_id_only(message)


def triage_message(llm: LLM, message: str, prior_intent: Intent | None) -> Intent:
    output = _parse_output(llm, message)
    order_id = _extract_order_id(message)
    preserve_prior = _should_restore_prior_intent(prior_intent, output, message)
    return _build_intent(output, order_id, prior_intent, preserve_prior, message)


def _parse_output(llm: LLM, message: str) -> TriageOutput:
    try:
        output = complete_json(llm, TRIAGE_SYSTEM, message, TriageOutput, TRIAGE_RETRIES)
    except LLMOutputError:
        return TriageOutput(intent=IntentType.unclear)
    return output


def _extract_order_id(message: str) -> str | None:
    order_ids = {match.upper() for match in re.findall(r"\bORD-\d{5}\b", message, re.IGNORECASE)}
    return next(iter(order_ids)) if len(order_ids) == 1 else None


def _build_intent(output, order_id, prior_intent, preserve_prior, message):
    intent = (
        prior_intent.intent
        if preserve_prior
        else (
            output.intent
            if output.intent != IntentType.unclear or not prior_intent
            else prior_intent.intent
        )
    )
    return Intent(
        intent=intent,
        order_id=order_id or (prior_intent.order_id if prior_intent else None),
        reason_code=output.reason_code or (prior_intent.reason_code if prior_intent else None),
        policy_topic=_policy_topic(message)
        if output.intent == IntentType.policy_question
        else PolicyTopic.general,
        list_orders=False
        if preserve_prior
        else (output.list_orders or _is_order_list_request(message)),
        injection_suspected=False if preserve_prior else output.injection_suspected,
    )


def _policy_topic(message: str) -> PolicyTopic:
    normalized = message.lower()
    if "return" in normalized and any(
        term in normalized for term in ("window", "days", "how long", "period", "within")
    ):
        return PolicyTopic.return_window
    groups = (
        (PolicyTopic.returnability, ("nonreturnable", "not returnable", "eligible for return")),
        (PolicyTopic.refund_limit, ("refund limit", "refunds in", "how many refunds")),
        (PolicyTopic.refund_ceiling, ("ceiling", "maximum refund", "max refund")),
        (PolicyTopic.refund_method, ("payment method", "original payment", "where refund")),
        (PolicyTopic.cancellation, ("cancel", "cancellation")),
        (PolicyTopic.confirmation, ("confirmation", "confirm a", "confirm before")),
        (PolicyTopic.security, ("ignore policy", "manager", "admin", "override")),
        (PolicyTopic.returnability, ("return",)),
        (PolicyTopic.refund, ("refund",)),
    )
    return next(
        (topic for topic, terms in groups if any(term in normalized for term in terms)),
        PolicyTopic.general,
    )
