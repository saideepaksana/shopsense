import uuid
from typing import Any

from shopsense import audit
from shopsense.baseline import BaselineSession
from shopsense.bootstrap import Deps, build_deps
from shopsense.bootstrap import build_baseline_session as build_baseline
from shopsense.config import Settings, load_settings
from shopsense.graph import build_graph
from shopsense.llm import LLM, LLMUnavailableError, build_llm
from shopsense.models import Intent, Reply
from shopsense.trace import build_trace


class Session:
    def __init__(self, customer_id: str, deps: Deps, graph: Any) -> None:
        self.customer_id = customer_id
        self.deps = deps
        self.graph = graph
        self.pending_plan_id = None
        self.prior_intent: Intent | None = None

    def send(self, text: str) -> Reply:
        before = self.deps.tool_call_count
        usage_before = self.deps.llm.usage()
        event_count = len(self.deps.recorder.events)
        confirmation = self._get_confirmation(text)
        if isinstance(confirmation, Reply):
            confirmation.trace = {"outcome": confirmation.outcome}
            return confirmation
        run_id = uuid.uuid4().hex
        try:
            result = self._invoke_graph(text, run_id, confirmation)
        except LLMUnavailableError as exc:
            usage_delta, node_ms = self._measure_turn(usage_before, event_count)
            return self._unavailable_reply(
                run_id, before, str(exc), usage_delta, node_ms
            )
        usage_delta, node_ms = self._measure_turn(usage_before, event_count)
        self._update_state(result, confirmation)
        reply = self._build_reply(result, before)
        reply.trace = build_trace(
            result,
            usage_delta,
            node_ms,
            self.deps.tool_call_count - before,
        )
        return reply

    def _get_confirmation(self, text: str) -> str | Reply | None:
        if not self.pending_plan_id:
            return None
        confirmation = self._parse_confirmation(text)
        if confirmation:
            return confirmation
        return Reply(
            'Please reply "yes" to confirm or "no" to cancel.',
            None,
            "awaiting_confirmation",
            [],
            0,
            uuid.uuid4().hex,
        )

    def _invoke_graph(self, text: str, run_id: str, confirmation: str | None) -> dict:
        return self.graph.invoke(
            {
                "run_id": run_id,
                "customer_id": self.customer_id,
                "message": text,
                "prior_intent": self.prior_intent,
                "pending_plan_id": self.pending_plan_id,
                "confirmation": confirmation,
            }
        )

    def _unavailable_reply(
        self,
        run_id: str,
        before: int,
        error: str,
        usage_delta: dict[str, int | float],
        node_ms: dict[str, float],
    ) -> Reply:
        api_key = self.deps.settings.llm_api_key
        if api_key:
            error = error.replace(api_key, "[redacted]")
        audit.record(
            self.deps.db_path,
            run_id,
            self.customer_id,
            "llm_unavailable",
            detail={"error": error},
        )
        reply = Reply(
            "The assistant is temporarily unavailable. No changes were made.",
            None,
            "llm_unavailable",
            [],
            self.deps.tool_call_count - before,
            run_id,
            error,
        )
        reply.trace = {
            "outcome": "llm_unavailable",
            "error": error,
            "llm_calls": usage_delta.get("calls", 0),
            "llm_ms": usage_delta.get("llm_milliseconds", 0),
            "tool_calls": self.deps.tool_call_count - before,
        }
        if node_ms:
            reply.trace["node_ms"] = node_ms
        return reply

    def _measure_turn(
        self, usage_before: dict[str, int | float], event_count: int
    ) -> tuple[dict[str, int | float], dict[str, float]]:
        usage_after = self.deps.llm.usage()
        usage_delta = {
            key: usage_after.get(key, 0) - usage_before.get(key, 0)
            for key in ("calls", "llm_milliseconds", "prompt_tokens", "completion_tokens")
        }
        node_ms: dict[str, float] = {}
        for event in self.deps.recorder.events[event_count:]:
            if event["name"] != "llm.complete":
                node_ms[event["name"]] = node_ms.get(event["name"], 0) + event["duration_ms"]
        return usage_delta, node_ms

    def _update_state(self, result: dict, confirmation: str | None) -> None:
        self.pending_plan_id = result.get("pending_plan_id")
        if confirmation is not None or result.get("outcome") in {
            "stale",
            "rejected",
            "blocked",
            "executed",
            "execution_failed",
        }:
            self.pending_plan_id = None
        self.prior_intent = result.get("intent") if result.get("outcome") == "clarify" else None

    def _build_reply(self, result: dict, before: int) -> Reply:
        calls = self.deps.tool_call_count - before
        plan = result.get("plan")
        return Reply(
            result["reply_text"],
            plan.decision if plan else None,
            result["outcome"],
            plan.cited_clause_ids if plan else [],
            calls,
            result["run_id"],
        )

    @staticmethod
    def _parse_confirmation(text: str) -> str | None:
        normalized = text.strip().lower().rstrip(".!")
        if normalized in {"yes", "y"}:
            return "yes"
        if normalized in {"no", "n"}:
            return "no"
        return None


def create_session(
    customer_id: str,
    db_path: str | None = None,
    llm: LLM | None = None,
    settings: Settings | None = None,
) -> Session:
    settings = settings or load_settings()
    deps = build_deps(db_path or settings.db_path, llm or build_llm(settings), settings)
    return Session(customer_id, deps, build_graph(deps))


def create_baseline_session(
    customer_id: str,
    db_path: str | None = None,
    llm: LLM | None = None,
    settings: Settings | None = None,
) -> BaselineSession:
    settings = settings or load_settings()
    return build_baseline(
        customer_id,
        db_path or settings.db_path,
        llm or build_llm(settings),
        settings,
    )
