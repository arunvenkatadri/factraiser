from factraiser.search import search


def test_search_ranks_title_matches_first(store):
    store.save(title="Deploy runbook", content="general notes", author="alice",
               scope="team", team="platform")
    store.save(title="Lunch spots", content="we discussed the deploy once", author="alice",
               scope="team", team="platform")

    hits = search("deploy", store.iter_accessible("alice", ["platform"]))
    assert [h.memory.title for h in hits] == ["Deploy runbook", "Lunch spots"]


def test_search_matches_tags(store):
    store.save(title="Q3 retro", content="notes", author="alice", scope="org",
               tags=["postgres", "incident"])
    hits = search("postgres", store.iter_accessible("bob", ["platform"]))
    assert hits and hits[0].memory.title == "Q3 retro"


def test_search_only_sees_accessible(store):
    store.save(title="Platform deploy", content="x", author="alice",
               scope="team", team="platform")
    hits = search("deploy", store.iter_accessible("dave", ["sales"]))
    assert hits == []


def test_empty_query(store):
    assert search("   ", store.iter_accessible("alice", ["platform"])) == []
