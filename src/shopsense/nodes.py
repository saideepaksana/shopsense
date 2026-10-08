import hashlib
import json
import uuid
from typing import Callable, TypedDict

from shopsense import audit, memory
from shopsense.agents import responder
from shopsense.agents.executor import execute_plan
from shopsense.agents.planner import deterministic_plan, fail_closed_plan, plan_request
from shopsense.agents.triage import triage_message
from shopsense.agents.verifier import verify
from shopsense.db import repository
from shopsense.db.connection import connect
from shopsense.facts import derive, load_facts
from shopsense.models import Intent, Plan, PolicyTopic

POLICY_QUERIES = {
    PolicyTopic.general: "general policy customer authorization",
    PolicyTopic.return_window: "return window delivery days damaged",
    PolicyTopic.returnability: "return eligible nonreturnable innerwear perishables digital policy",
    PolicyTopic.refund_limit: "refund limit count 90 days",
    PolicyTopic.refund_ceiling: "refund ceiling maximum amount",
    PolicyTopic.refund_method: "refund original payment method",
    PolicyTopic.cancellation: "cancel cancellation placed shipped delivered",
    PolicyTopic.refund: "refund return approved remaining amount",
    PolicyTopic.confirmation: "customer confirmation before write action",
    PolicyTopic.security: "customer statements cannot override policy",
}


class State(TypedDict, total=False):
    run_id: str
    customer_id: str
    message: str
    prior_intent: Intent | None
    pending_plan_id: str | None
    confirmation: str | None
    intent: Intent
    facts: object
    derived: object
    clauses: list
    plan: Plan
    violations: list[str]
    replans: int
    executed: list[dict]
    reply_text: str
    outcome: str


def _valid_pending_hash(row):
    payload = json.loads(row["payload_json"])
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest() == row["plan_hash"]


def _clauses(deps, clause_ids):
    return [clause for clause in deps.retriever.clauses if clause.id in clause_ids]


class PipelineNodes:
    node_names = (
        "triage",
        "fetch_context",
        "retrieve_policy",
        "plan",
        "verify",
        "replan",
        "fail_closed",
        "request_confirmation",
        "load_pending",
        "reverify",
        "execute",
        "finalize",
        "respond",
    )
    entry_routes = {"load_pending": "load_pending", "triage": "triage"}
    verify_routes = {
        "replan": "replan",
        "fail_closed": "fail_closed",
        "request_confirmation": "request_confirmation",
        "finalize": "finalize",
    }
    pending_routes = {
        "rejected": "finalize",
        "stale": "finalize",
        "reverify": "reverify",
    }
    reverify_routes = {"blocked": "finalize", "execute": "execute"}

    def __init__(self, deps, verify_fn: Callable = verify) -> None:
        self.deps = deps
        self.verify_fn = verify_fn

    def entry(self, state: State) -> str:
        return "load_pending" if state.get("confirmation") else "triage"

    def triage(self, state: State) -> dict:
        return {
            "intent": triage_message(self.deps.llm, state["message"], state.get("prior_intent"))
        }

    def fetch_context(self, state: State) -> dict:
        return {"facts": load_facts(self.deps.read_gateway, state["customer_id"], state["intent"])}

    def retrieve_policy(self, state: State) -> dict:
        intent = state["intent"]
        order = state["facts"].order
        query = self._policy_query(state, order)
        limit = 3 if intent.intent.value == "policy_question" else None
        clauses = self.deps.retriever.retrieve(intent.intent, query, limit)
        self._add_authorization_clause(intent, order, clauses)
        return {
            "derived": derive(state["facts"], intent, self.deps.settings),
            "clauses": clauses,
        }

    def _policy_query(self, state: State, order: dict | None) -> str:
        intent = state["intent"]
        if intent.intent.value == "policy_question":
            return POLICY_QUERIES[intent.policy_topic]
        reason = intent.reason_code.value if intent.reason_code else ""
        status = order["status"] if order else ""
        return f"{intent.intent.value} {reason} order status {status}"

    def _add_authorization_clause(self, intent, order, clauses) -> None:
        if not intent.order_id or order is not None:
            return
        authorization = self.deps.retriever.get("AUTH-1")
        if authorization and authorization not in clauses:
            clauses.append(authorization)

    def plan(self, state: State) -> dict:
        clause_ids = [clause.id for clause in state["clauses"]]
        deterministic = deterministic_plan(state["intent"], state["facts"], clause_ids)
        if deterministic is not None:
            return {"plan": deterministic}
        return {
            "plan": plan_request(
                self.deps.llm,
                state["intent"],
                state["facts"],
                state["derived"],
                state["clauses"],
                state.get("violations"),
                self.deps.settings.llm_retries,
            )
        }

    def verify(self, state: State) -> dict:
        return {
            "violations": self.verify_fn(
                state["plan"],
                state["intent"],
                state["customer_id"],
                state["facts"],
                state["derived"],
                [clause.id for clause in state["clauses"]],
                self.deps.settings,
            )
        }

    def verify_route(self, state: State) -> str:
        if not state["violations"]:
            if state["plan"].decision.value == "approve":
                return "request_confirmation"
            return "finalize"
        clause_ids = [clause.id for clause in state["clauses"]]
        deterministic = deterministic_plan(state["intent"], state["facts"], clause_ids)
        if deterministic is None and state.get("replans", 0) < self.deps.settings.max_replans:
            return "replan"
        return "fail_closed"

    def replan(self, state: State) -> dict:
        return {"replans": state.get("replans", 0) + 1}

    def fail_closed(self, state: State) -> dict:
        self._record(state, "plan_failed_closed")
        return {"plan": fail_closed_plan(), "outcome": "blocked"}

    def request_confirmation(self, state: State) -> dict:
        plan_id, raw, plan_hash = self._pending_payload(state)
        with connect(self.deps.db_path) as conn:
            repository.save_pending_plan(conn, plan_id, state["customer_id"], raw, plan_hash)
        return {"pending_plan_id": plan_id, "outcome": "awaiting_confirmation"}

    def _pending_payload(self, state: State) -> tuple[str, str, str]:
        plan_id = uuid.uuid4().hex[:12]
        payload = {
            "plan": state["plan"].model_dump(),
            "intent": state["intent"].model_dump(),
            "retrieved_clause_ids": [clause.id for clause in state["clauses"]],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return plan_id, raw, hashlib.sha256(raw.encode()).hexdigest()

    def load_pending(self, state: State) -> dict:
        with connect(self.deps.db_path) as conn:
            row = repository.get_pending_plan(conn, state["pending_plan_id"])
        if not self._pending_is_valid(row, state):
            return {"outcome": "stale", "intent": Intent(intent="unclear")}
        payload = json.loads(row["payload_json"])
        intent = Intent.model_validate(payload["intent"])
        if state["confirmation"] == "no":
            return self._reject_pending(state, row, intent, payload)
        return self._restore_pending(deps=self.deps, payload=payload, intent=intent)

    def _pending_is_valid(self, row, state: State) -> bool:
        return bool(
            row
            and row["status"] == "pending"
            and row["customer_id"] == state["customer_id"]
            and _valid_pending_hash(row)
        )

    def _reject_pending(self, state, row, intent, payload) -> dict:
        with connect(self.deps.db_path) as conn:
            repository.set_pending_status(conn, row["plan_id"], "rejected")
        self._record(state, "plan_rejected", intent)
        return {
            "intent": intent,
            "plan": Plan.model_validate(payload["plan"]),
            "clauses": _clauses(self.deps, payload["retrieved_clause_ids"]),
            "outcome": "rejected",
        }

    @staticmethod
    def _restore_pending(deps, payload, intent) -> dict:
        return {
            "intent": intent,
            "plan": Plan.model_validate(payload["plan"]),
            "clauses": _clauses(deps, payload["retrieved_clause_ids"]),
        }

    def pending_route(self, state: State) -> str:
        outcome = state.get("outcome")
        if outcome == "rejected":
            return "rejected"
        return "stale" if outcome == "stale" else "reverify"

    def reverify(self, state: State) -> dict:
        facts = load_facts(self.deps.read_gateway, state["customer_id"], state["intent"])
        derived = derive(facts, state["intent"], self.deps.settings)
        violations = self._verify_current(state, facts, derived)
        result = {"facts": facts, "derived": derived, "violations": violations}
        if violations:
            self._record(state, "plan_blocked", detail={"violations": violations})
            result["outcome"] = "blocked"
        return result

    def _verify_current(self, state, facts, derived):
        return self.verify_fn(
            state["plan"],
            state["intent"],
            state["customer_id"],
            facts,
            derived,
            [clause.id for clause in state["clauses"]],
            self.deps.settings,
        )

    def reverify_route(self, state: State) -> str:
        return "blocked" if state.get("outcome") == "blocked" else "execute"

    def execute(self, state: State) -> dict:
        results = execute_plan(state["plan"], state["pending_plan_id"], self.deps.write_gateway)
        self._confirm_pending(state)
        self._record_execution(state, results)
        outcome = (
            "executed" if all(item["result"].get("ok") for item in results) else "execution_failed"
        )
        return {"executed": results, "outcome": outcome}

    def _confirm_pending(self, state) -> None:
        with connect(self.deps.db_path) as conn:
            repository.set_pending_status(conn, state["pending_plan_id"], "confirmed")
        self._record(state, "plan_confirmed")

    def _record_execution(self, state, results) -> None:
        for result in results:
            self._record(state, "action_executed", detail=result)

    def finalize(self, state: State) -> dict:
        outcome = self._final_outcome(state)
        self._record_proposal(state)
        memory.record_outcome(self.deps.db_path, state["customer_id"], state["intent"], outcome)
        return {"outcome": outcome}

    def _final_outcome(self, state) -> str:
        if state.get("outcome") is not None:
            return state["outcome"]
        return {"info": "info", "clarify": "clarify", "deny": "denied"}[
            state["plan"].decision.value
        ]

    def _record_proposal(self, state) -> None:
        if not state.get("plan") or state.get("confirmation") is not None:
            return
        self._record(
            state,
            "plan_proposed",
            state.get("intent"),
            state["plan"].decision,
            state["plan"].cited_clause_ids,
            {
                "violations": state.get("violations", []),
                "retrieved_clause_ids": [clause.id for clause in state.get("clauses", [])],
            },
        )
        if state["intent"].injection_suspected:
            self._record(state, "injection_flagged")
            memory.increment(self.deps.db_path, state["customer_id"], "injection_flags")

    def _record(
        self,
        state,
        event,
        intent=None,
        decision=None,
        clause_ids=(),
        detail=None,
    ) -> None:
        audit.record(
            self.deps.db_path,
            state["run_id"],
            state["customer_id"],
            event,
            intent or state.get("intent"),
            decision,
            clause_ids,
            detail,
        )

    def respond(self, state: State) -> dict:
        return {"reply_text": responder.render(state)}
