from shopsense.facts import derive, load_facts
from shopsense.models import Intent


def test_derived_values(db_path, read_gateway, settings):
    for order_id, expected_days in [("ORD-10003", 3), ("ORD-10004", 20)]:
        customer = "C1" if order_id == "ORD-10003" else "C2"
        facts = load_facts(read_gateway, customer, Intent(intent="order_status", order_id=order_id))
        derived = derive(facts, Intent(intent="return_item", order_id=order_id), settings)
        assert derived.days_since_delivery == expected_days
    facts = load_facts(read_gateway, "C2", Intent(intent="return_item", order_id="ORD-10005"))
    assert derive(
        facts, Intent(intent="return_item", order_id="ORD-10005"), settings
    ).has_nonreturnable_item
    facts = load_facts(read_gateway, "C3", Intent(intent="refund_request", order_id="ORD-10007"))
    assert derive(
        facts, Intent(intent="refund_request", order_id="ORD-10007"), settings
    ).exceeds_ceiling
    facts = load_facts(read_gateway, "C5", Intent(intent="refund_request", order_id="ORD-10013"))
    assert derive(
        facts, Intent(intent="refund_request", order_id="ORD-10013"), settings
    ).over_refund_limit
    facts = load_facts(read_gateway, "C3", Intent(intent="refund_request", order_id="ORD-10009"))
    assert (
        derive(
            facts, Intent(intent="refund_request", order_id="ORD-10009"), settings
        ).existing_return["id"]
        == "RET-9001"
    )


def test_return_windows_and_refundable_amount(read_gateway, settings):
    facts = load_facts(read_gateway, "C4", Intent(intent="return_item", order_id="ORD-10011"))
    changed_mind = derive(
        facts,
        Intent(intent="return_item", order_id="ORD-10011", reason_code="changed_mind"),
        settings,
    )
    damaged = derive(
        facts,
        Intent(intent="return_item", order_id="ORD-10011", reason_code="damaged"),
        settings,
    )
    assert not changed_mind.within_window
    assert damaged.within_window

    order_facts = load_facts(
        read_gateway, "C4", Intent(intent="refund_request", order_id="ORD-10010")
    )
    assert (
        derive(
            order_facts, Intent(intent="refund_request", order_id="ORD-10010"), settings
        ).refundable_minor
        == 299900
    )
