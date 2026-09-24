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
from .naming import check_name


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
    # Set on memories created by promote_memory: the source memory and its author.
    promoted_from: str | None = None
    original_author: str | None = None

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
        if self.promoted_from:
            meta["promoted_from"] = self.promoted_from
            meta["original_author"] = self.original_author
        front = yaml.safe_dump(meta, sort_keys=False).strip()
        return f"---\n{front}\n---\n\n{self.content.strip()}\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Memory":
        match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
        if not match:
            raise StoreError("not a memory file (missing frontmatter)")
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise StoreError(f"invalid frontmatter YAML ({exc})") from exc
        if not isinstance(meta, dict):
            raise StoreError("frontmatter is not a mapping")
        tags = meta.get("tags") or []
        if not isinstance(tags, list):
            raise StoreError("frontmatter 'tags' is not a list")
        team = meta.get("team")
        promoted_from = meta.get("promoted_from")
        original_author = meta.get("original_author")
        return cls(
            id=str(meta.get("id", "")),
            title=str(meta.get("title", "")),
            content=match.group(2).strip(),
            author=str(meta.get("author", "")),
            scope=str(meta.get("scope", "personal")),
            team=None if team is None else str(team),
            tags=[str(t) for t in tags],
            created=str(meta.get("created", "")),
            promoted_from=None if promoted_from is None else str(promoted_from),
            original_author=None if original_author is None else str(original_author),
        )


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "memory"


class MemoryStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    # -- paths ------------------------------------------------------------

    def scope_dir(self, scope: str, *, team: str | None = None, user: str | None = None) -> Path:
        try:
            if scope == "org":
                return self.root / "org"
            if scope == "team":
                if not team:
                    raise StoreError("team scope requires a team name")
                return self.root / "teams" / check_name(team, "team name")
            if scope == "personal":
                if not user:
                    raise StoreError("personal scope requires a user name")
                return self.root / "users" / check_name(user, "user name")
        except ValueError as exc:
            raise StoreError(str(exc)) from exc
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
        promoted_from: Memory | None = None,
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
            promoted_from=promoted_from.id if promoted_from else None,
            original_author=promoted_from.author if promoted_from else None,
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
        # memory.id may come from hand-edited frontmatter — validate before
        # using it as a filename so a hostile id can't escape the scope dir.
        try:
            memory_id = check_name(memory.id, "memory id")
        except ValueError as exc:
            raise StoreError(str(exc)) from exc
        directory = self.scope_dir(memory.scope, team=memory.team, user=memory.author)
        return directory / f"{memory_id}.md"

    # -- read -------------------------------------------------------------

    def iter_scope(self, scope: str, *, team: str | None = None, user: str | None = None):
        """Memories stored in one scope directory.

        The directory, not the frontmatter, decides scope and team (and the
        author, for personal memory): frontmatter is hand-editable, and a file
        in org/ claiming to be someone's personal note must still read as org.
        """
        directory = self.scope_dir(scope, team=team, user=user)
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.md")):
            try:
                memory = Memory.from_markdown(path.read_text())
            except (StoreError, OSError, UnicodeDecodeError):
                continue  # one bad file must not take down recall for everyone
            memory.scope = scope
            memory.team = team if scope == "team" else None
            if scope == "personal":
                memory.author = user
            yield memory

    def iter_accessible(self, user: str, user_teams: list[str]):
        """All memories `user` may read: own personal + their teams + org."""
        yield from self.iter_scope("personal", user=user)
        for team in user_teams:
            yield from self.iter_scope("team", team=team)
        yield from self.iter_scope("org")

    def get(self, memory_id: str, user: str, user_teams: list[str]) -> Memory | None:
        for memory in self.iter_accessible(user, user_teams):
            if memory.id == memory_id:
                return memory
        return None
