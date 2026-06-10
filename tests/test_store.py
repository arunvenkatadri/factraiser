from factraiser.store import Memory, MemoryStore


def test_save_and_roundtrip(store):
    saved = store.save(
        title="Deploy runbook",
        content="Always run migrations before deploying the API.",
        author="alice",
        scope="team",
        team="platform",
        tags=["deploy", "runbook"],
    )
    path = store.scope_dir("team", team="platform") / f"{saved.id}.md"
    assert path.exists()

    loaded = Memory.from_markdown(path.read_text())
    assert loaded.title == "Deploy runbook"
    assert loaded.content == "Always run migrations before deploying the API."
    assert loaded.scope == "team"
    assert loaded.team == "platform"
    assert loaded.tags == ["deploy", "runbook"]


def test_personal_memory_is_isolated(store):
    store.save(title="My note", content="alice private", author="alice", scope="personal")
    alice_sees = list(store.iter_accessible("alice", ["platform"]))
    bob_sees = list(store.iter_accessible("bob", ["platform"]))
    assert any(m.title == "My note" for m in alice_sees)
    assert not any(m.title == "My note" for m in bob_sees)


def test_team_memory_visible_to_team_only(store):
    store.save(title="Team tip", content="x", author="alice", scope="team", team="platform")
    assert any(m.title == "Team tip" for m in store.iter_accessible("bob", ["platform"]))
    assert not any(m.title == "Team tip" for m in store.iter_accessible("dave", ["sales"]))


def test_org_memory_visible_to_all(store):
    store.save(title="Org policy", content="x", author="alice", scope="org")
    assert any(m.title == "Org policy" for m in store.iter_accessible("dave", ["sales"]))


def test_get_respects_access(store):
    saved = store.save(title="Secret", content="x", author="alice", scope="personal")
    assert store.get(saved.id, "alice", []) is not None
    assert store.get(saved.id, "bob", ["platform"]) is None
