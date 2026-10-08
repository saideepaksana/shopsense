import pytest

from shopsense.bootstrap import build_deps
from shopsense.config import Settings
from shopsense.db.seed import seed
from shopsense.gateway import ReadGateway, WriteGateway
from shopsense.mcp_servers.read_server import create_read_server
from shopsense.mcp_servers.write_server import create_write_server


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "shopsense.db"
    seed(str(path))
    return str(path)


@pytest.fixture
def read_gateway(db_path):
    return ReadGateway(create_read_server(db_path))


@pytest.fixture
def write_gateway(db_path):
    return WriteGateway(create_write_server(db_path))


@pytest.fixture
def settings(db_path):
    return Settings(
        db_path=db_path,
        llm_retries=2,
        max_replans=1,
    )


@pytest.fixture
def deps_factory(db_path, settings):
    def factory(llm):
        return build_deps(db_path, llm, settings)

    return factory
