import subprocess
import sys

from scripts.live_eval import _report_base, _resume_metadata
from shopsense.evaluation.runner import run_simulated_trial
from shopsense.evaluation.scenarios import all_scenarios
from shopsense.evaluation.simulated import SIMULATED, CustomerSimulator
from shopsense.llm import FakeLLM, LLMUnavailableError


def test_customer_simulator_retries_invalid_json():
    llm = FakeLLM(["not json", '{"message":"Hello","done":false}'])
    simulator = CustomerSimulator(llm, SIMULATED[0])

    turn = simulator.next_message([])

    assert turn.message == "Hello"
    assert not turn.done
    assert simulator.usage()["calls"] == 2


def test_simulated_pipeline_trial_succeeds_and_keeps_usage_separate(settings):
    scenario = next(item for item in all_scenarios() if item.id == "N1")
    simulator_llm = FakeLLM(
        ['{"message":"Please cancel ORD-10001","done":false}', '{"message":"yes","done":true}']
    )
    system_llm = FakeLLM(
        [
            '{"intent":"cancel_order","order_id":"ORD-10001"}',
            '{"decision":"approve","actions":[{"tool":"cancel_order","args":{"order_id":"ORD-10001"}}],"cited_clause_ids":["CAN-1"]}',
        ]
    )

    result = run_simulated_trial(
        settings, system_llm, simulator_llm, "pipeline", scenario, SIMULATED[0], 1
    )

    assert result["status"] == "pass"
    assert result["turns_used"] == 2
    assert result["simulator_usage"]["calls"] == 2
    assert result["turns"][0]["trace"]["llm_calls"] > 0


def test_simulated_baseline_refusal_does_not_mutate(settings):
    scenario = next(item for item in all_scenarios() if item.id == "R1")
    result = run_simulated_trial(
        settings,
        FakeLLM(['{"action":"reply","text":"I cannot cancel that shipped order."}']),
        FakeLLM(['{"message":"Cancel ORD-10002","done":true}']),
        "baseline",
        scenario,
        next(persona for persona in SIMULATED if persona.scenario_id == "R1"),
        1,
    )

    assert result["status"] == "pass"
    assert not result["verdict"]["mutated"]


def test_simulated_system_unavailable_is_infra_error(settings):
    scenario = next(item for item in all_scenarios() if item.id == "N1")

    class Offline:
        def usage(self):
            return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

        def complete(self, system, user):
            raise LLMUnavailableError("offline")

    result = run_simulated_trial(
        settings,
        Offline(),
        FakeLLM(['{"message":"Cancel ORD-10001","done":true}']),
        "pipeline",
        scenario,
        SIMULATED[0],
        1,
    )

    assert result["status"] == "infra_error"


def test_simulated_customer_unavailable_is_infra_error(settings):
    scenario = next(item for item in all_scenarios() if item.id == "N1")

    class Offline:
        def usage(self):
            return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

        def complete(self, system, user):
            raise LLMUnavailableError("offline")

    result = run_simulated_trial(
        settings, FakeLLM([]), Offline(), "pipeline", scenario, SIMULATED[0], 1
    )

    assert result["status"] == "infra_error"


def test_simulated_list_prints_twelve_personas():
    result = subprocess.run(
        [sys.executable, "scripts/live_eval.py", "--user", "simulated", "--list"],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = result.stdout.strip().splitlines()
    assert len(lines) == 12
    assert lines[0].startswith("N1 ")
    assert lines[-1].startswith("I6 ")


def test_simulated_report_suffix_and_resume_trial_count(tmp_path):
    path = _report_base(str(tmp_path), "stamp", "model", "simulated")

    metadata = _resume_metadata({"trials": 1}, 3)

    assert path.name == "stamp-model-simulated"
    assert metadata["trials"] == 3
