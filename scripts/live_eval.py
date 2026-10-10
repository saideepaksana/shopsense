import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from shopsense.clock import FROZEN_TODAY
from shopsense.config import SIMULATOR_TEMPERATURE, load_settings
from shopsense.evaluation.report import utc_stamp, write_report
from shopsense.evaluation.runner import run_simulated_trial, run_trial
from shopsense.evaluation.scenarios import Scenario, all_scenarios
from shopsense.evaluation.simulated import SIMULATED
from shopsense.llm import build_llm, build_simulator_llm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live ShopSense evaluation trials.")
    parser.add_argument("--system", choices=("pipeline", "baseline", "both"), default="both")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--only")
    parser.add_argument("--category")
    parser.add_argument("--output-dir", default="reports/live")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--resume")
    parser.add_argument("--user", choices=("scripted", "simulated"), default="scripted")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenarios, personas = _evaluation_scenarios(args.user)
    if args.list:
        _print_scenarios(scenarios, personas, args.user)
        return 0
    if args.trials < 1:
        raise SystemExit("--trials must be at least 1")
    clock_override = os.getenv("SHOPSENSE_TODAY")
    if clock_override and clock_override != FROZEN_TODAY.isoformat():
        raise SystemExit(f"SHOPSENSE_TODAY must be {FROZEN_TODAY.isoformat()} for this evaluation")
    selected = _select(scenarios, args.only, args.category)
    settings = load_settings()
    llm = build_llm(settings)
    simulator_llm = build_simulator_llm(settings) if args.user == "simulated" else None
    systems = ("pipeline", "baseline") if args.system == "both" else (args.system,)
    metadata = {
        "model": settings.llm_model,
        "provider_host": urlparse(settings.llm_base_url).hostname or "",
        "created_at": utc_stamp(),
        "trials": args.trials,
        "clock_date": FROZEN_TODAY.isoformat(),
        "user": args.user,
    }
    if args.user == "simulated":
        metadata["simulator_temperature"] = SIMULATOR_TEMPERATURE
    if args.resume:
        report_path = Path(args.resume)
        old = json.loads(report_path.read_text())
        records = old.get("trials", [])
        metadata = _resume_metadata(old.get("metadata", metadata), args.trials)
        report_base = report_path.with_suffix("")
    else:
        records = []
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", settings.llm_model).strip("-") or "model"
        report_base = _report_base(args.output_dir, metadata["created_at"], slug, args.user)
    work = [
        (system, scenario, trial)
        for system in systems
        for scenario in selected
        for trial in range(1, args.trials + 1)
    ]
    for index, (system, scenario, trial) in enumerate(work, 1):
        key = (system, scenario.id, trial)
        existing = next(
            (r for r in records if (r["system"], r["scenario"], r["trial"]) == key), None
        )
        if existing and existing["status"] != "infra_error":
            continue

        def save(result: dict) -> None:
            records[:] = [r for r in records if (r["system"], r["scenario"], r["trial"]) != key]
            records.append(dict(result))
            write_report(report_base, metadata, records, args.trials)

        if args.user == "simulated":
            result = run_simulated_trial(
                settings,
                llm,
                simulator_llm,
                system,
                scenario,
                personas[scenario.id],
                trial,
                settings.llm_api_key,
                save,
            )
        else:
            result = run_trial(settings, llm, system, scenario, trial, settings.llm_api_key, save)
        _print_progress(index, len(work), system, scenario, trial, result, args.user)
    json_path, md_path = write_report(report_base, metadata, records, args.trials)
    print(f"Reports: {json_path} and {md_path}")
    _print_summary(records)
    return _exit_code(records)


def _select(
    scenarios: tuple[Scenario, ...], only: str | None, category: str | None
) -> list[Scenario]:
    ids = set(only.split(",")) if only else None
    selected = [
        s
        for s in scenarios
        if (ids is None or s.id in ids) and (category is None or s.category == category)
    ]
    if ids and ids - {s.id for s in scenarios}:
        raise SystemExit(
            "Unknown scenario id(s): " + ", ".join(sorted(ids - {s.id for s in scenarios}))
        )
    return selected


def _resume_metadata(metadata: dict, requested_trials: int) -> dict:
    metadata["trials"] = max(int(metadata.get("trials", 1)), requested_trials)
    return metadata


def _evaluation_scenarios(user: str) -> tuple[tuple[Scenario, ...], dict]:
    scenarios = all_scenarios()
    personas = {persona.scenario_id: persona for persona in SIMULATED}
    selected = (
        scenarios
        if user == "scripted"
        else tuple(scenario for scenario in scenarios if scenario.id in personas)
    )
    return selected, personas


def _print_scenarios(scenarios: tuple[Scenario, ...], personas: dict, user: str) -> None:
    for scenario in scenarios:
        if user == "simulated":
            print(f"{scenario.id} {personas[scenario.id].goal}")
        else:
            print(f"{scenario.id} {scenario.category} | " + " -> ".join(scenario.turns))


def _report_base(output_dir: str, created_at: str, slug: str, user: str) -> Path:
    suffix = "-simulated" if user == "simulated" else ""
    return Path(output_dir) / f"{created_at}-{slug}{suffix}"


def _print_progress(
    index: int, total: int, system: str, scenario: Scenario, trial: int, result: dict, user: str
) -> None:
    outcome = result["turns"][-1]["outcome"] if result["turns"] else result["status"]
    state = "PASS" if result["status"] == "pass" else "FAIL"
    reasons = result.get("verdict", {}).get("checks", [])
    failure = reasons[0] if reasons else None
    if not failure and result.get("verdict", {}).get("unconfirmed_write"):
        failure = "unconfirmed_write"
    elif not failure and result.get("verdict", {}).get("policy_violation"):
        failure = "policy_violation"
    failure = failure or result.get("error") or outcome
    reason = f" {failure}" if state == "FAIL" else ""
    calls = sum(
        turn.get("trace", {}).get("llm_calls", 0) + turn.get("usage", {}).get("calls", 0)
        for turn in result["turns"]
    )
    turns = f" turns={result.get('turns_used', 0)}" if user == "simulated" else ""
    print(
        f"[{index:3}/{total}] {system} {scenario.id} t{trial} {state} "
        f"{result['duration_seconds']:.1f}s llm={calls}{turns}{reason}"
    )


def _print_summary(records: list[dict]) -> None:
    from shopsense.evaluation.metrics import aggregate

    result = aggregate(records, max((r["trial"] for r in records), default=1))
    systems = list(result)
    _print_table("Overall", systems, {system: result[system]["overall"] for system in systems})
    categories = sorted({name for groups in result.values() for name in groups["categories"]})
    for category in categories:
        values = {system: result[system]["categories"].get(category, {}) for system in systems}
        _print_table(category, systems, values)


def _print_table(title: str, systems: list[str], values: dict) -> None:
    metrics = (
        "task_success_state",
        "task_success_full",
        "policy_violation_rate",
        "injection_resistance_rate",
        "unconfirmed_write_rate",
        "false_block_rate",
        "clause_accuracy",
        "tool_call_efficiency",
        "mean_llm_calls",
        "mean_turns",
        "pass_k",
        "p50_turn_latency_ms",
        "p95_turn_latency_ms",
        "total_tokens",
        "error_count",
        "infra_error_count",
    )
    print(f"{title}\nMetric | " + " | ".join(systems))
    for metric in metrics:
        cells = [_console_value(values[system].get(metric)) for system in systems]
        print(f"{metric} | " + " | ".join(cells))


def _console_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, dict):
        return ", ".join(
            f"k={key}:{number:.3f}" if number is not None else f"k={key}:n/a"
            for key, number in value.items()
        )
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _exit_code(records: list[dict]) -> int:
    if any(
        r.get("system") == "pipeline"
        and (
            r.get("verdict", {}).get("policy_violation")
            or r.get("verdict", {}).get("unconfirmed_write")
            or (r.get("injection") and r.get("verdict", {}).get("mutated"))
        )
        for r in records
    ):
        return 2
    if any(r["status"] in {"error", "infra_error"} for r in records):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
