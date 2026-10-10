from shopsense.models import Decision, IntentType, ToolName


def _v0(plan) -> list[str]:
    mismatch = (plan.decision != Decision.approve and plan.actions) or (
        plan.decision == Decision.approve and not plan.actions
    )
    return ["V0_ACTIONS_MISMATCH"] if mismatch else []


def _v1(plan, intent) -> list[str]:
    names = [action.tool for action in plan.actions]
    allowed = {
        IntentType.cancel_order: [ToolName.cancel_order],
        IntentType.return_item: None,
        IntentType.refund_request: None,
    }.get(intent.intent, [])
    valid_sequences = (allowed is not None and names == allowed) or (
        allowed is None
        and names in ([ToolName.create_return, ToolName.issue_refund], [ToolName.issue_refund])
    )
    return ["V1_TOOL_NOT_ALLOWED"] if plan.actions and not valid_sequences else []


def _v2(plan, intent, customer_id, facts) -> list[str]:
    invalid_owner = plan.actions and (
        not facts.order
        or facts.order.get("customer_id") != customer_id
        or any(action.args.get("order_id") != intent.order_id for action in plan.actions)
    )
    return ["V2_NOT_OWNED"] if invalid_owner else []


def _v3(plan, facts) -> list[str]:
    if not facts.order:
        return []
    violations = []
    for action in plan.actions:
        status = facts.order["status"]
        if action.tool == ToolName.cancel_order and status != "placed":
            violations.append("V3_BAD_STATE")
        if action.tool == ToolName.create_return and (
            status != "delivered" or facts.order["returns"]
        ):
            violations.append("V3_BAD_STATE")
        if action.tool == ToolName.issue_refund and len(plan.actions) == 1:
            returns = {item["id"]: item["status"] for item in facts.order["returns"]}
            return_id = action.args.get("return_id")
            if (
                status != "return_requested"
                or return_id not in returns
                or returns.get(return_id) not in {"approved", "received"}
            ):
                violations.append("V3_BAD_STATE")
    return violations


def _v4(plan, derived) -> list[str]:
    return [
        "V4_OUTSIDE_WINDOW"
        for action in plan.actions
        if action.tool == ToolName.create_return and not derived.within_window
    ]


def _v5(plan, derived) -> list[str]:
    return [
        "V5_NON_RETURNABLE"
        for action in plan.actions
        if action.tool == ToolName.create_return and derived.has_nonreturnable_item
    ]


def _v6(plan, derived) -> list[str]:
    return [
        "V6_BAD_AMOUNT"
        for action in plan.actions
        if action.tool == ToolName.issue_refund
        and (
            type(action.args.get("amount_minor")) is not int
            or action.args.get("amount_minor") != derived.refundable_minor
            or not derived.refundable_minor
        )
    ]


def _v7(plan, settings) -> list[str]:
    return [
        "V7_OVER_CEILING"
        for action in plan.actions
        if action.tool == ToolName.issue_refund
        and type(action.args.get("amount_minor")) is int
        and action.args.get("amount_minor") > settings.refund_ceiling_minor
    ]


def _v8(plan, derived) -> list[str]:
    return [
        "V8_REFUND_LIMIT"
        for action in plan.actions
        if action.tool == ToolName.issue_refund and derived.over_refund_limit
    ]


def _v9(plan, retrieved_ids) -> list[str]:
    invalid = plan.decision in {Decision.approve, Decision.deny} and (
        not plan.cited_clause_ids
        or any(clause_id not in retrieved_ids for clause_id in plan.cited_clause_ids)
    )
    return ["V9_BAD_CITATION"] if invalid else []


def _v10(plan, intent) -> list[str]:
    violations = []
    for index, action in enumerate(plan.actions):
        expected = {
            ToolName.cancel_order: {"order_id"},
            ToolName.create_return: {"order_id", "reason_code"},
            ToolName.issue_refund: {"order_id", "return_id", "amount_minor"},
        }[action.tool]
        invalid_reason = action.tool == ToolName.create_return and action.args.get(
            "reason_code"
        ) != (intent.reason_code.value if intent.reason_code else "other")
        unresolved_return = (
            action.tool == ToolName.issue_refund
            and action.args.get("return_id") == "$return_id"
            and not any(
                previous.tool == ToolName.create_return for previous in plan.actions[:index]
            )
        )
        new_return_mismatch = (
            action.tool == ToolName.issue_refund
            and any(previous.tool == ToolName.create_return for previous in plan.actions[:index])
            and action.args.get("return_id") != "$return_id"
        )
        if (
            set(action.args) != expected
            or invalid_reason
            or unresolved_return
            or new_return_mismatch
        ):
            violations.append("V10_BAD_ARGS")
    return violations


def verify(plan, intent, customer_id, facts, derived, retrieved_ids, settings) -> list[str]:
    violations = []
    violations.extend(_v0(plan))
    violations.extend(_v1(plan, intent))
    violations.extend(_v2(plan, intent, customer_id, facts))
    violations.extend(_v3(plan, facts))
    violations.extend(_v4(plan, derived))
    violations.extend(_v5(plan, derived))
    violations.extend(_v6(plan, derived))
    violations.extend(_v7(plan, settings))
    violations.extend(_v8(plan, derived))
    violations.extend(_v9(plan, retrieved_ids))
    violations.extend(_v10(plan, intent))
    return list(dict.fromkeys(violations))
