from shopsense.agents.planner import deterministic_plan, plan_request
from shopsense.agents.triage import triage_message
from shopsense.agents.verifier import verify
from shopsense.facts import Derived, load_facts
from shopsense.llm import FakeLLM
from shopsense.models import Intent


def test_triage_regex_and_prior_intent():
    intent = triage_message(
        FakeLLM(['{"intent":"cancel_order","order_id":"ORD-99999"}']),
        "cancel ORD-10001",
        None,
    )
    assert intent.order_id == "ORD-10001"
    prior = Intent(intent="cancel_order", order_id="ORD-10001")
    merged = triage_message(FakeLLM(['{"intent":"unclear"}']), "yes", prior)
    assert merged.intent.value == "cancel_order" and merged.order_id == "ORD-10001"


def test_triage_rejects_ambiguous_order_ids():
    llm = FakeLLM(['{"intent":"order_status"}'])
    assert triage_message(llm, "ORD-100012", None).order_id is None
    assert (
        triage_message(
            FakeLLM(['{"intent":"order_status"}']), "ORD-10001 and ORD-10002", None
        ).order_id
        is None
    )
    assert (
        triage_message(
            FakeLLM(['{"intent":"order_status"}']), "ORD-10001 and ORD-10001", None
        ).order_id
        == "ORD-10001"
    )


def test_triage_normalizes_policy_question_topic():
    intent = triage_message(
        FakeLLM(['{"intent":"policy_question"}']),
        "What is the return window?",
        None,
    )

    assert intent.policy_topic.value == "return_window"


def test_planner_has_no_raw_message_and_fail_closes(read_gateway, settings):
    intent = Intent(intent="cancel_order", order_id="ORD-10001")
    facts = load_facts(read_gateway, "C1", intent)
    llm = FakeLLM(["garbage"] * 3)
    plan = plan_request(
        llm,
        intent,
        facts,
        Derived(None, 10, False, False, 0, None, False, 0, False),
        [],
        None,
        2,
    )
    assert plan.decision.value == "deny"
    llm = FakeLLM(
        ['{"decision":"deny","actions":[],"cited_clause_ids":["CAN-2"],"rationale":"no"}']
    )
    plan_request(
        llm,
        intent,
        facts,
        Derived(None, 10, False, False, 0, None, False, 0, False),
        [],
        None,
        0,
    )
    assert "customer message" not in llm.calls[0][1]


def test_deterministic_plans():
    missing = Intent(intent="cancel_order")
    assert deterministic_plan(missing, type("F", (), {"order": None})(), []) is not None


def test_planner_coerces_amount_before_verification(read_gateway, settings):
    intent = Intent(intent="refund_request", order_id="ORD-10009")
    facts = load_facts(read_gateway, "C3", intent)
    derived = Derived(6, 10, True, False, 349900, {"id": "RET-9001"}, False, 0, False)
    plan = plan_request(
        FakeLLM(
            [
                '{"decision":"approve","actions":[{"tool":"issue_refund","args":{"order_id":"ORD-10009","return_id":"RET-9001","amount_minor":"349900"}}],"cited_clause_ids":["REF-5"],"rationale":"eligible"}'
            ]
        ),
        intent,
        facts,
        derived,
        [type("Clause", (), {"id": "REF-5", "text": "refund policy"})()],
        None,
        0,
    )
    assert not verify(plan, intent, "C3", facts, derived, ["REF-5"], settings)
