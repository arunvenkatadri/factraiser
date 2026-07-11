"""Curation reports derived from the trace log.

Three sections, all advisory — nothing is auto-deleted or auto-promoted:

- **fix_or_archive**: memories with net-negative outcomes (misleading notes
  attached, so a human knows exactly what to correct)
- **stale**: shared-tier memories never recalled, or unused for N days
- **promote**: team memories that led to successes for multiple users —
  candidates for org tier (promotion stays an explicit, guardrailed act)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import OrgConfig
from .store import Memory, MemoryStore
from .traces import MemoryStats, TraceLog


@dataclass
class ReviewReport:
    fix_or_archive: list[tuple[Memory, MemoryStats]] = field(default_factory=list)
    stale: list[Memory] = field(default_factory=list)
    promote: list[tuple[Memory, MemoryStats]] = field(default_factory=list)


def build_report(
    config: OrgConfig,
    store: MemoryStore,
    user: str,
    stale_days: int = 90,
    now: datetime | None = None,
) -> ReviewReport:
    now = now or datetime.now(timezone.utc)
    log = TraceLog(config.memory_root)
    stats = log.aggregate(config.users() or [user], now=now)
    cutoff = (now - timedelta(days=stale_days)).isoformat(timespec="seconds")

    report = ReviewReport()
    for memory in store.iter_accessible(user, config.teams_of(user)):
        entry = stats.get(memory.id)

        if entry and entry.decayed_net < 0:
            report.fix_or_archive.append((memory, entry))
            continue

        if memory.scope in ("team", "org"):
            never_used = entry is None or entry.recalls == 0
            unused_lately = entry is not None and entry.last_used and entry.last_used < cutoff
            if never_used or unused_lately:
                report.stale.append(memory)

        if (
            memory.scope == "team"
            and entry
            and len(entry.success_users) >= 2
            and entry.decayed_net > 0
        ):
            report.promote.append((memory, entry))

    return report


def render_report(report: ReviewReport, stale_days: int) -> str:
    lines: list[str] = []

    lines.append(f"Fix or archive ({len(report.fix_or_archive)}) — net-negative outcomes:")
    for memory, entry in report.fix_or_archive:
        lines.append(f"  [{memory.id}] {memory.title} (net {entry.decayed_net:+.1f})")
        for note in entry.misleading_notes:
            lines.append(f"      note: {note}")

    lines.append(f"\nStale ({len(report.stale)}) — shared memories unused for {stale_days}+ days:")
    for memory in report.stale:
        where = memory.scope if memory.scope != "team" else f"team:{memory.team}"
        lines.append(f"  [{memory.id}] ({where}) {memory.title}")

    lines.append(f"\nPromotion candidates ({len(report.promote)}) — team memories with successes from 2+ users:")
    for memory, entry in report.promote:
        users = ", ".join(sorted(entry.success_users))
        lines.append(
            f"  [{memory.id}] (team:{memory.team}) {memory.title} — helped: {users}. "
            f"Promote with: promote_memory({memory.id!r}, 'org')"
        )

    return "\n".join(lines)
