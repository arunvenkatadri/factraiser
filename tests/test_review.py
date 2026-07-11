from datetime import datetime, timedelta, timezone

from factraiser.review import build_report, render_report
from factraiser.search import search
from factraiser.traces import TraceLog


def _outcome(log, user, memory_id, result, note=""):
    trace = log.log_recall(user, "q", [memory_id])
    log.log_outcome(user, trace, result, note)


def test_usefulness_reranks_equal_relevance(config, store):
    good = store.save(title="Deploy guide", content="x", author="alice",
                      scope="team", team="platform")
    bad = store.save(title="Deploy guide", content="x", author="alice",
                     scope="team", team="platform")
    log = TraceLog(config.memory_root)
    _outcome(log, "alice", good.id, "success")
    _outcome(log, "alice", bad.id, "misleading", "wrong flag order")

    stats = log.aggregate(["alice"])
    mult = {mid: s.multiplier() for mid, s in stats.items()}
    assert mult[good.id] > 1.0 > mult[bad.id] >= 0.4

    hits = search("deploy guide", store.iter_accessible("alice", ["platform"]),
                  usefulness=mult)
    assert hits[0].memory.id == good.id
    assert hits[-1].memory.id == bad.id


def test_decay_shrinks_old_outcomes(config, store):
    log = TraceLog(config.memory_root)
    _outcome(log, "alice", "mem-1", "success")
    fresh = log.aggregate(["alice"]) ["mem-1"].decayed_net
    year_later = datetime.now(timezone.utc) + timedelta(days=360)
    aged = log.aggregate(["alice"], now=year_later)["mem-1"].decayed_net
    assert 0 < aged < fresh / 3  # two half-lives -> ~1/4


def test_report_sections(config, store):
    log = TraceLog(config.memory_root)
    misleading = store.save(title="Old runbook", content="x", author="alice",
                            scope="team", team="platform")
    promotable = store.save(title="Great tip", content="x", author="alice",
                            scope="team", team="platform")
    stale = store.save(title="Never used", content="x", author="alice", scope="org")
    personal = store.save(title="My note", content="x", author="alice", scope="personal")

    _outcome(log, "alice", misleading.id, "misleading", "step 2 outdated")
    _outcome(log, "alice", promotable.id, "success")
    _outcome(log, "bob", promotable.id, "success")

    report = build_report(config, store, "alice")
    assert [m.id for m, _ in report.fix_or_archive] == [misleading.id]
    assert report.fix_or_archive[0][1].misleading_notes == ["step 2 outdated"]
    assert stale.id in [m.id for m in report.stale]
    assert personal.id not in [m.id for m in report.stale]  # personal never composted
    assert [m.id for m, _ in report.promote] == [promotable.id]

    text = render_report(report, 90)
    assert "step 2 outdated" in text
    assert "promote_memory" in text


def test_single_user_success_is_not_promotable(config, store):
    log = TraceLog(config.memory_root)
    memory = store.save(title="Tip", content="x", author="alice",
                        scope="team", team="platform")
    _outcome(log, "alice", memory.id, "success")
    report = build_report(config, store, "alice")
    assert report.promote == []
