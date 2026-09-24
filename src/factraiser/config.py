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

from .naming import check_name

VALID_SCOPES = ("personal", "team", "org")
DEFAULT_BLOCKED_CATEGORIES = ["pii", "secrets", "hr", "legal"]


class ConfigError(Exception):
    pass


def _mapping(value, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping, got {type(value).__name__}")
    return value


def _optional_bool(value, where: str) -> bool | None:
    # Strict on purpose: bool("false") is True, and this is a permissions file.
    if value is None or isinstance(value, bool):
        return value
    raise ConfigError(f"{where} must be true or false (unquoted), got {value!r}")


def _string_list(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where} must be a list of strings")
    return list(value)


def _name(value, what: str) -> str:
    try:
        return check_name(value, what)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


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
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: not valid YAML ({exc})") from exc
    if not isinstance(raw, dict) or "org" not in raw:
        raise ConfigError(f"{path}: missing required key 'org'")

    try:
        return _parse(raw, path)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def _parse(raw: dict, path: Path) -> OrgConfig:
    perms = _mapping(raw.get("permissions"), "permissions")
    teams: dict[str, Team] = {}
    for name, spec in _mapping(raw.get("teams"), "teams").items():
        name = _name(name, "team name")
        spec = _mapping(spec, f"teams.{name}")
        tperms = _mapping(spec.get("permissions"), f"teams.{name}.permissions")
        members = _string_list(spec.get("members") or [], f"teams.{name}.members")
        teams[name] = Team(
            name=name,
            members=[_name(m, "user name") for m in members],
            write_team=_optional_bool(tperms.get("write_team"), f"teams.{name}.permissions.write_team"),
            write_org=_optional_bool(tperms.get("write_org"), f"teams.{name}.permissions.write_org"),
        )

    graw = _mapping(raw.get("guardrails"), "guardrails")
    categories = _string_list(
        graw.get("blocked_categories", DEFAULT_BLOCKED_CATEGORIES),
        "guardrails.blocked_categories",
    )
    unknown = sorted(set(categories) - set(DEFAULT_BLOCKED_CATEGORIES))
    if unknown:
        raise ConfigError(
            f"guardrails.blocked_categories: unknown {unknown}; "
            f"expected any of {DEFAULT_BLOCKED_CATEGORIES}"
        )
    blocklist = _string_list(graw.get("custom_blocklist") or [], "guardrails.custom_blocklist")
    if any(not term.strip() for term in blocklist):
        raise ConfigError("guardrails.custom_blocklist must not contain empty terms")
    guardrails = Guardrails(blocked_categories=categories, custom_blocklist=blocklist)

    write_team = _optional_bool(perms.get("write_team"), "permissions.write_team")
    write_org = _optional_bool(perms.get("write_org"), "permissions.write_org")

    memory_root = Path(raw.get("memory_root", "memories"))
    if not memory_root.is_absolute():
        memory_root = path.parent / memory_root

    return OrgConfig(
        org=str(raw["org"]),
        memory_root=memory_root,
        teams=teams,
        default_write_team=True if write_team is None else write_team,
        default_write_org=False if write_org is None else write_org,
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
