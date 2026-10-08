from dataclasses import dataclass

from shopsense.gateway import ReadGateway, WriteGateway
from shopsense.mcp_servers.read_server import create_read_server
from shopsense.mcp_servers.write_server import create_write_server
from shopsense.policy.loader import load_clauses
from shopsense.policy.retriever import PolicyRetriever
from shopsense.telemetry import MeteredLLM, Recorder


@dataclass
class Deps:
    settings: object
    llm: object
    read_gateway: object
    write_gateway: object
    retriever: object
    db_path: str
    recorder: Recorder | None = None

    @property
    def tool_call_count(self):
        return self.read_gateway.call_count + self.write_gateway.call_count


def build_deps(db_path, llm, settings):
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
