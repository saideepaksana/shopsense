from contextlib import closing

from shopsense.agents.executor import execute_plan
from shopsense.db.connection import connect
from shopsense.models import Action, Plan


def test_executor_resolves_return_id_and_is_idempotent(db_path, write_gateway):
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
                    "return_id": "$return_id",
                    "amount_minor": 199700,
                },
            ),
        ],
    )
    first = execute_plan(plan, "plan-1", write_gateway)
    second = execute_plan(plan, "plan-1", write_gateway)
    assert len(first) == 2 and len(second) == 2
    with closing(connect(db_path)) as conn, conn:
        assert (
            conn.execute("select count(*) from returns where order_id='ORD-10003'").fetchone()[0]
            == 1
        )
        assert (
            conn.execute("select count(*) from refunds where order_id='ORD-10003'").fetchone()[0]
            == 1
        )


def test_executor_stops_after_failed_action(write_gateway):
    plan = Plan(
        decision="approve",
        actions=[
            Action(
                tool="issue_refund",
                args={
                    "order_id": "ORD-10009",
                    "return_id": "RET-UNKNOWN",
                    "amount_minor": 349900,
                },
            ),
            Action(
                tool="create_return",
                args={"order_id": "ORD-10009", "reason_code": "changed_mind"},
            ),
        ],
    )

    results = execute_plan(plan, "failed-plan", write_gateway)

    assert len(results) == 1
    assert write_gateway.call_count == 1
