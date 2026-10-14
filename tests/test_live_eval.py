from contextlib import closing

from scripts.live_eval import _work_items
from shopsense.db.connection import connect
from shopsense.db.repository import snapshot_state
from shopsense.db.seed import ORDERS
from shopsense.evaluation.judge import judge
from shopsense.evaluation.metrics import aggregate
from shopsense.evaluation.report import render_markdown
from shopsense.evaluation.runner import run_trial
from shopsense.evaluation.scenarios import all_scenarios
from shopsense.llm import FakeLLM, LLMUnavailableError


def test_scenarios_match_seeded_customers_and_totals(db_path):
    scenarios = all_scenarios()
    assert len(scenarios) == 41
    assert len({scenario.id for scenario in scenarios}) == 41
    order_customers = {order[0]: order[1] for order in ORDERS}
    with closing(connect(db_path)) as conn:
        totals = {
            row["id"]: row["total_minor"]
            for row in conn.execute("SELECT id,total_minor FROM orders")
        }
    for scenario in scenarios:
        expected = scenario.expectation
        if expected.order_id and scenario.category in {"normal", "ambiguous", "refusal"}:
            assert order_customers[expected.order_id] == scenario.customer_id
        if expected.refund_amount_minor is not None:
            assert expected.refund_amount_minor == totals[expected.order_id]


def test_live_work_is_trial_major():
    scenarios = all_scenarios()[:2]

    work = _work_items(("pipeline", "baseline"), scenarios, 2)

    assert [(system, scenario.id, trial) for system, scenario, trial in work] == [
        ("pipeline", scenarios[0].id, 1),
        ("baseline", scenarios[0].id, 1),
        ("pipeline", scenarios[1].id, 1),
        ("baseline", scenarios[1].id, 1),
        ("pipeline", scenarios[0].id, 2),
        ("baseline", scenarios[0].id, 2),
        ("pipeline", scenarios[1].id, 2),
        ("baseline", scenarios[1].id, 2),
    ]


def test_judge_detects_collateral_and_unconfirmed_mutation(db_path):
    with closing(connect(db_path)) as conn:
        before = snapshot_state(conn)
    changed = {key: list(value) for key, value in before.items()}
    changed["orders"] = [dict(row) for row in before["orders"]]
    next(row for row in changed["orders"] if row["id"] == "ORD-10002")["status"] = "cancelled"
    scenario = next(item for item in all_scenarios() if item.id == "N1")
    verdict = judge(
        "pipeline",
        scenario,
        before,
        [before, changed],
        ["cancel now"],
        [{"outcome": "executed", "text": "", "cited_clause_ids": [], "trace": {}}],
    )
    assert verdict.mutated
    assert verdict.policy_violation
    assert verdict.unconfirmed_write
    assert verdict.collateral


def test_baseline_judge_skips_pipeline_checks_for_correct_state(db_path):
    with closing(connect(db_path)) as conn:
        before = snapshot_state(conn)
    scenario = next(item for item in all_scenarios() if item.id == "R1")
    verdict = judge(
        "baseline",
        scenario,
        before,
        [before, before],
        ["cancel ORD-10002"],
        [{"outcome": "baseline", "text": "Declined", "cited_clause_ids": [], "trace": {}}],
    )
    assert verdict.state_success
    assert verdict.checks == ()
    assert not verdict.false_block
    assert not verdict.task_success_full


def test_baseline_judge_reports_only_state_reasons(db_path):
    with closing(connect(db_path)) as conn:
        before = snapshot_state(conn)
    changed = {key: list(value) for key, value in before.items()}
    changed["orders"] = [dict(row) for row in before["orders"]]
    next(row for row in changed["orders"] if row["id"] == "ORD-10002")["status"] = "delivered"
    scenario = next(item for item in all_scenarios() if item.id == "R1")
    verdict = judge(
        "baseline",
        scenario,
        before,
        [before, changed],
        ["cancel ORD-10002"],
        [{"outcome": "baseline", "text": "Done", "cited_clause_ids": [], "trace": {}}],
    )
    assert verdict.checks
    assert all(reason.startswith("state:") for reason in verdict.checks)


def test_metrics_exclude_infrastructure_errors_and_calculate_pass_k():
    records = [
        {
            "system": "pipeline",
            "scenario": "N1",
            "category": "normal",
            "trial": 1,
            "status": "pass",
            "verdict": {"state_success": True, "task_success_full": True},
            "turns": [{"wall_ms": 10, "tool_calls": 1}],
        },
        {
            "system": "pipeline",
            "scenario": "N1",
            "category": "normal",
            "trial": 2,
            "status": "fail",
            "verdict": {"state_success": False},
            "turns": [{"wall_ms": 30, "tool_calls": 0}],
        },
        {
            "system": "pipeline",
            "scenario": "N1",
            "category": "normal",
            "trial": 3,
            "status": "infra_error",
            "turns": [{"wall_ms": 100}],
        },
    ]
    metrics = aggregate(records, 2)["pipeline"]["overall"]
    assert metrics["task_success_state"] == 0.5
    assert metrics["pass_k"] == {"1": 0.5, "2": 0.0}
    assert metrics["p95_turn_latency_ms"] == 30
    assert metrics["infra_error_count"] == 1


def test_baseline_metrics_leave_pipeline_only_fields_empty():
    record = {
        "system": "baseline",
        "scenario": "R1",
        "category": "refusal",
        "trial": 1,
        "status": "pass",
        "verdict": {"state_success": True},
        "turns": [],
        "clauses_required": True,
    }
    metrics = aggregate([record], 1)["baseline"]["overall"]
    assert metrics["task_success_full"] is None
    assert metrics["false_block_rate"] is None
    assert metrics["clause_accuracy"] is None


def test_metrics_include_baseline_stop_reasons_and_simulator_tokens():
    record = {
        "system": "baseline",
        "scenario": "N1",
        "category": "normal",
        "trial": 1,
        "status": "pass",
        "verdict": {"state_success": True},
        "turns": [
            {
                "tool_calls": 0,
                "wall_ms": 0,
                "trace": {"stop_reason": "replied"},
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            }
        ],
        "simulator_usage": {"prompt_tokens": 7, "completion_tokens": 11},
    }

    metrics = aggregate([record], 1)["baseline"]["overall"]

    assert metrics["stop_reasons"] == {"replied": 1}
    assert metrics["simulator_tokens"] == 18
    assert metrics["total_tokens"] == 23


def test_tool_efficiency_ignores_scenarios_without_expected_changes():
    records = [
        {
            "system": "baseline",
            "scenario": "read",
            "category": "normal",
            "trial": 1,
            "status": "pass",
            "expects_change": False,
            "verdict": {"state_success": True},
            "turns": [{"tool_calls": 0, "wall_ms": 0}],
        },
        {
            "system": "baseline",
            "scenario": "write",
            "category": "normal",
            "trial": 1,
            "status": "pass",
            "expects_change": True,
            "verdict": {"state_success": True},
            "turns": [{"tool_calls": 4, "wall_ms": 0}],
        },
    ]

    metrics = aggregate(records, 1)["baseline"]["overall"]

    assert metrics["tool_call_efficiency"] == 4


def test_empty_metric_denominators_are_none():
    record = {
        "system": "pipeline",
        "scenario": "N1",
        "category": "normal",
        "trial": 1,
        "status": "error",
        "injection": False,
        "clauses_required": False,
        "turns": [],
    }

    metrics = aggregate([record], 1)["pipeline"]["overall"]

    assert metrics["task_success_state"] is None
    assert metrics["task_success_full"] is None
    assert metrics["policy_violation_rate"] is None
    assert metrics["injection_resistance_rate"] is None
    assert metrics["unconfirmed_write_rate"] is None
    assert metrics["false_block_rate"] is None
    assert metrics["clause_accuracy"] is None
    assert metrics["pass_k"] == {"1": None}


def test_runner_records_success_and_unavailable_trials(db_path, settings):
    success_llm = FakeLLM(
        [
            '{"intent":"cancel_order","order_id":"ORD-10001"}',
            '{"decision":"approve","actions":[{"tool":"cancel_order","args":{"order_id":"ORD-10001"}}],"cited_clause_ids":["CAN-1"]}',
        ]
    )
    result = run_trial(
        settings, success_llm, "pipeline", next(s for s in all_scenarios() if s.id == "N1"), 1
    )
    assert result["status"] == "pass"
    baseline = run_trial(
        settings,
        FakeLLM(['{"action":"reply","text":"I cannot cancel that order."}']),
        "baseline",
        next(s for s in all_scenarios() if s.id == "R1"),
        1,
    )
    assert baseline["status"] == "pass"
    assert baseline["turns"][0]["outcome"] == "baseline"
    assert baseline["verdict"]["checks"] == ()
    outage = type(
        "Outage",
        (),
        {
            "complete": lambda self, system, user: (_ for _ in ()).throw(
                LLMUnavailableError("offline")
            )
        },
    )()
    failed = run_trial(
        settings, outage, "pipeline", next(s for s in all_scenarios() if s.id == "R1"), 1
    )
    assert failed["status"] == "infra_error"


def test_runner_scrubs_keys_from_trial_errors(settings):
    secret = "test-api-secret"

    class BrokenLLM:
        def complete(self, system, user):
            raise RuntimeError(secret)

    result = run_trial(
        settings,
        BrokenLLM(),
        "pipeline",
        next(s for s in all_scenarios() if s.id == "R1"),
        1,
        secret,
    )
    assert result["status"] == "error"
    assert secret not in result["error"]
    assert "***" in result["error"]


def test_baseline_unavailable_is_infra_error_and_keeps_prior_turn(settings):
    secret = "provider-secret"

    class IntermittentLLM:
        def __init__(self):
            self.calls = 0

        def complete(self, system, user):
            self.calls += 1
            if self.calls == 1:
                return '{"action":"reply","text":"Please confirm."}'
            raise LLMUnavailableError(f"offline {secret}")

    result = run_trial(
        settings,
        IntermittentLLM(),
        "baseline",
        next(s for s in all_scenarios() if s.id == "N1"),
        1,
        secret,
    )

    assert result["status"] == "infra_error"
    assert len(result["turns"]) == 1
    assert result["error"].startswith("LLMUnavailableError:")
    assert secret not in result["error"]
    assert "***" in result["error"]


def test_markdown_includes_both_systems_and_failures():
    groups = {"overall": {}, "categories": {}}
    payload = {
        "metadata": {},
        "metrics": {"pipeline": groups, "baseline": groups},
        "trials": [
            {
                "system": "pipeline",
                "scenario": "N1",
                "trial": 1,
                "status": "fail",
                "verdict": {"checks": ["outcome mismatch"]},
                "turns": [],
            }
        ],
    }
    rendered = render_markdown(payload)
    assert "| Metric | pipeline | baseline |" in rendered
    assert "## Failures" in rendered
    assert "n/a" in rendered
