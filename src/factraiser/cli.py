"""Factraiser CLI: org setup, inspection, and the MCP server entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import ConfigError, Guardrails, OrgConfig, Team, load_config, save_config
from .guardrails import scan
from .search import search as run_search
from .store import MemoryStore
from .traces import TraceLog

DEFAULT_CONFIG = "factraiser.yaml"


def _config_path(args) -> Path:
    return Path(args.config or os.environ.get("FACTRAISER_CONFIG", DEFAULT_CONFIG))


def cmd_init(args) -> int:
    path = _config_path(args)
    if path.exists():
        print(f"{path} already exists", file=sys.stderr)
        return 1
    config = OrgConfig(org=args.org, memory_root=path.parent / "memories")
    save_config(config, path)
    (path.parent / "memories" / "org").mkdir(parents=True, exist_ok=True)
    print(f"Initialized org {args.org!r}: wrote {path} and created memories/.")
    print("Next: factraiser add-team <name>, then factraiser add-user <user> --team <name>")
    return 0


def cmd_add_team(args) -> int:
    path = _config_path(args)
    config = load_config(path)
    if args.name in config.teams:
        print(f"team {args.name!r} already exists", file=sys.stderr)
        return 1
    config.teams[args.name] = Team(
        name=args.name, write_team=args.write_team, write_org=args.write_org
    )
    save_config(config, path)
    print(f"Added team {args.name!r}.")
    return 0


def cmd_add_user(args) -> int:
    path = _config_path(args)
    config = load_config(path)
    if args.team not in config.teams:
        print(f"unknown team {args.team!r} — run add-team first", file=sys.stderr)
        return 1
    members = config.teams[args.team].members
    if args.user in members:
        print(f"{args.user} is already in team {args.team!r}", file=sys.stderr)
        return 1
    members.append(args.user)
    save_config(config, path)
    print(f"Added {args.user} to team {args.team!r}.")
    return 0


def cmd_status(args) -> int:
    config = load_config(_config_path(args))
    store = MemoryStore(config.memory_root)
    print(f"org: {config.org}")
    print(f"memory root: {config.memory_root}")
    org_count = sum(1 for _ in store._iter_dir(store.scope_dir("org")))
    print(f"org memories: {org_count}")
    for team in config.teams.values():
        count = sum(1 for _ in store._iter_dir(store.scope_dir("team", team=team.name)))
        print(f"team {team.name}: {len(team.members)} members, {count} memories")
    return 0


def cmd_search(args) -> int:
    config = load_config(_config_path(args))
    store = MemoryStore(config.memory_root)
    user = args.user or os.environ.get("FACTRAISER_USER")
    if not user:
        print("pass --user or set FACTRAISER_USER", file=sys.stderr)
        return 1
    hits = run_search(args.query, store.iter_accessible(user, config.teams_of(user)))
    for hit in hits:
        where = hit.memory.scope if hit.memory.scope != "team" else f"team:{hit.memory.team}"
        print(f"{hit.score:5.1f}  [{hit.memory.id}] ({where}) {hit.memory.title}")
    if not hits:
        print("no matches")
    return 0


def cmd_scan(args) -> int:
    config = load_config(_config_path(args))
    text = Path(args.file).read_text() if args.file != "-" else sys.stdin.read()
    findings = scan(text, config.guardrails)
    for finding in findings:
        print(f"[{finding.category}] {finding.label}: …{finding.excerpt}…")
    if findings:
        print(f"\n{len(findings)} finding(s) — this content would be blocked from team/org memory.")
        return 1
    print("clean — no guardrail findings")
    return 0


def cmd_stats(args) -> int:
    """Per-memory usage aggregates, filtered to memories the user can read."""
    config = load_config(_config_path(args))
    store = MemoryStore(config.memory_root)
    user = args.user or os.environ.get("FACTRAISER_USER")
    if not user:
        print("pass --user or set FACTRAISER_USER", file=sys.stderr)
        return 1
    stats = TraceLog(config.memory_root).aggregate(config.users() or [user])
    readable = {m.id: m for m in store.iter_accessible(user, config.teams_of(user))}
    rows = [(mid, s) for mid, s in stats.items() if mid in readable]
    if not rows:
        print("no usage recorded yet for memories you can read")
        return 0
    rows.sort(key=lambda r: r[1].recalls, reverse=True)
    print(f"{'recalls':>7} {'succ':>4} {'part':>4} {'fail':>4} {'misl':>4}  {'last used':<20} memory")
    for mid, s in rows:
        o = s.outcomes
        print(
            f"{s.recalls:>7} {o['success']:>4} {o['partial']:>4} {o['failure']:>4} "
            f"{o['misleading']:>4}  {s.last_used:<20} [{mid}] {readable[mid].title}"
        )
    return 0


def cmd_review(args) -> int:
    """Compost report + promotion candidates, derived from usage traces."""
    from .review import build_report, render_report

    config = load_config(_config_path(args))
    user = args.user or os.environ.get("FACTRAISER_USER")
    if not user:
        print("pass --user or set FACTRAISER_USER", file=sys.stderr)
        return 1
    report = build_report(config, MemoryStore(config.memory_root), user, stale_days=args.days)
    print(render_report(report, args.days))
    return 0


def cmd_insights(args) -> int:
    from .insights import generate_insights

    config = load_config(_config_path(args))
    print(generate_insights(config, MemoryStore(config.memory_root)))
    return 0


def cmd_serve(args) -> int:
    from .server import run

    if args.config:
        os.environ["FACTRAISER_CONFIG"] = args.config
    if args.user:
        os.environ["FACTRAISER_USER"] = args.user
    run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factraiser", description=__doc__)
    parser.add_argument("--config", help=f"path to org config (default: {DEFAULT_CONFIG})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a new org config and memory repository")
    p.add_argument("org", help="organization name")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add-team", help="add a team")
    p.add_argument("name")
    p.add_argument("--write-team", type=lambda v: v.lower() == "true", default=None,
                   help="override org default for writing to team memory (true/false)")
    p.add_argument("--write-org", type=lambda v: v.lower() == "true", default=None,
                   help="override org default for writing to org memory (true/false)")
    p.set_defaults(func=cmd_add_team)

    p = sub.add_parser("add-user", help="add a user to a team")
    p.add_argument("user")
    p.add_argument("--team", required=True)
    p.set_defaults(func=cmd_add_user)

    p = sub.add_parser("status", help="show org, teams, and memory counts")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("search", help="search memory as a user")
    p.add_argument("query")
    p.add_argument("--user")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("scan", help="guardrail-scan a file (or - for stdin)")
    p.add_argument("file")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("stats", help="per-memory usage and outcome aggregates")
    p.add_argument("--user")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("review", help="compost report + promotion candidates from usage traces")
    p.add_argument("--user")
    p.add_argument("--days", type=int, default=90, help="staleness threshold in days (default 90)")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("insights", help="Claude-generated readout of shared memory (needs ANTHROPIC_API_KEY)")
    p.set_defaults(func=cmd_insights)

    p = sub.add_parser("serve", help="run the MCP server (stdio)")
    p.add_argument("--user", help="sets FACTRAISER_USER")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
