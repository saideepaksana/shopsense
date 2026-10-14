import json
from datetime import datetime, timezone
from pathlib import Path

from shopsense.evaluation.metrics import aggregate

METRIC_NAMES = (
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
    "simulator_tokens",
    "error_count",
    "infra_error_count",
)


def write_report(path: Path, metadata: dict, records: list[dict], trials: int) -> tuple[Path, Path]:
    metrics = aggregate(records, trials)
    payload = {"metadata": metadata, "metrics": metrics, "trials": records}
    json_path = path.with_suffix(".json")
    markdown_path = path.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    markdown_path.write_text(render_markdown(payload))
    return json_path, markdown_path


def render_markdown(payload: dict) -> str:
    metadata = payload["metadata"]
    lines = [
        "# ShopSense live evaluation",
        "",
        f"Model: {metadata.get('model', 'unknown')}  ",
        f"Provider host: {metadata.get('provider_host', 'unknown')}  ",
        f"Date: {metadata.get('created_at', '')}  ",
        f"Trials per scenario: {metadata.get('trials', '')}  ",
        f"Clock date: {metadata.get('clock_date', '')}",
        "",
    ]
    if metadata.get("user") == "simulated":
        lines.insert(
            2,
            f"Customer: LLM-simulated (temperature {metadata.get('simulator_temperature', '')})  ",
        )
    metrics = payload["metrics"]
    overall = {system: groups["overall"] for system, groups in metrics.items()}
    lines.extend(["## Summary", "", _table("Overall", overall), ""])
    if "baseline" in overall and overall["baseline"].get("stop_reasons") is not None:
        reasons = overall["baseline"]["stop_reasons"]
        order = ("replied", "invalid_output", "unknown_action", "bad_tool_call", "max_steps")
        lines.extend(
            [
                "Baseline stop reasons: "
                + ", ".join(f"{reason}={reasons.get(reason, 0)}" for reason in order),
                "",
            ]
        )
    categories = sorted(
        {category for groups in metrics.values() for category in groups["categories"]}
    )
    for category in categories:
        columns = {
            system: groups["categories"].get(category, {}) for system, groups in metrics.items()
        }
        lines.extend([_table(category, columns), ""])
    lines.extend(["## Failures", ""])
    failures = [r for r in payload["trials"] if r["status"] in {"fail", "error", "infra_error"}]
    if not failures:
        lines.append("No failed trials.")
    for record in failures:
        reasons = list(record.get("verdict", {}).get("checks", []))
        if record.get("verdict", {}).get("policy_violation"):
            reasons.append("policy_violation")
        if record.get("verdict", {}).get("unconfirmed_write"):
            reasons.append("unconfirmed_write")
        if record.get("error"):
            reasons.append("error: " + record["error"])
        lines.extend(
            [
                f"### {record['system']} {record['scenario']} trial {record['trial']}",
                "",
                "; ".join(reasons) or record["status"],
                "",
            ]
        )
        for turn in record.get("turns", []):
            lines.extend(
                [f"- Customer: {turn['user']}", f"  Assistant ({turn['outcome']}): {turn['text']}"]
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _table(title: str, groups: dict) -> str:
    columns = list(groups)
    lines = [
        f"### {title}",
        "",
        "| Metric | " + " | ".join(columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    for metric in METRIC_NAMES:
        values = [groups[column].get(metric, "n/a") for column in columns]
        lines.append(f"| {metric} | " + " | ".join(_format(value) for value in values) + " |")
    return "\n".join(lines)


def _format(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, dict):
        return (
            ", ".join(
                f"k={key}: {number:.3f}" if number is not None else f"k={key}: n/a"
                for key, number in value.items()
            )
            or "n/a"
        )
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
