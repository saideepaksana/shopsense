import json

from shopsense.baseline import BaselineSession
from shopsense.llm import FakeLLM


def test_baseline_tool_then_reply(read_gateway, write_gateway):
    llm = FakeLLM(
        [
            '{"action":"call_tool","tool":"get_order","args":{"order_id":"ORD-10001"}}',
            '{"action":"reply","text":"done"}',
        ]
    )
    session = BaselineSession("C1", llm, read_gateway, write_gateway, "policy", 4)
    reply = session.send("status")
    assert reply.text == "done"
    assert reply.tool_calls == 1


def test_baseline_prompt_disables_native_function_calling(read_gateway, write_gateway):
    session = BaselineSession("C1", FakeLLM([]), read_gateway, write_gateway, "policy", 1)

    assert (
        "You have no native function-calling interface; call tools only through the JSON action."
        in session._system_prompt()
    )


def test_baseline_max_steps(read_gateway, write_gateway):
    session = BaselineSession(
        "C1",
        FakeLLM(['{"action":"call_tool","tool":"list_orders","args":{}}'] * 2),
        read_gateway,
        write_gateway,
        "policy",
        2,
    )
    assert session.send("status").text == "I could not complete this request."


def test_baseline_keeps_assistant_history(read_gateway, write_gateway):
    llm = FakeLLM(
        [
            '{"action":"reply","text":"Your order is placed."}',
            '{"action":"reply","text":"I can still help."}',
        ]
    )
    session = BaselineSession("C1", llm, read_gateway, write_gateway, "policy", 4)

    session.send("status")
    session.send("yes")

    assert {"assistant": "Your order is placed."} in json.loads(llm.calls[1][1])


def test_baseline_scopes_read_tools_to_customer(read_gateway, write_gateway):
    llm = FakeLLM(
        [
            '{"action":"call_tool","tool":"get_order","args":{"customer_id":"C2","order_id":"ORD-10001"}}',
            '{"action":"reply","text":"done"}',
        ]
    )
    session = BaselineSession("C1", llm, read_gateway, write_gateway, "policy", 4)

    session.send("status")

    assert '"customer_id": "C1"' in llm.calls[1][1]
    assert '"customer_id": "C2"' not in llm.calls[1][1]


def test_baseline_recovers_from_invalid_tool_arguments(read_gateway, write_gateway):
    llm = FakeLLM(
        [
            '{"action":"call_tool","tool":"issue_refund","args":{"order_id":"ORD-10009",'
            '"return_id":"RET-9001","amount_minor":"lots"}}',
            '{"action":"reply","text":"I could not process those tool arguments."}',
        ]
    )
    session = BaselineSession("C3", llm, read_gateway, write_gateway, "policy", 4)

    reply = session.send("refund the return")

    assert reply.text == "I could not process those tool arguments."
