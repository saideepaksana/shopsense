import pytest

from shopsense.llm import FakeLLM, LLMUnavailableError
from shopsense.session import create_session
from shopsense.trace import build_trace, render_trace


def test_trace_for_cancel_proposal_excludes_customer_message(db_path, settings):
    raw_message = "cancel ORD-10001 SENTINEL-CUSTOMER-TEXT"
    llm = FakeLLM(
        [
            '{"intent":"cancel_order","order_id":"ORD-10001"}',
            '{"decision":"approve","actions":[{"tool":"cancel_order",'
            '"args":{"order_id":"ORD-10001"}}],"cited_clause_ids":["CAN-1"]}',
        ]
    )

    reply = create_session("C1", db_path=db_path, llm=llm, settings=settings).send(raw_message)

    assert reply.trace["outcome"] == "awaiting_confirmation"
    assert reply.trace["intent"]["order_id"] == "ORD-10001"
    assert "CAN-1" in reply.trace["retrieved_clause_ids"]
    assert "SENTINEL-CUSTOMER-TEXT" not in repr(reply.trace)
    assert reply.trace["llm_calls"] == 2
    assert reply.trace["node_ms"]


def test_trace_for_denial(db_path, settings):
    llm = FakeLLM(
        [
            '{"intent":"return_item","order_id":"ORD-10007"}',
            '{"decision":"deny","cited_clause_ids":["REF-3"],"rationale":"above limit"}',
        ]
    )

    reply = create_session("C3", db_path=db_path, llm=llm, settings=settings).send(
        "return ORD-10007"
    )

    assert reply.trace["outcome"] == "denied"
    assert reply.trace["plan_decision"] == "deny"
    assert reply.trace["cited_clause_ids"] == ["REF-3"]


def test_trace_for_blocked_plan_has_violations(db_path, settings):
    llm = FakeLLM(
        [
            '{"intent":"cancel_order","order_id":"ORD-10002"}',
            '{"decision":"approve","actions":[{"tool":"cancel_order",'
            '"args":{"order_id":"ORD-10002"}}],"cited_clause_ids":["CAN-1"]}',
            '{"decision":"approve","actions":[{"tool":"cancel_order",'
            '"args":{"order_id":"ORD-10002"}}],"cited_clause_ids":["CAN-1"]}',
        ]
    )

    reply = create_session("C1", db_path=db_path, llm=llm, settings=settings).send(
        "cancel ORD-10002"
    )

    assert reply.outcome == "blocked"
    assert reply.trace["violations"]
    assert reply.trace["replans"] == 1


def test_trace_for_confirmation_turn_restores_plan(db_path, settings):
    llm = FakeLLM(
        [
            '{"intent":"cancel_order","order_id":"ORD-10001"}',
            '{"decision":"approve","actions":[{"tool":"cancel_order",'
            '"args":{"order_id":"ORD-10001"}}],"cited_clause_ids":["CAN-1"]}',
        ]
    )
    session = create_session("C1", db_path=db_path, llm=llm, settings=settings)
    session.send("cancel ORD-10001")

    reply = session.send("yes")

    assert reply.trace["outcome"] == "executed"
    assert reply.trace["intent"]["order_id"] == "ORD-10001"
    assert reply.trace["plan_decision"] == "approve"
    assert reply.trace["llm_calls"] == 0


def test_unavailable_trace_contains_error_and_not_message(db_path, settings):
    class BrokenLLM:
        def complete(self, system, user):
            raise LLMUnavailableError("provider offline")

    reply = create_session("C1", db_path=db_path, llm=BrokenLLM(), settings=settings).send(
        "cancel ORD-10001 PRIVATE-RAW-MESSAGE"
    )

    assert reply.trace["outcome"] == "llm_unavailable"
    assert reply.trace["error"] == "provider offline"
    assert "PRIVATE-RAW-MESSAGE" not in repr(reply.trace)


def test_confirmation_reprompt_has_minimal_trace(db_path, settings):
    llm = FakeLLM(
        [
            '{"intent":"cancel_order","order_id":"ORD-10001"}',
            '{"decision":"approve","actions":[{"tool":"cancel_order",'
            '"args":{"order_id":"ORD-10001"}}],"cited_clause_ids":["CAN-1"]}',
        ]
    )
    session = create_session("C1", db_path=db_path, llm=llm, settings=settings)
    session.send("cancel ORD-10001")

    reply = session.send("yes and refund ORD-10004")

    assert reply.trace["outcome"] == "awaiting_confirmation"
    assert reply.trace == {"outcome": "awaiting_confirmation"}
    assert len(llm.calls) == 2


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        (
            {
                "outcome": "awaiting_confirmation",
                "intent": {
                    "type": "cancel_order",
                    "order_id": "ORD-10001",
                    "reason_code": None,
                    "injection_suspected": False,
                },
                "retrieved_clause_ids": ["CAN-1", "CAN-3"],
                "plan_decision": "approve",
                "action_tool_names": ["cancel_order"],
                "cited_clause_ids": ["CAN-1"],
                "violations": [],
                "replans": 0,
                "llm_calls": 2,
                "llm_ms": 1840,
                "prompt_tokens": 1210,
                "completion_tokens": 96,
                "tool_calls": 3,
                "node_ms": {"triage": 620, "plan": 1100},
            },
            "[outcome=awaiting_confirmation]\n"
            "  intent   cancel_order ORD-10001 reason=- injection=no\n"
            "  policy   CAN-1 CAN-3\n"
            "  plan     approve [cancel_order] cites CAN-1\n"
            "  verify   OK replans=0\n"
            "  cost     llm_calls=2 llm_ms=1840 tokens=1210/96 tool_calls=3\n"
            "  nodes    triage=620ms plan=1100ms",
        ),
        (
            {"outcome": "llm_unavailable", "error": "HTTP 401: invalid key"},
            "[outcome=llm_unavailable]",
        ),
    ],
)
def test_render_trace_golden_strings(trace, expected):
    rendered = render_trace(trace)

    if trace["outcome"] == "llm_unavailable":
        assert rendered == expected
    else:
        assert rendered == expected


def test_build_trace_does_not_copy_unknown_graph_fields():
    trace = build_trace(
        {"outcome": "info", "message": "PRIVATE", "api_key": "SECRET"},
        {},
        {},
        0,
    )

    assert "message" not in trace
    assert "api_key" not in trace
