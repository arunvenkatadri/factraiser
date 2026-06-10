import pytest

from factraiser.config import Guardrails, OrgConfig, Team
from factraiser.store import MemoryStore


@pytest.fixture
def config(tmp_path):
    return OrgConfig(
        org="acme",
        memory_root=tmp_path / "memories",
        teams={
            "platform": Team(name="platform", members=["alice", "bob"], write_org=True),
            "hr": Team(name="hr", members=["carol"], write_team=False),
            "sales": Team(name="sales", members=["dave"]),
        },
        default_write_team=True,
        default_write_org=False,
        guardrails=Guardrails(custom_blocklist=["project titan"]),
    )


@pytest.fixture
def store(config):
    return MemoryStore(config.memory_root)
