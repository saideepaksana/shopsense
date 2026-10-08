from shopsense.models import format_inr


def describe_plan(plan, facts, derived) -> str:
    order = facts.order["id"]
    if plan.actions[0].tool.value == "cancel_order":
        return (
            f"Cancel order {order} and refund "
            f"{format_inr(derived.refundable_minor)} to your original payment method."
        )
    return (
        f"Return order {order} and refund "
        f"{format_inr(derived.refundable_minor)} to your original payment method."
    )


def _render_order_list(facts) -> str:
    if not facts.customer_orders:
        return "You do not have any orders on your account."
    return "Your orders:\n" + "\n".join(
        f"- {order['id']} ({order['status']}, {format_inr(order['total_minor'])})"
        for order in facts.customer_orders
    )


def _render_order_status(facts) -> str:
    order = facts.order
    dates = ", ".join(
        f"{key[:-3]} {order[key]}" for key in ("shipped_at", "delivered_at") if order.get(key)
    )
    return (
        f"Order {order['id']} is {order['status']}. Placed {order['placed_at']}. "
        f"{dates}. Total {format_inr(order['total_minor'])}."
    )


def _render_policy_answer(plan, clauses) -> str:
    return "\n".join(
        f"[{clause_id}] {clauses.get(clause_id, '')}" for clause_id in plan.cited_clause_ids
    )


def _render_clarification(intent, facts) -> str:
    if intent.intent.value == "unclear":
        return (
            "I can help with order status, cancellations, returns and refunds. "
            "What would you like to do?"
        )
    orders = list(facts.customer_orders)
    last_order_id = facts.memory.get("last_order_id")
    for index, order in enumerate(orders):
        if order["id"] == last_order_id:
            orders.insert(0, orders.pop(index))
            break
    lines = [
        f"\n- {order['id']} ({order['status']}, {format_inr(order['total_minor'])})"
        f"{' <- last order you asked about' if order['id'] == last_order_id else ''}"
        for order in orders[:5]
    ]
    return "Which order is this about?" + "".join(lines)


def _render_execution(state) -> str:
    messages = []
    for row in state.get("executed", []):
        result = row["result"]
        if row["tool"] == "cancel_order":
            messages.append(
                f"Order {result['order_id']} is cancelled. "
                f"{format_inr(result['refund_amount_minor'])} will be refunded to "
                "your original payment method."
            )
        elif row["tool"] == "create_return":
            messages.append(f"Return {result['return_id']} is approved.")
        else:
            messages.append(
                f"{format_inr(result['amount_minor'])} has been refunded to your "
                "original payment method."
            )
    return "\n".join(messages)


def render(state) -> str:
    clauses = {clause.id: clause.text for clause in state.get("clauses", [])}
    return _renderer_for(state)(state, clauses)


def _renderer_for(state):
    if state["outcome"] == "info":
        return _render_info
    return {
        "clarify": _render_clarification_outcome,
        "denied": _render_denied,
        "awaiting_confirmation": _render_confirmation,
        "rejected": _render_rejected,
        "blocked": _render_blocked,
        "stale": _render_stale,
        "execution_failed": _render_execution_failed,
    }.get(state["outcome"], _render_execution_result)


def _render_info(state, clauses) -> str:
    intent = state["intent"]
    facts = state["facts"]
    if intent.list_orders:
        return _render_order_list(facts)
    if intent.intent.value == "order_status":
        return _render_order_status(facts)
    return _render_policy_answer(state["plan"], clauses)


def _render_clarification_outcome(state, _) -> str:
    return _render_clarification(state["intent"], state["facts"])


def _render_denied(state, clauses) -> str:
    plan = state["plan"]
    citations = "".join(
        f"\n[{clause_id}] {clauses.get(clause_id, '')}" for clause_id in plan.cited_clause_ids
    )
    return "I can't do that. " + plan.rationale + citations


def _render_confirmation(state, _) -> str:
    description = describe_plan(state["plan"], state["facts"], state["derived"])
    return f'I can do the following: {description} Reply "yes" to confirm or "no" to cancel.'


def _render_rejected(_, __) -> str:
    return "Okay, I have cancelled that request. Nothing was changed."


def _render_blocked(_, __) -> str:
    return "I could not safely complete this automatically, so I made no changes."


def _render_stale(_, __) -> str:
    return "I could not find a pending request to confirm."


def _render_execution_failed(_, __) -> str:
    return "Something went wrong while processing this, so it may be incomplete. Please try again."


def _render_execution_result(state, _) -> str:
    return _render_execution(state)
