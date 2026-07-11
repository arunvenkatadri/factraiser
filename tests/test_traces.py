import pytest

from factraiser.traces import TraceLog


@pytest.fixture
def log(config):
    return TraceLog(config.memory_root)


def test_recall_then_outcome_roundtrip(log):
    trace_id = log.log_recall("alice", "postgres failover", ["mem-1", "mem-2"])
    assert trace_id.startswith("tr-")

    event = log.log_outcome("alice", trace_id, "success", "runbook worked")
    # memory_ids denormalized from the recall event
    assert event["memory_ids"] == ["mem-1", "mem-2"]

    events = list(log.iter_events("alice"))
    assert [e["event"] for e in events] == ["recall", "outcome"]


def test_outcome_requires_known_trace_or_explicit_ids(log):
    with pytest.raises(KeyError):
        log.log_outcome("alice", "tr-nope", "failure")
    event = log.log_outcome("alice", "tr-nope", "failure", memory_ids=["mem-9"])
    assert event["memory_ids"] == ["mem-9"]


def test_invalid_result_rejected(log):
    trace_id = log.log_recall("alice", "q", ["mem-1"])
    with pytest.raises(ValueError):
        log.log_outcome("alice", trace_id, "great")


def test_traces_are_per_user(log):
    log.log_recall("alice", "secret project", ["mem-1"])
    assert list(log.iter_events("bob")) == []


def test_aggregate_counts_and_misleading(log):
    t1 = log.log_recall("alice", "q1", ["mem-1"])
    log.log_outcome("alice", t1, "success")
    t2 = log.log_recall("bob", "q2", ["mem-1", "mem-2"])
    log.log_outcome("bob", t2, "misleading", "runbook out of date")

    stats = log.aggregate(["alice", "bob"])
    assert stats["mem-1"].recalls == 2
    assert stats["mem-1"].outcomes["success"] == 1
    assert stats["mem-1"].outcomes["misleading"] == 1
    assert stats["mem-2"].outcomes["misleading"] == 1
    assert stats["mem-1"].last_used  # populated
