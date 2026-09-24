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
        f.write(json.dumps({"event": "outcome", "trace_id": "tr-other", "ts": "not-a-date",
                            "result": "success", "memory_ids": ["mem-1"],
                            "user": "alice"}) + "\n")
        f.write(json.dumps({"event": "outcome", "ts": "2026-01-01T00:00:00+00:00",
                            "result": "success", "memory_ids": ["mem-1"]}) + "\n")  # no trace_id

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


# -- guardrails cover every shared field -------------------------------------

def test_secret_in_tags_is_blocked(env):
    result = server.remember(title="Deploy", content="notes", scope="org",
                             tags=["AKIAABCDEFGHIJKLMNOP"])
    assert result.startswith("BLOCKED")


def test_promote_rescans_tags(env, store):
    memory = store.save(title="Deploy", content="notes", author="alice",
                        scope="personal", tags=["password=hunter2"])
    assert server.promote_memory(memory.id, "team", team="platform").startswith("BLOCKED")


def test_misleading_note_is_guardrail_scanned(env):
    server.remember(title="Runbook", content="failover steps", scope="team", team="platform")
    trace = server.recall("failover").splitlines()[0].removeprefix("trace: ")
    result = server.record_outcome(trace, "misleading", "ask jane.doe@example.com")
    assert result.startswith("BLOCKED")
    assert server.record_outcome(trace, "misleading", "step 2 is outdated").startswith("Recorded")


# -- corrupted memory files --------------------------------------------------

@pytest.mark.parametrize("raw", [
    b"---\nfoo: [unclosed\n---\nbody\n",          # invalid YAML
    b"---\n- a list\n---\nbody\n",                # frontmatter not a mapping
    b"---\ntitle: deploy\ntags: 5\n---\nbody\n",  # tags not a list
    b"---\ntitle: deploy\n---\n\xff\xfe",          # not UTF-8
])
def test_corrupted_memory_file_is_skipped(env, store, raw):
    server.remember(title="Deploy guide", content="deploy steps", scope="org")
    (store.scope_dir("org") / "corrupt.md").write_bytes(raw)
    assert "Deploy guide" in server.recall("deploy")
    assert "Deploy guide" in server.list_memories()
    assert "Deploy guide" in server.shared_context()


def test_location_decides_scope_not_frontmatter(store):
    directory = store.scope_dir("org")
    directory.mkdir(parents=True)
    (directory / "spoof.md").write_text(
        "---\nid: spoof\ntitle: t\nauthor: bob\nscope: personal\n---\nx\n")
    [memory] = list(store.iter_accessible("alice", []))
    assert memory.scope == "org"


def test_personal_author_is_the_directory_owner(store):
    directory = store.scope_dir("personal", user="alice")
    directory.mkdir(parents=True)
    (directory / "m.md").write_text(
        "---\nid: m\ntitle: t\nauthor: bob\nscope: personal\n---\nx\n")
    [memory] = list(store.iter_accessible("alice", []))
    assert memory.author == "alice"


# -- outcome manipulation ----------------------------------------------------

def test_repeated_outcomes_on_one_trace_count_once(config):
    log = TraceLog(config.memory_root)
    trace = log.log_recall("alice", "q", ["mem-1"])
    for _ in range(50):
        log.log_outcome("alice", trace, "misleading")
    log.log_outcome("alice", trace, "success")  # latest verdict wins
    stats = log.aggregate(["alice"])["mem-1"]
    assert stats.outcomes["misleading"] == 0
    assert stats.outcomes["success"] == 1


def test_one_user_cannot_sink_a_memory_alone(config):
    log = TraceLog(config.memory_root)
    for _ in range(50):
        trace = log.log_recall("alice", "q", ["mem-1"])
        log.log_outcome("alice", trace, "misleading")
    solo = log.aggregate(["alice"])["mem-1"].multiplier()
    for user in ("bob", "carol", "dave", "erin"):
        for _ in range(3):
            trace = log.log_recall(user, "q", ["mem-1"])
            log.log_outcome(user, trace, "misleading")
    crowd = log.aggregate(["alice", "bob", "carol", "dave", "erin"])["mem-1"].multiplier()
    assert solo > 0.6          # a single user's spam has bounded effect
    assert crowd < solo        # broad agreement sinks it further
    assert crowd >= 0.4        # documented floor holds


# -- config validation -------------------------------------------------------

@pytest.mark.parametrize("snippet", [
    "teams:\n  p:\n    permissions:\n      write_org: 'false'\n",
    "permissions:\n  write_org: 'no'\n",
    "teams: [a, b]\n",
    "teams:\n  ../x: {}\n",
    "teams:\n  p:\n    members: ['../root']\n",
    "guardrails:\n  blocked_categories: null\n",
    "guardrails:\n  blocked_categories: [pii, typo]\n",
    "guardrails:\n  custom_blocklist: ['']\n",
])
def test_invalid_config_rejected(tmp_path, snippet):
    from factraiser.config import ConfigError, load_config
    path = tmp_path / "factraiser.yaml"
    path.write_text("org: acme\n" + snippet)
    with pytest.raises(ConfigError):
        load_config(path)


def test_empty_blocklist_term_never_matches():
    from factraiser.config import Guardrails
    from factraiser.guardrails import scan
    assert scan("anything", Guardrails(blocked_categories=[], custom_blocklist=["", "  "])) == []


# -- promotion ---------------------------------------------------------------

def test_promote_must_widen_scope(env, store):
    memory = store.save(title="Tip", content="x", author="bob", scope="team", team="platform")
    assert server.promote_memory(memory.id, "team", team="platform").startswith("INVALID")
    assert server.promote_memory(memory.id, "personal").startswith("INVALID")


def test_promote_records_provenance(env, store):
    memory = store.save(title="Tip", content="x", author="bob", scope="team", team="platform")
    result = server.promote_memory(memory.id, "org")
    promoted_id = result.split("→ ")[1].split()[0]
    promoted = store.get(promoted_id, "alice", ["platform"])
    assert promoted.promoted_from == memory.id
    assert promoted.original_author == "bob"


# -- insights CLI ------------------------------------------------------------

def test_insights_without_anthropic_is_a_clean_error(env, monkeypatch, capsys):
    import builtins
    from factraiser.cli import main
    real_import = builtins.__import__

    def no_anthropic(name, *a, **kw):
        if name == "anthropic":
            raise ImportError("no anthropic")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_anthropic)
    assert main(["--config", str(env), "insights"]) == 1
    assert "pip install" in capsys.readouterr().err


def test_promote_to_unknown_scope_is_denied(env, store):
    memory = store.save(title="Tip", content="x", author="alice", scope="personal")
    assert server.promote_memory(memory.id, "galaxy").startswith("DENIED")
