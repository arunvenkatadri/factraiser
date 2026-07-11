"""Filesystem-backed memory store.

Layout under ``memory_root`` (designed to live in a git repo, so the org
repository *is* the memory store)::

    memories/
      org/                    # org-wide memory, readable by everyone
        20260610-deploy-runbook-a1b2c3.md
      teams/
        platform/             # readable by members of `platform`
      users/
        alice/                # personal memory, readable only by alice

Each memory is a markdown file with YAML frontmatter, so it stays human
readable, diffable, and reviewable in pull requests.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import VALID_SCOPES


class StoreError(Exception):
    pass


@dataclass
class Memory:
    id: str
    title: str
    content: str
    author: str
    scope: str  # personal | team | org
    team: str | None = None
    tags: list[str] = field(default_factory=list)
    created: str = ""

    def to_markdown(self) -> str:
        meta = {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "scope": self.scope,
            "tags": self.tags,
            "created": self.created,
        }
        if self.team:
            meta["team"] = self.team
        front = yaml.safe_dump(meta, sort_keys=False).strip()
        return f"---\n{front}\n---\n\n{self.content.strip()}\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Memory":
        match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
        if not match:
            raise StoreError("not a memory file (missing frontmatter)")
        meta = yaml.safe_load(match.group(1)) or {}
        return cls(
            id=str(meta.get("id", "")),
            title=str(meta.get("title", "")),
            content=match.group(2).strip(),
            author=str(meta.get("author", "")),
            scope=str(meta.get("scope", "personal")),
            team=meta.get("team"),
            tags=list(meta.get("tags") or []),
            created=str(meta.get("created", "")),
        )


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "memory"


class MemoryStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    # -- paths ------------------------------------------------------------

    def scope_dir(self, scope: str, *, team: str | None = None, user: str | None = None) -> Path:
        if scope == "org":
            return self.root / "org"
        if scope == "team":
            if not team:
                raise StoreError("team scope requires a team name")
            return self.root / "teams" / team
        if scope == "personal":
            if not user:
                raise StoreError("personal scope requires a user name")
            return self.root / "users" / user
        raise StoreError(f"unknown scope {scope!r}; expected one of {VALID_SCOPES}")

    # -- write ------------------------------------------------------------

    def save(
        self,
        *,
        title: str,
        content: str,
        author: str,
        scope: str,
        team: str | None = None,
        tags: list[str] | None = None,
    ) -> Memory:
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        digest = secrets.token_hex(3)  # random: identical saves must not collide
        memory = Memory(
            id=f"{created[:10].replace('-', '')}-{_slugify(title)}-{digest}",
            title=title,
            content=content,
            author=author,
            scope=scope,
            team=team if scope == "team" else None,
            tags=tags or [],
            created=created,
        )
        directory = self.scope_dir(scope, team=team, user=author)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{memory.id}.md").write_text(memory.to_markdown())
        return memory

    def delete(self, memory: Memory) -> None:
        path = self._path_of(memory)
        if path.exists():
            path.unlink()

    def _path_of(self, memory: Memory) -> Path:
        directory = self.scope_dir(memory.scope, team=memory.team, user=memory.author)
        return directory / f"{memory.id}.md"

    # -- read -------------------------------------------------------------

    def _iter_dir(self, directory: Path):
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.md")):
            try:
                yield Memory.from_markdown(path.read_text())
            except StoreError:
                continue  # skip stray non-memory markdown

    def iter_accessible(self, user: str, user_teams: list[str]):
        """All memories `user` may read: own personal + their teams + org."""
        yield from self._iter_dir(self.scope_dir("personal", user=user))
        for team in user_teams:
            yield from self._iter_dir(self.scope_dir("team", team=team))
        yield from self._iter_dir(self.scope_dir("org"))

    def get(self, memory_id: str, user: str, user_teams: list[str]) -> Memory | None:
        for memory in self.iter_accessible(user, user_teams):
            if memory.id == memory_id:
                return memory
        return None
