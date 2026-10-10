from typing import Any


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _intent_trace(intent: Any) -> dict | None:
    if intent is None:
        return None
    return {
        "type": _enum_value(intent.intent),
        "order_id": intent.order_id,
        "reason_code": _enum_value(intent.reason_code) if intent.reason_code else None,
        "injection_suspected": intent.injection_suspected,
    }


def _plan_trace(plan: Any) -> dict | None:
    if plan is None:
        return None
    return {
        "decision": _enum_value(plan.decision),
        "actions": [_enum_value(action.tool) for action in plan.actions],
        "cited_clause_ids": list(plan.cited_clause_ids),
    }


def build_trace(result: dict, usage_delta: dict, node_ms: dict, tool_calls: int) -> dict:
    """Build a trace from graph output and per-turn measurements."""
    intent = _intent_trace(result.get("intent"))
    plan = _plan_trace(result.get("plan"))
    return {
        "outcome": result.get("outcome"),
        "intent": intent,
        "retrieved_clause_ids": [
            clause.id for clause in result.get("clauses", [])
        ],
        "plan_decision": plan["decision"] if plan else None,
        "action_tool_names": plan["actions"] if plan else [],
        "cited_clause_ids": plan["cited_clause_ids"] if plan else [],
        "violations": list(result.get("violations", [])),
        "replans": result.get("replans", 0),
        "llm_calls": usage_delta.get("calls", 0),
        "llm_ms": usage_delta.get("llm_milliseconds", 0),
        "prompt_tokens": usage_delta.get("prompt_tokens", 0),
        "completion_tokens": usage_delta.get("completion_tokens", 0),
        "node_ms": dict(node_ms),
        "tool_calls": tool_calls,
    }


def render_trace(trace: dict) -> str:
    """Render compact per-turn trace text."""
    lines = [f"[outcome={trace.get('outcome', 'unknown')}]"]
    _append_intent(lines, trace.get("intent"))
    _append_policy(lines, trace.get("retrieved_clause_ids", []))
    _append_plan(lines, trace)
    _append_verify(lines, trace)
    _append_cost(lines, trace)
    _append_nodes(lines, trace.get("node_ms", {}))
    return "\n".join(lines)


def _append_intent(lines: list[str], intent: dict | None) -> None:
    if not intent:
        return
    order = intent.get("order_id") or "-"
    reason = intent.get("reason_code") or "-"
    injection = "yes" if intent.get("injection_suspected") else "no"
    lines.append(
        f"  intent   {intent.get('type', '-')} {order} reason={reason} injection={injection}"
    )


def _append_policy(lines: list[str], clause_ids: list[str]) -> None:
    if clause_ids:
        lines.append("  policy   " + " ".join(clause_ids))


def _append_plan(lines: list[str], trace: dict) -> None:
    decision = trace.get("plan_decision")
    if decision is None:
        return
    actions = ",".join(trace.get("action_tool_names", []))
    citations = " ".join(trace.get("cited_clause_ids", []))
    lines.append(f"  plan     {decision} [{actions}] cites {citations}".rstrip())


def _append_verify(lines: list[str], trace: dict) -> None:
    if trace.get("plan_decision") is None and not trace.get("violations"):
        return
    violations = trace.get("violations", [])
    result = f"violations={violations}" if violations else "OK"
    lines.append(f"  verify   {result} replans={trace.get('replans', 0)}")


def _append_cost(lines: list[str], trace: dict) -> None:
    keys = ("llm_calls", "llm_ms", "prompt_tokens", "completion_tokens", "tool_calls")
    if not any(key in trace for key in keys):
        return
    lines.append(
        f"  cost     llm_calls={trace.get('llm_calls', 0)} "
        f"llm_ms={trace.get('llm_ms', 0):.0f} "
        f"tokens={trace.get('prompt_tokens', 0)}/{trace.get('completion_tokens', 0)} "
        f"tool_calls={trace.get('tool_calls', 0)}"
    )


def _append_nodes(lines: list[str], node_ms: dict[str, float]) -> None:
    if node_ms:
        values = " ".join(f"{name}={duration:.0f}ms" for name, duration in node_ms.items())
        lines.append("  nodes    " + values)
