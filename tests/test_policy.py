from shopsense.models import IntentType
from shopsense.policy.loader import load_clauses
from shopsense.policy.retriever import PolicyRetriever


def test_loader_and_retriever():
    clauses = load_clauses("policies/store_policy.md")
    assert len(clauses) == 18
    retriever = PolicyRetriever(clauses, 6)
    result = retriever.retrieve(IntentType.cancel_order, "cancel_order order status shipped")
    ids = [clause.id for clause in result]
    assert ids[0] == "CAN-2"
    assert all(clause.id in ids for clause in clauses if "general" in clause.tags)
    assert {"REF-3", "REF-4"} <= {
        c.id
        for c in retriever.retrieve(IntentType.refund_request, "refund limit last 90 days ceiling")
    }
    assert len(retriever.retrieve(IntentType.policy_question, "return window", limit=3)) == 3
