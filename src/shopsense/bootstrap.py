from dataclasses import dataclass
from pathlib import Path

from shopsense.baseline import BaselineSession
from shopsense.config import Settings
from shopsense.gateway import ReadGateway, WriteGateway
from shopsense.llm import LLM
from shopsense.mcp_servers.read_server import create_read_server
from shopsense.mcp_servers.write_server import create_write_server
from shopsense.policy.loader import load_clauses
from shopsense.policy.retriever import PolicyRetriever
from shopsense.telemetry import MeteredLLM, Recorder


@dataclass
class Deps:
    settings: Settings
    llm: MeteredLLM
    read_gateway: ReadGateway
    write_gateway: WriteGateway
    retriever: PolicyRetriever
    db_path: str
    recorder: Recorder | None = None

    @property
    def tool_call_count(self):
        return self.read_gateway.call_count + self.write_gateway.call_count


def build_deps(db_path: str, llm: LLM, settings: Settings) -> Deps:
    recorder = Recorder()
    return Deps(
        settings,
        MeteredLLM(llm, recorder),
        ReadGateway(create_read_server(db_path, settings.refund_limit_days)),
        WriteGateway(create_write_server(db_path)),
        PolicyRetriever(load_clauses(settings.policy_path), settings.clause_top_k),
        db_path,
        recorder,
    )


def build_baseline_session(
    customer_id: str, db_path: str, llm: LLM, settings: Settings
) -> BaselineSession:
    deps = build_deps(db_path, llm, settings)
    return BaselineSession(
        customer_id,
        deps.llm,
        deps.read_gateway,
        deps.write_gateway,
        Path(settings.policy_path).read_text(),
        settings.baseline_max_steps,
    )
