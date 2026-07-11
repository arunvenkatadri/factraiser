"""Usage traces: the append-only signal log behind the outcome loop.

Memories stay immutable; every use of memory is recorded here instead.
Layout mirrors the personal tier's ACL — a user's traces describe what they
were working on, so only that user reads their raw traces::

    memories/traces/users/<user>/<YYYY-MM>.jsonl

Two event types (see docs/design/outcome-loop.md):

- ``recall``:  which memories were surfaced for which query
- ``outcome``: how the task that used them concluded

``memory_ids`` is denormalized onto outcome events so each line is a
complete, exportable training example on its own.

Per-memory aggregates (counts only — no task content) may be shown to anyone
who can read the memory itself; that filtering happens in the caller.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VALID_RESULTS = ("success", "partial", "failure", "misleading")


@dataclass
class MemoryStats:
    recalls: int = 0
    outcomes: dict[str, int] = field(default_factory=lambda: {r: 0 for r in VALID_RESULTS})
    last_used: str = ""


class TraceLog:
    def __init__(self, memory_root: str | Path):
        self.root = Path(memory_root) / "traces" / "users"

    def _file(self, user: str, ts: str) -> Path:
        directory = self.root / user
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{ts[:7]}.jsonl"

    def _append(self, user: str, event: dict) -> None:
        with self._file(user, event["ts"]).open("a") as f:
            f.write(json.dumps(event) + "\n")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # -- write --------------------------------------------------------------

    def log_recall(self, user: str, query: str, memory_ids: list[str]) -> str:
        ts = self._now()
        trace_id = f"tr-{ts[:10].replace('-', '')}-{secrets.token_hex(3)}"
        self._append(user, {
            "v": 1, "event": "recall", "trace_id": trace_id, "ts": ts,
            "user": user, "query": query, "memory_ids": memory_ids,
        })
        return trace_id

    def log_outcome(
        self,
        user: str,
        trace_id: str,
        result: str,
        note: str = "",
        memory_ids: list[str] | None = None,
    ) -> dict:
        if result not in VALID_RESULTS:
            raise ValueError(f"result must be one of {VALID_RESULTS}, got {result!r}")
        if memory_ids is None:
            recall = self.find_recall(user, trace_id)
            if recall is None:
                raise KeyError(f"no recall event with trace_id {trace_id!r} for {user}")
            memory_ids = recall["memory_ids"]
        event = {
            "v": 1, "event": "outcome", "trace_id": trace_id, "ts": self._now(),
            "user": user, "result": result, "note": note, "memory_ids": memory_ids,
        }
        self._append(user, event)
        return event

    # -- read ---------------------------------------------------------------

    def iter_events(self, user: str):
        directory = self.root / user
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if line.strip():
                    yield json.loads(line)

    def find_recall(self, user: str, trace_id: str) -> dict | None:
        for event in self.iter_events(user):
            if event["event"] == "recall" and event["trace_id"] == trace_id:
                return event
        return None

    def aggregate(self, users: list[str]) -> dict[str, MemoryStats]:
        """Per-memory aggregates across the given users' traces.

        Counts only — safe to show to anyone who can read the memory itself.
        """
        stats: dict[str, MemoryStats] = {}
        for user in users:
            for event in self.iter_events(user):
                for memory_id in event.get("memory_ids", []):
                    entry = stats.setdefault(memory_id, MemoryStats())
                    if event["event"] == "recall":
                        entry.recalls += 1
                    elif event["event"] == "outcome" and event["result"] in entry.outcomes:
                        entry.outcomes[event["result"]] += 1
                    if event["ts"] > entry.last_used:
                        entry.last_used = event["ts"]
        return stats
