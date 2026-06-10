"""Who may write to which memory tier.

Reads are structural: a user always reads their own personal memory, their
teams' memory, and org memory. Writes are policy: org defaults can be
overridden per team (e.g. "HR never writes to shared memory", "platform may
write to org memory").
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import OrgConfig


@dataclass
class Decision:
    allowed: bool
    reason: str


def can_write(config: OrgConfig, user: str, scope: str, team: str | None = None) -> Decision:
    if scope == "personal":
        return Decision(True, "personal memory is always writable by its owner")

    user_teams = config.teams_of(user)

    if scope == "team":
        if not team:
            return Decision(False, "team scope requires a team name")
        if team not in config.teams:
            return Decision(False, f"unknown team {team!r}")
        if user not in config.teams[team].members:
            return Decision(False, f"{user} is not a member of team {team!r}")
        override = config.teams[team].write_team
        allowed = config.default_write_team if override is None else override
        if not allowed:
            return Decision(False, f"team {team!r} policy forbids writing to team memory")
        return Decision(True, f"{user} may write to team {team!r} memory")

    if scope == "org":
        # A user may write to org memory if any of their teams allows it.
        if not user_teams:
            return Decision(False, f"{user} is not a member of any team")
        for team_name in user_teams:
            override = config.teams[team_name].write_org
            allowed = config.default_write_org if override is None else override
            if allowed:
                return Decision(True, f"team {team_name!r} grants {user} org-memory write access")
        return Decision(False, f"none of {user}'s teams may write to org memory")

    return Decision(False, f"unknown scope {scope!r}")
