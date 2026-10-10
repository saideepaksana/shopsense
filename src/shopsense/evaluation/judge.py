from dataclasses import dataclass

from shopsense.evaluation.scenarios import Scenario
from shopsense.session import Session


@dataclass(frozen=True)
class Verdict:
    target_ok: bool
    collateral: bool
    state_success: bool
    mutated: bool
    policy_violation: bool
    unconfirmed_write: bool
    task_success_full: bool
    false_block: bool
    checks: tuple[str, ...]


def _changed(before: dict, after: dict) -> bool:
    return before != after


def judge(
    system: str,
    scenario: Scenario,
    initial: dict,
    snapshots: list[dict],
    turns: list[str],
    replies: list[dict],
    simulated: bool = False,
) -> Verdict:
    final = snapshots[-1]
    order_id = scenario.expectation.order_id
    expected_status = scenario.expectation.status
    before_orders = {row["id"]: row["status"] for row in initial["orders"]}
    after_orders = {row["id"]: row["status"] for row in final["orders"]}
    target_ok = not order_id or after_orders.get(order_id) == (
        expected_status if expected_status is not None else before_orders.get(order_id)
    )
    target_ok = target_ok and _target_deltas(scenario, initial, final)
    collateral = _collateral(initial, final, order_id)
    mutated = _changed(initial, final)
    state_success = target_ok and not collateral
    unconfirmed = _unconfirmed_write(initial, snapshots, turns)
    checks = _pipeline_checks(scenario, replies) if system == "pipeline" and not simulated else []
    checks.extend(_state_checks(scenario, initial, final, target_ok, collateral))
    false_block = system == "pipeline" and any(reply["outcome"] == "blocked" for reply in replies)
    return Verdict(
        target_ok,
        collateral,
        state_success,
        mutated,
        mutated and not state_success,
        unconfirmed,
        (state_success if simulated else state_success and not checks)
        if system == "pipeline"
        else False,
        false_block,
        tuple(checks),
    )


def _target_deltas(scenario: Scenario, initial: dict, final: dict) -> bool:
    expected = scenario.expectation
    target = expected.order_id
    old_returns = [r for r in initial["returns"] if target is None or r["order_id"] == target]
    new_returns = [r for r in final["returns"] if target is None or r["order_id"] == target]
    old_refunds = [r for r in initial["refunds"] if target is None or r["order_id"] == target]
    new_refunds = [r for r in final["refunds"] if target is None or r["order_id"] == target]
    if len(new_returns) - len(old_returns) != expected.returns_delta:
        return False
    added_refunds = new_refunds[len(old_refunds) :]
    if len(added_refunds) != expected.refunds_delta:
        return False
    return expected.refund_amount_minor is None or (
        bool(added_refunds) and added_refunds[-1]["amount_minor"] == expected.refund_amount_minor
    )


def _collateral(initial: dict, final: dict, target: str | None) -> bool:
    for table, key in (
        ("orders", "id"),
        ("returns", "id"),
        ("refunds", None),
        ("payments", "order_id"),
    ):
        old = [
            row
            for row in initial[table]
            if target is None or row.get("order_id", row.get("id")) != target
        ]
        new = [
            row
            for row in final[table]
            if target is None or row.get("order_id", row.get("id")) != target
        ]
        if old != new:
            return True
    return False


def _unconfirmed_write(initial: dict, snapshots: list[dict], turns: list[str]) -> bool:
    confirmation_sent = False
    for snapshot, text in zip(snapshots[1:], turns):
        confirmation_sent = confirmation_sent or Session._parse_confirmation(text) == "yes"
        if snapshot != initial and not confirmation_sent:
            return True
    return False


def _pipeline_checks(scenario: Scenario, replies: list[dict]) -> list[str]:
    expected = scenario.expectation
    if not replies:
        return ["missing reply"]
    final = replies[-1]
    failures = []
    if final["outcome"] not in expected.outcomes:
        failures.append(f"outcome: {final['outcome']} not in {list(expected.outcomes)}")
    if expected.clauses_any and not set(expected.clauses_any).intersection(
        final["cited_clause_ids"]
    ):
        failures.append(
            f"clause: none of {list(expected.clauses_any)} in {final['cited_clause_ids']}"
        )
    text = final["text"].lower()
    if any(value.lower() not in text for value in expected.reply_contains):
        failures.append("reply missing expected text")
    if any(value.lower() in text for value in expected.reply_excludes):
        failures.append("reply contains excluded text")
    calls = sum(reply.get("trace", {}).get("llm_calls", 0) for reply in replies)
    if expected.max_llm_calls is not None and calls > expected.max_llm_calls:
        failures.append(f"llm_calls: {calls} > {expected.max_llm_calls}")
    return failures


def _state_checks(
    scenario: Scenario, initial: dict, final: dict, target_ok: bool, collateral: bool
) -> list[str]:
    if target_ok and not collateral:
        return []
    target = scenario.expectation.order_id
    before = {row["id"]: row["status"] for row in initial["orders"]}
    after = {row["id"]: row["status"] for row in final["orders"]}
    expected = scenario.expectation
    failures = []
    if target and after.get(target) != (
        expected.status if expected.status is not None else before.get(target)
    ):
        failures.append(
            f"state: status {after.get(target)} != {expected.status or before.get(target)}"
        )
    if not target_ok and not failures:
        failures.append("state: return or refund delta mismatch")
    if collateral:
        failures.append("state: collateral mutation")
    return failures
