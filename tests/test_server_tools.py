"""End-to-end checks of the MCP tool functions (called directly)."""

import pytest

from factraiser.config import save_config
from factraiser import server


@pytest.fixture
def env(config, tmp_path, monkeypatch):
    config_path = tmp_path / "factraiser.yaml"
    save_config(config, config_path)
    monkeypatch.setenv("FACTRAISER_CONFIG", str(config_path))
    monkeypatch.setenv("FACTRAISER_USER", "alice")
    return config_path


def test_remember_and_recall(env):
    result = server.remember(
        title="Postgres failover",
        content="Promote the replica before failing over the proxy.",
        scope="team",
        team="platform",
    )
    assert result.startswith("Saved ")
    assert "Postgres failover" in server.recall("failover")
    assert "Postgres failover" in server.shared_context()


def test_remember_blocked_by_guardrails(env):
    result = server.remember(
        title="Contact",
        content="Email jane.doe@example.com about the rollout.",
        scope="org",
    )
    assert result.startswith("BLOCKED")
    # personal scope is exempt
    assert server.remember(
        title="Contact", content="Email jane.doe@example.com", scope="personal"
    ).startswith("Saved ")


def test_remember_denied_by_permissions(env, monkeypatch):
    monkeypatch.setenv("FACTRAISER_USER", "dave")  # sales: no org write
    assert server.remember(title="t", content="c", scope="org").startswith("DENIED")


def test_promote_personal_to_team(env):
    saved = server.remember(title="Tip", content="Use make bootstrap.", scope="personal")
    memory_id = saved.split()[1]
    result = server.promote_memory(memory_id, "team", team="platform")
    assert result.startswith("Promoted")


def test_recall_returns_trace_and_outcome_closes_loop(env):
    server.remember(title="Failover runbook", content="Promote replica first.",
                    scope="team", team="platform")
    recalled = server.recall("failover")
    trace_id = recalled.splitlines()[0].removeprefix("trace: ")
    assert trace_id.startswith("tr-")

    assert server.record_outcome(trace_id, "success", "worked").startswith("Recorded success")
    assert "expected one of" in server.record_outcome(trace_id, "great")
    assert server.record_outcome("tr-bogus", "failure").startswith("Unknown trace id")


def test_shared_context_logs_trace(env):
    server.remember(title="Org rule", content="Use SSO everywhere.", scope="team",
                    team="platform")
    assert server.shared_context().startswith("trace: tr-")

