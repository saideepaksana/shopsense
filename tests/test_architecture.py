import inspect
from pathlib import Path

from shopsense.agents.triage import triage_message

ROOT = Path(__file__).parents[1] / "src" / "shopsense"


def test_architecture_rules():
    triage = (ROOT / "agents" / "triage.py").read_text()
    assert "gateway" not in triage.lower()
    assert list(inspect.signature(triage_message).parameters) == [
        "llm",
        "message",
        "prior_intent",
    ]
    for name in ["planner.py", "verifier.py", "responder.py"]:
        text = (ROOT / "agents" / name).read_text()
        assert (
            "WriteGateway" not in text
            and "write_gateway" not in text
            and "write_server" not in text
        )
    facts = (ROOT / "facts.py").read_text()
    assert all(term not in facts for term in ("WriteGateway", "write_gateway", "write_server"))
    executor = (ROOT / "agents" / "executor.py").read_text()
    assert "write_gateway" in executor
    nodes = (ROOT / "nodes.py").read_text()
    assert nodes.count('state["message"]') == 1
    assert 'triage_message(self.deps.llm, state["message"]' in nodes
    session = (ROOT / "session.py").read_text()
    assert "execute_plan" not in session
    assert "WriteGateway" not in session
    assert "write_gateway" not in session
    write_server = (ROOT / "mcp_servers" / "write_server.py").read_text().lower()
    assert not any(
        term in write_server for term in ("ownership", "ceiling", "window", "shipped", "delivered")
    )
    for path in ROOT.rglob("*.py"):
        if path.name not in {"connection.py", "repository.py"}:
            assert "sqlite3" not in path.read_text()
