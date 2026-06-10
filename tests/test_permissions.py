from factraiser.permissions import can_write


def test_personal_always_writable(config):
    assert can_write(config, "anyone", "personal").allowed


def test_team_write_requires_membership(config):
    assert can_write(config, "alice", "team", "platform").allowed
    assert not can_write(config, "dave", "team", "platform").allowed


def test_team_policy_can_forbid_team_writes(config):
    # HR has write_team: false — carol can't commit to her own team's memory
    decision = can_write(config, "carol", "team", "hr")
    assert not decision.allowed
    assert "policy" in decision.reason


def test_org_write_denied_by_default(config):
    # sales inherits the org default (write_org: false)
    assert not can_write(config, "dave", "org").allowed


def test_org_write_granted_by_team_override(config):
    assert can_write(config, "alice", "org").allowed


def test_unknown_team_and_scope(config):
    assert not can_write(config, "alice", "team", "nope").allowed
    assert not can_write(config, "alice", "galaxy").allowed
