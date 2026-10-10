import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from shopsense.config import SIMULATED_MAX_TURNS, Settings
from shopsense.db.connection import connect
from shopsense.db.repository import snapshot_state
from shopsense.db.seed import seed
from shopsense.evaluation.judge import judge
from shopsense.evaluation.scenarios import Scenario
from shopsense.evaluation.simulated import CustomerSimulator, Persona
from shopsense.llm import LLM, LLMUnavailableError
from shopsense.models import Reply
from shopsense.session import create_baseline_session, create_session


def run_trial(
    settings: Settings,
    llm: LLM,
    system: str,
    scenario: Scenario,
    trial: int,
    api_key: str = "",
    on_trial: Callable[[dict], None] | None = None,
) -> dict:
    return _run_trial(settings, llm, system, scenario, trial, api_key, on_trial)


def run_simulated_trial(
    settings: Settings,
    llm: LLM,
    simulator_llm: LLM,
    system: str,
    scenario: Scenario,
    persona: Persona,
    trial: int,
    api_key: str = "",
    on_trial: Callable[[dict], None] | None = None,
) -> dict:
    simulator = CustomerSimulator(simulator_llm, persona)
    return _run_trial(settings, llm, system, scenario, trial, api_key, on_trial, simulator)


def _run_trial(
    settings: Settings,
    llm: LLM,
    system: str,
    scenario: Scenario,
    trial: int,
    api_key: str,
    on_trial: Callable[[dict], None] | None,
    simulator: CustomerSimulator | None = None,
) -> dict:
    started = time.perf_counter()
    record = _new_record(system, scenario, trial, simulator is not None)
    try:
        with tempfile.TemporaryDirectory(prefix="shopsense-eval-") as directory:
            db_path = str(Path(directory) / "shopsense.db")
            seed(db_path)
            session = _create_session(system, scenario.customer_id, db_path, llm, settings)
            with closing(connect(db_path)) as conn:
                initial = snapshot_state(conn)
            snapshots, sent_turns = _run_conversation(
                session, db_path, system, scenario, api_key, record, simulator, initial
            )
            verdict = judge(
                system,
                scenario,
                initial,
                snapshots,
                sent_turns,
                record["turns"],
                simulator is not None,
            )
            record["verdict"] = verdict.__dict__
            if record["status"] != "infra_error":
                success_key = "task_success_full" if system == "pipeline" else "state_success"
                record["status"] = "pass" if record["verdict"][success_key] else "fail"
    except LLMUnavailableError as exc:
        record["status"] = "infra_error"
        record["error"] = _scrub(f"{type(exc).__name__}: {exc}", api_key)
    except Exception as exc:
        record["status"] = "error"
        record["error"] = _scrub(f"{type(exc).__name__}: {exc}", api_key)
    if simulator:
        record["simulator_usage"] = simulator.usage()
    record["duration_seconds"] = time.perf_counter() - started
    if on_trial is not None:
        on_trial(record)
    return record


def _run_conversation(
    session: Any,
    db_path: str,
    system: str,
    scenario: Scenario,
    api_key: str,
    record: dict,
    simulator: CustomerSimulator | None,
    initial: dict,
) -> tuple[list[dict], list[str]]:
    snapshots = [initial]
    sent_turns = []
    transcript: list[dict[str, str]] = []
    turns = range(SIMULATED_MAX_TURNS) if simulator else scenario.turns
    for _ in turns:
        turn, text = _customer_message(simulator, transcript, scenario, sent_turns)
        if _skip_unconfirmed_yes(session, system, simulator, text, sent_turns, snapshots):
            continue
        reply, entry, snapshot = _send_turn(session, db_path, system, text, api_key)
        sent_turns.append(text)
        record["turns"].append(entry)
        snapshots.append(snapshot)
        if simulator:
            transcript.extend(
                [
                    {"role": "customer", "content": text},
                    {"role": "assistant", "content": reply.text},
                ]
            )
            record["turns_used"] = len(sent_turns)
            record["simulator_usage"] = simulator.usage()
        if reply.outcome == "llm_unavailable":
            record["status"] = "infra_error"
            record["error"] = _scrub(reply.error or "LLM unavailable", api_key)
            break
        if turn is not None and turn.done:
            break
    return snapshots, sent_turns


def _customer_message(
    simulator: CustomerSimulator | None,
    transcript: list[dict[str, str]],
    scenario: Scenario,
    sent_turns: list[str],
) -> tuple[Any, str]:
    if simulator:
        turn = simulator.next_message(transcript)
        return turn, turn.message
    return None, scenario.turns[len(sent_turns)]


def _skip_unconfirmed_yes(
    session: Any,
    system: str,
    simulator: CustomerSimulator | None,
    text: str,
    sent_turns: list[str],
    snapshots: list[dict],
) -> bool:
    if not simulator and system == "pipeline" and text == "yes" and session.pending_plan_id is None:
        sent_turns.append(text)
        snapshots.append(snapshots[-1])
        return True
    return False


def _new_record(system: str, scenario: Scenario, trial: int, simulated: bool) -> dict:
    record = {
        "system": system,
        "scenario": scenario.id,
        "category": scenario.category,
        "trial": trial,
        "status": "error",
        "turns": [],
        "error": None,
        "injection": scenario.injection,
        "clauses_required": bool(scenario.expectation.clauses_any),
    }
    if simulated:
        record.update(
            {
                "turns_used": 0,
                "simulator_usage": {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0},
            }
        )
    return record


def _create_session(
    system: str, customer_id: str, db_path: str, llm: LLM, settings: Settings
) -> Any:
    if system == "pipeline":
        return create_session(customer_id, db_path=db_path, llm=llm, settings=settings)
    return create_baseline_session(customer_id, db_path=db_path, llm=llm, settings=settings)


def _send_turn(
    session: Any, db_path: str, system: str, text: str, api_key: str
) -> tuple[Reply, dict, dict]:
    before = time.perf_counter()
    usage_before = session.llm.usage() if system == "baseline" else {}
    reply = session.send(text)
    entry = {
        "user": _scrub(text, api_key),
        "text": _scrub(reply.text, api_key),
        "outcome": reply.outcome,
        "cited_clause_ids": reply.cited_clause_ids,
        "trace": reply.trace if system == "pipeline" else {},
        "usage": _usage_delta(session.llm.usage(), usage_before) if system == "baseline" else {},
        "wall_ms": (time.perf_counter() - before) * 1000,
        "tool_calls": reply.tool_calls,
    }
    with closing(connect(db_path)) as conn:
        state = snapshot_state(conn)
    return reply, entry, state


def _scrub(value: str, api_key: str) -> str:
    return value.replace(api_key, "***") if api_key else value


def _usage_delta(after: dict, before: dict) -> dict:
    return {key: value - before.get(key, 0) for key, value in after.items()}
