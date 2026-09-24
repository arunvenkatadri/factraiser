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
import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .naming import check_name

VALID_RESULTS = ("success", "partial", "failure", "misleading")

MAX_NOTE_LEN = 4_000

# Contribution of each outcome to a memory's usefulness signal. `misleading`
# is punished hardest — a wrong memory is worse than no memory.
_OUTCOME_WEIGHTS = {"success": 1.0, "partial": 0.5, "failure": -0.5, "misleading": -2.0}
# Outcome contributions halve every 180 days, so stale wins don't coast.
_HALF_LIFE_DAYS = 180.0
# Bounds on one user's total contribution to a memory's score, so no single
# user can sink (or boost) a memory alone — it takes agreement across users.
_USER_NET_MIN, _USER_NET_MAX = -2.0, 1.0


@dataclass
class MemoryStats:
    recalls: int = 0
    outcomes: dict[str, int] = field(default_factory=lambda: {r: 0 for r in VALID_RESULTS})
    last_used: str = ""
    decayed_net: float = 0.0  # time-decayed sum of outcome weights
    success_users: set[str] = field(default_factory=set)
    misleading_notes: list[str] = field(default_factory=list)

    def multiplier(self) -> float:
        """Usefulness multiplier for search ranking, bounded [0.4, 1.3].

        Relevance stays the primary signal; this is a tiebreaker-plus.
        Memories with no outcome history get exactly 1.0.
        """
        if self.decayed_net == 0.0:
            return 1.0
        # Asymmetric: a wrong memory is worse than no memory, so the
        # downside (to 0.4) is steeper than the upside (to 1.3).
        swing = 0.6 if self.decayed_net < 0 else 0.3
        return max(0.4, 1.0 + swing * math.tanh(self.decayed_net / 3.0))


class TraceLog:
    def __init__(self, memory_root: str | Path):
        self.root = Path(memory_root) / "traces" / "users"

    def _file(self, user: str, ts: str) -> Path:
        directory = self.root / check_name(user, "user name")
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
        note = note[:MAX_NOTE_LEN]
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
        directory = self.root / check_name(user, "user name")
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # one corrupted line must not take down recall/stats
                if (
                    isinstance(event, dict)
                    and isinstance(event.get("event"), str)
                    and isinstance(event.get("ts"), str)
                    and isinstance(event.get("trace_id"), str)
                ):
                    yield event

    def find_recall(self, user: str, trace_id: str) -> dict | None:
        for event in self.iter_events(user):
            if event["event"] == "recall" and event["trace_id"] == trace_id:
                return event
        return None

    def aggregate(self, users: list[str], now: datetime | None = None) -> dict[str, MemoryStats]:
        """Per-memory aggregates across the given users' traces.

        Counts, a time-decayed usefulness score, which users had successes
        (drives promotion candidates), and notes attached to `misleading`
        outcomes (drives the compost report). No task content beyond those
        notes — safe to show to anyone who can read the memory itself.

        Anti-gaming: only the latest outcome per trace counts (re-recording
        replaces the verdict, it doesn't add one), and each user's total
        contribution to a memory's score is clamped to
        [_USER_NET_MIN, _USER_NET_MAX].
        """
        now = now or datetime.now(timezone.utc)
        stats: dict[str, MemoryStats] = {}

        def entry_for(memory_id: str, ts: str) -> MemoryStats:
            entry = stats.setdefault(memory_id, MemoryStats())
            if ts > entry.last_used:
                entry.last_used = ts
            return entry

        for user in users:
            latest_outcome: dict[str, dict] = {}
            for event in self.iter_events(user):
                memory_ids = event.get("memory_ids")
                if not isinstance(memory_ids, list):
                    continue
                if event["event"] == "recall":
                    for memory_id in memory_ids:
                        entry_for(str(memory_id), event["ts"]).recalls += 1
                elif event["event"] == "outcome" and event.get("result") in VALID_RESULTS:
                    latest_outcome[event["trace_id"]] = event  # later lines win

            user_net: dict[str, float] = {}
            for event in latest_outcome.values():
                result = event["result"]
                try:
                    age_seconds = (now - datetime.fromisoformat(event["ts"])).total_seconds()
                    age_days = max(0.0, age_seconds / 86400)
                except (ValueError, TypeError):
                    age_days = 0.0  # unparseable timestamp: count it, skip decay
                decay = 0.5 ** (age_days / _HALF_LIFE_DAYS)
                for memory_id in map(str, event["memory_ids"]):
                    entry = entry_for(memory_id, event["ts"])
                    entry.outcomes[result] += 1
                    user_net[memory_id] = user_net.get(memory_id, 0.0) + _OUTCOME_WEIGHTS[result] * decay
                    if result == "success":
                        # the trace directory is the identity, not the forgeable event field
                        entry.success_users.add(user)
                    elif result == "misleading" and event.get("note"):
                        if len(entry.misleading_notes) < 3:
                            entry.misleading_notes.append(str(event["note"])[:200])
            for memory_id, net in user_net.items():
                stats[memory_id].decayed_net += min(_USER_NET_MAX, max(_USER_NET_MIN, net))
        return stats
