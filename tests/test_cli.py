import pytest

from shopsense import audit, cli
from shopsense.baseline import BaselineSession
from shopsense.cli_commands import handle_command
from shopsense.llm import FakeLLM
from shopsense.session import create_baseline_session, create_session


def test_help_command_lists_all_commands(db_path):
    text = handle_command("/help", "C1", db_path)

    assert all(command in text for command in ("/orders", "/db", "/audit", "/quit"))


def test_orders_command_uses_customer_orders_format(db_path):
    text = handle_command("/orders", "C1", db_path)

    assert text.startswith("Your orders:\n- ORD-10001 (placed, Rs 2,999.00)")
    assert "ORD-10002" in text and "ORD-10003" in text
    assert "ORD-10004" not in text


def test_db_command_reads_order_and_payment_details(db_path):
    text = handle_command("/db ORD-10009", "C3", db_path)

    assert "Status: return_requested" in text
    assert "Payment: paid, Rs 3,499.00" in text
    assert "RET-9001 (approved" in text
    assert "Refunds: none" in text


def test_db_command_hides_another_customers_order(db_path):
    assert handle_command("/db ORD-10004", "C1", db_path) == "not found"
    assert handle_command("/db ORD-99999", "C1", db_path) == "not found"


def test_audit_command_scopes_rows_to_customer(db_path):
    audit.record(db_path, "other-run", "C2", "private_event", clause_ids=["SEC-1"])
    audit.record(db_path, "own-run", "C1", "plan_proposed", clause_ids=["CAN-1"])

    text = handle_command("/audit", "C1", db_path)

    assert "plan_proposed" in text and "CAN-1" in text
    assert "private_event" not in text and "SEC-1" not in text


def test_unknown_command_returns_hint(db_path):
    assert handle_command("/wat", "C1", db_path) == "Unknown command. Type /help."


def test_unknown_customer_exits_with_code_two(monkeypatch, capsys, db_path, settings):
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr("sys.argv", ["shopsense", "--customer", "C99", "--db", db_path])

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert capsys.readouterr().out == "Unknown customer: C99\n"


def test_baseline_mode_runs_a_scripted_turn(monkeypatch, capsys, db_path, settings):
    session = create_baseline_session(
        "C1",
        db_path,
        llm=FakeLLM(['{"action":"reply","text":"Your order is placed."}']),
        settings=settings,
    )
    assert isinstance(session, BaselineSession)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "create_baseline_session", lambda *args, **kwargs: session)
    monkeypatch.setattr(
        "sys.argv",
        ["shopsense", "--customer", "C1", "--db", db_path, "--mode", "baseline", "--verbose"],
    )
    turns = iter(["status", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(turns))

    cli.main()
    output = capsys.readouterr().out

    assert "Logged in as C1 (Asha Rao) [baseline: no verifier, no confirmation gate]." in output
    assert "assistant> Your order is placed." in output
    assert "[outcome=baseline tool_calls=0 llm_calls=1" in output


def test_guarded_verbose_cli_renders_fake_llm_trace(monkeypatch, capsys, db_path, settings):
    session = create_session(
        "C1",
        db_path,
        llm=FakeLLM(
            [
                '{"intent":"cancel_order","order_id":"ORD-10001"}',
                '{"decision":"approve","actions":[{"tool":"cancel_order",'
                '"args":{"order_id":"ORD-10001"}}],"cited_clause_ids":["CAN-1"]}',
            ]
        ),
        settings=settings,
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "create_session", lambda *args, **kwargs: session)
    monkeypatch.setattr("sys.argv", ["shopsense", "--customer", "C1", "--db", db_path, "--verbose"])
    turns = iter(["cancel ORD-10001", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(turns))

    cli.main()
    output = capsys.readouterr().out

    assert "[outcome=awaiting_confirmation]" in output
    assert "intent   cancel_order ORD-10001" in output
    assert "plan     approve [cancel_order] cites CAN-1" in output
    assert "llm_calls=2" in output
