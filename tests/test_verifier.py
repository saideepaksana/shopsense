from shopsense.agents.verifier import verify
from shopsense.facts import derive, load_facts
from shopsense.models import Action, Intent, Plan


def _case(read_gateway, settings, customer, intent, plan):
    facts = load_facts(read_gateway, customer, intent)
    derived = derive(facts, intent, settings)
    return verify(
        plan,
        intent,
        customer,
        facts,
        derived,
        [
            "CAN-1",
            "CAN-2",
            "CAN-3",
            "RET-1",
            "RET-2",
            "RET-3",
            "RET-4",
            "REF-3",
            "REF-4",
            "REF-5",
            "REF-6",
            "AUTH-1",
        ],
        settings,
    )


def test_verifier_passing_cases(read_gateway, settings):
    cancel = Intent(intent="cancel_order", order_id="ORD-10001")
    assert not _case(
        read_gateway,
        settings,
        "C1",
        cancel,
        Plan(
            decision="approve",
            actions=[Action(tool="cancel_order", args={"order_id": "ORD-10001"})],
            cited_clause_ids=["CAN-1"],
        ),
    )
    refund = Intent(intent="refund_request", order_id="ORD-10009")
    assert not _case(
        read_gateway,
        settings,
        "C3",
        refund,
        Plan(
            decision="approve",
            actions=[
                Action(
                    tool="issue_refund",
                    args={
                        "order_id": "ORD-10009",
                        "return_id": "RET-9001",
                        "amount_minor": 349900,
                    },
                )
            ],
            cited_clause_ids=["REF-5"],
        ),
    )


def test_verifier_blocks_key_rules(read_gateway, settings):
    cases = [
        (
            "C1",
            Intent(intent="cancel_order", order_id="ORD-10002"),
            Plan(
                decision="approve",
                actions=[Action(tool="cancel_order", args={"order_id": "ORD-10002"})],
                cited_clause_ids=["CAN-2"],
            ),
            "V3_BAD_STATE",
        ),
        (
            "C2",
            Intent(intent="return_item", order_id="ORD-10004"),
            Plan(
                decision="approve",
                actions=[
                    Action(
                        tool="create_return",
                        args={"order_id": "ORD-10004", "reason_code": "changed_mind"},
                    ),
                    Action(
                        tool="issue_refund",
                        args={
                            "order_id": "ORD-10004",
                            "return_id": "$return_id",
                            "amount_minor": 199900,
                        },
                    ),
                ],
                cited_clause_ids=["RET-1"],
            ),
            "V4_OUTSIDE_WINDOW",
        ),
        (
            "C2",
            Intent(intent="return_item", order_id="ORD-10005"),
            Plan(
                decision="approve",
                actions=[
                    Action(
                        tool="create_return",
                        args={"order_id": "ORD-10005", "reason_code": "changed_mind"},
                    ),
                    Action(
                        tool="issue_refund",
                        args={
                            "order_id": "ORD-10005",
                            "return_id": "$return_id",
                            "amount_minor": 59900,
                        },
                    ),
                ],
                cited_clause_ids=["RET-2"],
            ),
            "V5_NON_RETURNABLE",
        ),
        (
            "C3",
            Intent(intent="refund_request", order_id="ORD-10007"),
            Plan(
                decision="approve",
                actions=[
                    Action(
                        tool="issue_refund",
                        args={
                            "order_id": "ORD-10007",
                            "return_id": "RET-9001",
                            "amount_minor": 1250000,
                        },
                    )
                ],
                cited_clause_ids=["REF-3"],
            ),
            "V7_OVER_CEILING",
        ),
    ]
    for customer, intent, plan, code in cases:
        assert code in _case(read_gateway, settings, customer, intent, plan)


def test_verifier_blocks_plan_shape_and_citation_rules(read_gateway, settings):
    cases = [
        (
            "C1",
            Intent(intent="cancel_order", order_id="ORD-10001"),
            Plan(
                decision="deny",
                actions=[Action(tool="cancel_order", args={"order_id": "ORD-10001"})],
                cited_clause_ids=["CAN-1"],
            ),
            "V0_ACTIONS_MISMATCH",
        ),
        (
            "C1",
            Intent(intent="cancel_order", order_id="ORD-10001"),
            Plan(
                decision="approve",
                actions=[
                    Action(
                        tool="issue_refund",
                        args={
                            "order_id": "ORD-10001",
                            "return_id": "RET-1",
                            "amount_minor": 1,
                        },
                    )
                ],
                cited_clause_ids=["CAN-1"],
            ),
            "V1_TOOL_NOT_ALLOWED",
        ),
        (
            "C1",
            Intent(intent="cancel_order", order_id="ORD-10001"),
            Plan(
                decision="approve",
                actions=[Action(tool="cancel_order", args={"order_id": "ORD-10002"})],
                cited_clause_ids=["CAN-1"],
            ),
            "V2_NOT_OWNED",
        ),
        (
            "C3",
            Intent(intent="refund_request", order_id="ORD-10009"),
            Plan(
                decision="approve",
                actions=[
                    Action(
                        tool="issue_refund",
                        args={
                            "order_id": "ORD-10009",
                            "return_id": "RET-9001",
                            "amount_minor": 1,
                        },
                    )
                ],
                cited_clause_ids=["REF-5"],
            ),
            "V6_BAD_AMOUNT",
        ),
        (
            "C5",
            Intent(intent="refund_request", order_id="ORD-10013"),
            Plan(
                decision="approve",
                actions=[
                    Action(
                        tool="issue_refund",
                        args={
                            "order_id": "ORD-10013",
                            "return_id": "RET-9002",
                            "amount_minor": 72000,
                        },
                    )
                ],
                cited_clause_ids=["REF-5"],
            ),
            "V8_REFUND_LIMIT",
        ),
        (
            "C1",
            Intent(intent="cancel_order", order_id="ORD-10001"),
            Plan(
                decision="approve",
                actions=[Action(tool="cancel_order", args={"order_id": "ORD-10001"})],
            ),
            "V9_BAD_CITATION",
        ),
        (
            "C1",
            Intent(intent="cancel_order", order_id="ORD-10001"),
            Plan(
                decision="approve",
                actions=[Action(tool="cancel_order", args={})],
                cited_clause_ids=["CAN-1"],
            ),
            "V10_BAD_ARGS",
        ),
    ]
    for customer, intent, plan, code in cases:
        assert code in _case(read_gateway, settings, customer, intent, plan)


def test_verifier_requires_new_return_placeholder_for_combined_plan(read_gateway, settings):
    intent = Intent(intent="return_item", order_id="ORD-10003", reason_code="changed_mind")
    plan = Plan(
        decision="approve",
        actions=[
            Action(
                tool="create_return",
                args={"order_id": "ORD-10003", "reason_code": "changed_mind"},
            ),
            Action(
                tool="issue_refund",
                args={
                    "order_id": "ORD-10003",
                    "return_id": "RET-9001",
                    "amount_minor": 199700,
                },
            ),
        ],
        cited_clause_ids=["REF-5"],
    )

    assert "V10_BAD_ARGS" in _case(read_gateway, settings, "C1", intent, plan)
