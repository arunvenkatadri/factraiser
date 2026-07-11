"""Factraiser MCP server.

Exposes the tiered memory hierarchy to Claude (or any MCP client) over stdio.
Identity and config come from the environment:

- ``FACTRAISER_USER``   — who the connected user is (required)
- ``FACTRAISER_CONFIG`` — path to factraiser.yaml (default: ./factraiser.yaml)

Example Claude Desktop / Claude Code config::

    {
      "mcpServers": {
        "factraiser": {
          "command": "factraiser",
          "args": ["serve"],
          "env": {
            "FACTRAISER_USER": "alice",
            "FACTRAISER_CONFIG": "/path/to/factraiser.yaml"
          }
        }
      }
    }
"""

from __future__ import annotations

import os

try:  # mcp SDK 2.x — MCP spec 2026-07-28: stateless core, server/discover
    from mcp.server.mcpserver import MCPServer as _ServerClass
except ImportError:  # mcp SDK 1.x — classic initialize handshake
    from mcp.server.fastmcp import FastMCP as _ServerClass

from .config import OrgConfig, load_config
from .guardrails import check_for_scope
from .permissions import can_write
from .search import search as run_search
from .store import Memory, MemoryStore
from .traces import VALID_RESULTS, TraceLog

mcp = _ServerClass(
    "factraiser",
    instructions=(
        "Factraiser is the organization's shared memory. Use `recall` before "
        "starting a task to pull relevant team and org learnings, and use "
        "`remember` to commit durable, broadly useful learnings to the right "
        "tier. Prefer the narrowest scope that fits: personal for individual "
        "context, team for team practices, org for org-wide knowledge. Writes "
        "to team/org memory are guardrail-scanned; if a write is blocked, "
        "redact the flagged content and retry, or fall back to personal scope. "
        "When a task that used recalled memory concludes, call `record_outcome` "
        "with the trace id from the recall — without asking the user — so the "
        "org learns which memories actually help. Use result 'misleading' when "
        "a memory was wrong or harmful, distinct from the task merely failing."
    ),
)


def _context() -> tuple[OrgConfig, MemoryStore, str]:
    user = os.environ.get("FACTRAISER_USER")
    if not user:
        raise RuntimeError("FACTRAISER_USER is not set; the server needs to know who you are")
    config = load_config(os.environ.get("FACTRAISER_CONFIG", "factraiser.yaml"))
    return config, MemoryStore(config.memory_root), user


def _render(memory: Memory, *, with_body: bool = True) -> str:
    where = memory.scope if memory.scope != "team" else f"team:{memory.team}"
    head = f"[{memory.id}] ({where}) {memory.title} — by {memory.author}, {memory.created}"
    if memory.tags:
        head += f" | tags: {', '.join(memory.tags)}"
    return f"{head}\n{memory.content}" if with_body else head


@mcp.tool()
def remember(
    title: str,
    content: str,
    scope: str = "personal",
    team: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Save a memory to the given tier (personal, team, or org).

    Use the narrowest scope that fits. `team` is required for team scope.
    Team/org writes are permission-checked and guardrail-scanned: if blocked,
    the response lists the findings so you can redact and retry.
    """
    config, store, user = _context()

    decision = can_write(config, user, scope, team)
    if not decision.allowed:
        return f"DENIED: {decision.reason}"

    findings = check_for_scope(f"{title}\n{content}", scope, config.guardrails)
    if findings:
        lines = [f"- [{f.category}] {f.label}: …{f.excerpt}…" for f in findings]
        return (
            f"BLOCKED by guardrails — this content may not be written to {scope} memory:\n"
            + "\n".join(lines)
            + "\nRedact the flagged content and retry, or save to personal scope instead."
        )

    memory = store.save(
        title=title, content=content, author=user, scope=scope, team=team, tags=tags
    )
    return f"Saved {memory.id} to {scope} memory."


@mcp.tool()
def recall(query: str, limit: int = 8) -> str:
    """Search all memory you can read (your personal, your teams', and org).

    Call this before starting a task to pull relevant prior learnings. When
    the task concludes, report how it went via `record_outcome` using the
    trace id in the first line of the result.
    """
    config, store, user = _context()
    log = TraceLog(config.memory_root)
    stats = log.aggregate(config.users() or [user])
    hits = run_search(
        query,
        store.iter_accessible(user, config.teams_of(user)),
        limit=limit,
        usefulness={mid: s.multiplier() for mid, s in stats.items()},
    )
    if not hits:
        return "No matching memories."
    trace_id = log.log_recall(user, query, [h.memory.id for h in hits])
    return f"trace: {trace_id}\n\n" + "\n\n".join(_render(h.memory) for h in hits)


@mcp.tool()
def read_memory(memory_id: str) -> str:
    """Read a single memory by id."""
    config, store, user = _context()
    memory = store.get(memory_id, user, config.teams_of(user))
    if memory is None:
        return f"No accessible memory with id {memory_id!r}."
    return _render(memory)


@mcp.tool()
def list_memories(scope: str | None = None) -> str:
    """List memories you can read, optionally filtered by scope (personal/team/org)."""
    config, store, user = _context()
    memories = [
        m
        for m in store.iter_accessible(user, config.teams_of(user))
        if scope is None or m.scope == scope
    ]
    if not memories:
        return "No memories yet."
    return "\n".join(_render(m, with_body=False) for m in memories)


@mcp.tool()
def promote_memory(memory_id: str, to_scope: str, team: str | None = None) -> str:
    """Promote a memory up the hierarchy (personal → team → org).

    Re-runs permission and guardrail checks for the destination tier. The
    original memory is kept; promotion creates a copy in the wider tier.
    """
    config, store, user = _context()
    memory = store.get(memory_id, user, config.teams_of(user))
    if memory is None:
        return f"No accessible memory with id {memory_id!r}."

    decision = can_write(config, user, to_scope, team)
    if not decision.allowed:
        return f"DENIED: {decision.reason}"

    findings = check_for_scope(f"{memory.title}\n{memory.content}", to_scope, config.guardrails)
    if findings:
        lines = [f"- [{f.category}] {f.label}: …{f.excerpt}…" for f in findings]
        return (
            f"BLOCKED by guardrails — cannot promote to {to_scope} memory:\n" + "\n".join(lines)
        )

    promoted = store.save(
        title=memory.title,
        content=memory.content,
        author=user,
        scope=to_scope,
        team=team,
        tags=memory.tags,
    )
    return f"Promoted {memory_id} → {promoted.id} ({to_scope})."


@mcp.tool()
def shared_context() -> str:
    """Digest of all team and org memory you can read.

    Pull this at the start of a session to ground your work in what the
    organization already knows and steer in the directions it has chosen.
    """
    config, store, user = _context()
    shared = [
        m
        for m in store.iter_accessible(user, config.teams_of(user))
        if m.scope in ("team", "org")
    ]
    if not shared:
        return "No shared memory yet — the org/team tiers are empty."
    trace_id = TraceLog(config.memory_root).log_recall(
        user, "(shared_context)", [m.id for m in shared]
    )
    header = f"trace: {trace_id}\nShared memory for org {config.org!r} ({len(shared)} entries):"
    return header + "\n\n" + "\n\n".join(_render(m) for m in shared)


@mcp.tool()
def record_outcome(trace_id: str, result: str, note: str = "") -> str:
    """Record how a task that used recalled memory concluded.

    Call this when such a task wraps up — no need to ask the user first.
    `result` is one of: success, partial, failure, or misleading (the recalled
    memory was wrong or harmful — distinct from the task merely failing).
    Add a short `note` when a memory was outdated or misleading, so it can be
    fixed. This signal drives ranking, pruning, and promotion of memories.
    """
    config, store, user = _context()
    log = TraceLog(config.memory_root)
    if result not in VALID_RESULTS:
        return f"Invalid result {result!r}; expected one of: {', '.join(VALID_RESULTS)}."
    try:
        event = log.log_outcome(user, trace_id, result, note)
    except KeyError:
        return (
            f"Unknown trace id {trace_id!r} — use the `trace:` id returned by "
            "recall or shared_context."
        )
    return f"Recorded {result} for {len(event['memory_ids'])} memories on {trace_id}."


def run() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    run()
