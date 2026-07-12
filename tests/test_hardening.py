"""Sweep tests: path traversal, input caps, corrupted-data resilience."""

import json

import pytest

from factraiser import server
from factraiser.config import save_config
from factraiser.naming import check_name
from factraiser.store import StoreError
from factraiser.traces import TraceLog


# -- name validation ---------------------------------------------------------

@pytest.mark.parametrize("bad", ["../evil", "a/b", "..", ".hidden", "", "x" * 65, "a\\b"])
def test_check_name_rejects_path_escapes(bad):
    with pytest.raises(ValueError):
        check_name(bad)


@pytest.mark.parametrize("good", ["alice", "platform", "team-1", "a.b_c", "20260711-x-abc123"])
def test_check_name_accepts_normal_names(good):
    assert check_name(good) == good


def test_scope_dir_rejects_traversal(store):
    with pytest.raises(StoreError):
        store.scope_dir("team", team="../org")
    with pytest.raises(StoreError):
        store.scope_dir("personal", user="../../etc")


def test_hostile_frontmatter_id_cannot_escape(store):
    memory = store.save(title="t", content="c", author="alice", scope="personal")
    memory.id = "../../../etc/passwd"
    with pytest.raises(StoreError):
        store.delete(memory)


def test_tracelog_rejects_bad_user(config):
    log = TraceLog(config.memory_root)
    with pytest.raises(ValueError):
        log.log_recall("../alice", "q", ["m"])
    with pytest.raises(ValueError):
        list(log.iter_events("../alice"))


# -- corrupted trace data ----------------------------------------------------

def test_corrupted_trace_lines_are_skipped(config):
    log = TraceLog(config.memory_root)
    trace = log.log_recall("alice", "q", ["mem-1"])
    log.log_outcome("alice", trace, "success")

    trace_file = next((log.root / "alice").glob("*.jsonl"))
    with trace_file.open("a") as f:
        f.write("{not json}\n")
        f.write('"a bare string"\n')
        f.write(json.dumps({"event": "outcome", "ts": "not-a-date", "result": "success",
                            "memory_ids": ["mem-1"], "user": "alice"}) + "\n")

    stats = log.aggregate(["alice"])
    # good events counted; junk skipped; bad-timestamp outcome counted without decay
    assert stats["mem-1"].outcomes["success"] == 2
    assert stats["mem-1"].recalls == 1


# -- LLM input caps ----------------------------------------------------------

@pytest.fixture
def env(config, tmp_path, monkeypatch):
    config_path = tmp_path / "factraiser.yaml"
    save_config(config, config_path)
    monkeypatch.setenv("FACTRAISER_CONFIG", str(config_path))
    monkeypatch.setenv("FACTRAISER_USER", "alice")
    return config_path


def test_remember_rejects_oversized_and_empty(env):
    assert server.remember(title="", content="x").startswith("INVALID")
    assert server.remember(title="t", content="x" * 200_000).startswith("INVALID")
    assert server.remember(title="t" * 500, content="x").startswith("INVALID")


def test_recall_limit_is_clamped(env):
    server.remember(title="Deploy note", content="deploy stuff", scope="personal")
    assert "Deploy note" in server.recall("deploy", limit=-5)
    assert "Deploy note" in server.recall("deploy", limit=10_000)


def test_bad_identity_rejected(env, monkeypatch):
    monkeypatch.setenv("FACTRAISER_USER", "../root")
    with pytest.raises(RuntimeError):
        server.recall("anything")


def test_teamless_user_signal_counts(env, monkeypatch):
    # zoe is in no team but her outcomes must still feed ranking aggregates
    monkeypatch.setenv("FACTRAISER_USER", "zoe")
    server.remember(title="Zoe note", content="postgres tuning", scope="personal")
    out = server.recall("postgres")
    trace = out.splitlines()[0].removeprefix("trace: ")
    server.record_outcome(trace, "success")
    # a second recall ranks with zoe's own signal included (no crash, hit returned)
    assert "Zoe note" in server.recall("postgres")
