import json
from dataclasses import asdict

from shopsense.llm import LLMOutputError, complete_json
from shopsense.models import Decision, IntentType, Plan
from shopsense.prompts import PLANNER_SYSTEM


def fail_closed_plan() -> Plan:
    return Plan(
        decision=Decision.deny,
        rationale="I could not safely complete this request automatically.",
    )


def plan_request(
    llm, intent, facts, derived, clauses, violations: list[str] | None, retries: int
) -> Plan:
    payload = {
        "intent": {
            "intent": intent.intent.value,
            "reason_code": intent.reason_code.value if intent.reason_code else None,
        },
        "order": facts.order,
        "derived": asdict(derived),
        "clauses": [{"id": x.id, "text": x.text} for x in clauses],
    }
    if violations:
        payload["previous_attempt_violations"] = violations
    try:
        return complete_json(llm, PLANNER_SYSTEM, json.dumps(payload), Plan, retries)
    except LLMOutputError:
        return fail_closed_plan()


def deterministic_plan(intent, facts, retrieved_ids: list[str]) -> Plan | None:
    if intent.intent == IntentType.unclear:
        return Plan(decision=Decision.clarify)
    if intent.intent == IntentType.policy_question:
        return Plan(decision=Decision.info, cited_clause_ids=retrieved_ids)
    if intent.intent == IntentType.order_status and intent.list_orders:
        return Plan(decision=Decision.info)
    if intent.intent == IntentType.order_status and not intent.order_id:
        return Plan(decision=Decision.clarify)
    if (
        intent.intent
        in {IntentType.cancel_order, IntentType.return_item, IntentType.refund_request}
        and not intent.order_id
    ):
        return Plan(decision=Decision.clarify)
    if intent.order_id and not facts.order:
        return Plan(
            decision=Decision.deny,
            cited_clause_ids=["AUTH-1"],
            rationale="I could not find that order on your account.",
        )
    if intent.intent == IntentType.order_status:
        return Plan(decision=Decision.info, cited_clause_ids=["INF-1"])
    return None
