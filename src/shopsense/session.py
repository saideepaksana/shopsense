import uuid

from shopsense import audit
from shopsense.bootstrap import build_deps
from shopsense.config import load_settings
from shopsense.graph import build_graph
from shopsense.llm import LLMUnavailableError, build_llm
from shopsense.models import Reply


class Session:
    def __init__(self, customer_id, deps, graph):
        self.customer_id = customer_id
        self.deps = deps
        self.graph = graph
        self.pending_plan_id = None
        self.prior_intent = None

    def send(self, text):
        before = self.deps.tool_call_count
        confirmation = self._get_confirmation(text)
        if isinstance(confirmation, Reply):
            return confirmation
        run_id = uuid.uuid4().hex
        try:
            result = self._invoke_graph(text, run_id, confirmation)
        except LLMUnavailableError:
            return self._unavailable_reply(run_id, before)
        self._update_state(result, confirmation)
        return self._build_reply(result, before)

    def _get_confirmation(self, text):
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

    def _invoke_graph(self, text, run_id, confirmation):
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

    def _unavailable_reply(self, run_id, before):
        audit.record(self.deps.db_path, run_id, self.customer_id, "llm_unavailable")
        return Reply(
            "The assistant is temporarily unavailable. No changes were made.",
            None,
            "llm_unavailable",
            [],
            self.deps.tool_call_count - before,
            run_id,
        )

    def _update_state(self, result, confirmation):
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

    def _build_reply(self, result, before):
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
    def _parse_confirmation(text):
        normalized = text.strip()
        if normalized == "yes":
            return "yes"
        if normalized == "no":
            return "no"
        return None


def create_session(customer_id, db_path=None, llm=None, settings=None):
    settings = settings or load_settings()
    deps = build_deps(db_path or settings.db_path, llm or build_llm(settings), settings)
    return Session(customer_id, deps, build_graph(deps))
