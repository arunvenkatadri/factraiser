"""Organization configuration: org name, teams, permissions, guardrails.

The whole org is described by a single ``factraiser.yaml``::

    org: acme
    memory_root: memories

    teams:
      platform:
        members: [alice, bob]
        permissions:
          write_org: true
      hr:
        members: [carol]
        permissions:
          write_team: false   # HR notes stay personal by default

    permissions:              # org-wide defaults
      write_team: true
      write_org: false

    guardrails:
      blocked_categories: [pii, secrets, hr, legal]
      custom_blocklist: ["project titan"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_SCOPES = ("personal", "team", "org")
DEFAULT_BLOCKED_CATEGORIES = ["pii", "secrets", "hr", "legal"]


class ConfigError(Exception):
    pass


@dataclass
class Team:
    name: str
    members: list[str] = field(default_factory=list)
    # None means "inherit the org default"
    write_team: bool | None = None
    write_org: bool | None = None


@dataclass
class Guardrails:
    blocked_categories: list[str] = field(
        default_factory=lambda: list(DEFAULT_BLOCKED_CATEGORIES)
    )
    custom_blocklist: list[str] = field(default_factory=list)


@dataclass
class OrgConfig:
    org: str
    memory_root: Path
    teams: dict[str, Team] = field(default_factory=dict)
    default_write_team: bool = True
    default_write_org: bool = False
    guardrails: Guardrails = field(default_factory=Guardrails)
    path: Path | None = None

    def teams_of(self, user: str) -> list[str]:
        return [t.name for t in self.teams.values() if user in t.members]

    def users(self) -> list[str]:
        seen: list[str] = []
        for team in self.teams.values():
            for member in team.members:
                if member not in seen:
                    seen.append(member)
        return seen


def load_config(path: str | Path) -> OrgConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"No config found at {path}. Run `factraiser init <org-name>` first."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    if "org" not in raw:
        raise ConfigError(f"{path}: missing required key 'org'")

    perms = raw.get("permissions") or {}
    teams: dict[str, Team] = {}
    for name, spec in (raw.get("teams") or {}).items():
        spec = spec or {}
        tperms = spec.get("permissions") or {}
        teams[name] = Team(
            name=name,
            members=list(spec.get("members") or []),
            write_team=tperms.get("write_team"),
            write_org=tperms.get("write_org"),
        )

    graw = raw.get("guardrails") or {}
    guardrails = Guardrails(
        blocked_categories=list(
            graw.get("blocked_categories", DEFAULT_BLOCKED_CATEGORIES)
        ),
        custom_blocklist=list(graw.get("custom_blocklist") or []),
    )

    memory_root = Path(raw.get("memory_root", "memories"))
    if not memory_root.is_absolute():
        memory_root = path.parent / memory_root

    return OrgConfig(
        org=raw["org"],
        memory_root=memory_root,
        teams=teams,
        default_write_team=bool(perms.get("write_team", True)),
        default_write_org=bool(perms.get("write_org", False)),
        guardrails=guardrails,
        path=path,
    )


def save_config(config: OrgConfig, path: str | Path) -> None:
    path = Path(path)
    teams: dict = {}
    for team in config.teams.values():
        spec: dict = {"members": list(team.members)}
        tperms = {}
        if team.write_team is not None:
            tperms["write_team"] = team.write_team
        if team.write_org is not None:
            tperms["write_org"] = team.write_org
        if tperms:
            spec["permissions"] = tperms
        teams[team.name] = spec

    raw = {
        "org": config.org,
        "memory_root": str(
            config.memory_root.relative_to(path.parent)
            if config.memory_root.is_relative_to(path.parent)
            else config.memory_root
        ),
        "teams": teams,
        "permissions": {
            "write_team": config.default_write_team,
            "write_org": config.default_write_org,
        },
        "guardrails": {
            "blocked_categories": config.guardrails.blocked_categories,
            "custom_blocklist": config.guardrails.custom_blocklist,
        },
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
