# Design: The Outcome Loop

**Status:** proposal — no code yet. React to this before implementation.

## Why

Factraiser today is the storage half of an institutional learning system: memory
goes in, permissioned and guardrailed, and comes back out via `recall`. Nothing
measures whether a recalled memory actually *helped*, and nothing gets better
with use. This design adds the missing half — a feedback loop where every use
of memory generates signal, and that signal drives ranking, pruning, and
promotion. The trace log it produces is also the org-owned dataset for private
evals (and, later, RL) — the "learning loop the firm owns," independent of any
particular model.

Guiding constraints, carried over from the existing architecture:

1. **Memories stay immutable.** No stats are written into memory files — that
   would churn git history and invite merge conflicts. All signal lives in an
   append-only trace log; usefulness is *derived at query time*, same principle
   as `shared_context` and `insights`.
2. **Traces are personal-tier by default.** A trace describes what a user was
   working on — that's as sensitive as personal memory. Only *aggregates per
   memory* (recall counts, outcome tallies) surface to people who can already
   read that memory.
3. **Tier crossings stay explicit.** Signal *nominates* memories for promotion;
   a human (or PR review) still promotes.

## The loop

```
recall ──▶ task ──▶ record_outcome ──▶ trace log ──▶ derived usefulness
   ▲                                                      │
   └──────── ranking / decay / promotion candidates ◀─────┘
```

1. **`recall` / `shared_context` log a trace event** — which memories were
   surfaced for which query — and return a `trace_id` in their output.
2. **A new `record_outcome` MCP tool** closes the loop. The server instructions
   tell the model: *when a task that used recalled memory concludes, record
   whether it succeeded.* The model is the reporter; the user is never nagged.
   Args: `trace_id`, `result` (`success | partial | failure`), optional `note`
   ("the runbook's migration order was wrong for Postgres 16").
3. **Usefulness is computed from traces at query time**: per memory, how often
   recalled, how often present in successful vs. failed outcomes, recency.

## Trace log

Append-only JSONL, one directory per user (mirrors the personal tier ACL,
avoids git merge conflicts), one file per month:

```
memories/
└── traces/
    └── users/
        └── alice/
            └── 2026-06.jsonl
```

Two event types, versioned:

```json
{"v": 1, "event": "recall",  "trace_id": "tr-20260615-a1b2c3", "ts": "2026-06-15T18:20:00+00:00",
 "user": "alice", "query": "postgres failover", "memory_ids": ["20260610-deploy-runbook-4c17d5"]}

{"v": 1, "event": "outcome", "trace_id": "tr-20260615-a1b2c3", "ts": "2026-06-15T18:41:00+00:00",
 "user": "alice", "result": "success", "note": "failover completed using the runbook",
 "memory_ids": ["20260610-deploy-runbook-4c17d5"]}
```

`memory_ids` is denormalized onto the outcome event so each line is a complete,
exportable training example even if its paired recall event is pruned.

**Access:** a user reads only their own traces. Per-memory aggregates
(`recalls: 14, success: 11, failure: 1, last_used: …`) are visible to anyone
who can read the memory itself — counts don't leak task content.

## What the signal drives

**Ranking (Phase 2).** `search` gains a usefulness multiplier: memories with a
positive outcome record rank above never-used ones; memories that repeatedly
co-occur with failure sink. Recency decay so stale knowledge doesn't coast on
old wins. The keyword/embedding relevance score stays primary — usefulness is
a tiebreaker-plus, not the ranking.

**Pruning (Phase 2).** `factraiser review` prints a compost report: memories
never recalled in N days, or with net-negative outcomes — candidates for a
human to archive or rewrite. Nothing is auto-deleted.

**Promotion candidates (Phase 2).** Team memories recalled successfully by
multiple users are flagged (in `factraiser insights` and a `promote-candidates`
report) as candidates for org tier. Promotion itself stays an explicit,
guardrailed act.

**Private evals (Phase 3).** `factraiser eval` answers "is memory helping *this
org*?" with two honest v1 measures:
- *Retrieval quality*: replay past recall queries against the current store —
  does the memory that led to a recorded success still rank in the top k?
- *Observational outcome delta*: success rate of traced tasks that used memory
  vs. those that didn't. Reported with the caveat that it's correlational;
  causal A/B (same task, memory on/off) is a later, deliberate experiment.

**Export (Phase 3).** `factraiser export-traces` emits a JSONL dataset —
`{query, memories_used, result, note}` — the org-owned corpus for evals or RL
fine-tuning. Export is an explicit act: guardrail-scanned, personal traces
included only by their owner (or an org policy knob). The schema above is
designed so this export needs no retrofit.

## Rollout

| Phase | Ships | New surface |
|---|---|---|
| 1 | Trace logging in `recall`/`shared_context`; `record_outcome` tool; `factraiser stats` (per-memory aggregates) | 1 MCP tool, 1 CLI cmd |
| 2 | Usefulness-weighted ranking; `factraiser review` compost report; promotion candidates | ranking change, 1 CLI cmd |
| 3 | `factraiser eval`; `factraiser export-traces` | 2 CLI cmds |

Phase 1 is deliberately small — the whole design fails or succeeds on whether
`record_outcome` actually gets called with faithful data, so we ship the
capture primitive first and look at real traces before building ranking on top.

## Open questions

1. **Outcome taxonomy** — is `success | partial | failure` enough, or do we
   want a "memory was wrong/harmful" flag distinct from "task failed anyway"?
   (Leaning: add `misleading` as a fourth result — it's the signal pruning
   needs most.)
2. **Should the model auto-record without confirming with the user?** Low
   friction vs. label quality. (Leaning: auto-record, since the trace log is
   reviewable and per-user; noisy labels beat no labels.)
3. **Trace retention** — keep forever (it's the training asset) or expire
   recall events after N months, keeping only outcome events? (Leaning: keep
   outcomes forever, prune bare recalls after 12 months.)
