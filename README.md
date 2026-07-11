# factraiser<img width="1402" height="1122" alt="factraiser" src="https://github.com/user-attachments/assets/835f820a-cead-48e3-a2e7-b9b532f58e20" />

**AI Memory for enterprises.**

We all know the problem. The memory your org needs is fragmented across all of your users — a Claude memory here, an `.md` file there.

1. Not all memories and `.md` files are suitable for public consumption.
2. Some memories and `.md` files are needed to help move the org forward.

The impact: despite your super-talented team and your AI spend, your org may feel more disconnected than ever — learnings aren't shared across teams the way they should be.

**The answer:** a tiered, hierarchical memory structure. Users on the same enterprise account interact with broader memory tiers and push knowledge into a shared repository with appropriate access. The LLM reads the org- and team-level entries to derive insights and steer people correctly.

<img width="2040" height="1260" alt="memory_hierarchy_3x" src="https://github.com/user-attachments/assets/92546c44-d5a6-4bd2-9ea1-732526313871" />

## How it works

Factraiser is an **MCP server** backed by a plain-files memory repository, so the org repo *is* the memory store — human-readable markdown, diffable, reviewable in pull requests.

```
memories/
├── org/                # readable by everyone in the org
├── teams/<team>/       # readable by team members
└── users/<user>/       # personal — readable only by the author
```

Three tiers, three rules:

| Tier | Who reads it | Who writes it | Guardrails |
|---|---|---|---|
| `personal` | only the author | always the author | never filtered |
| `team` | team members | members, unless team policy forbids | scanned on write |
| `org` | everyone | only teams granted `write_org` | scanned on write |

Connected through MCP, Claude can:

- **`recall`** / **`shared_context`** — pull relevant team and org learnings before starting a task, so the LLM steers people in the direction the org has already chosen.
- **`remember`** — commit a durable learning to the narrowest tier that fits, subject to permissions and guardrails.
- **`promote_memory`** — move a learning up the hierarchy (personal → team → org), re-checked at each step.

**The outcome loop:** every `recall` is traced, and when a task concludes the LLM calls **`record_outcome`** (`success` / `partial` / `failure` / `misleading`) so the org learns which memories actually help. Memories stay immutable — signal lives in an append-only, per-user trace log under `memories/traces/`, and usefulness is derived at query time. See `docs/design/outcome-loop.md` for the full design (ranking, pruning, private evals, and org-owned trace export follow in later phases).

**Guardrails:** by default, PII, secrets, HR, and legal content are blocked from anything that isn't personal memory. When a write is blocked, the findings are returned so the LLM can redact and retry. These checks are pattern-based and imperfect — give the AI context and treat them as a safety net, not the only line of defense.

## Quickstart

```bash
pip install -e .
```

**Step 1 — Name your org.** This creates the org config and memory repository:

```bash
factraiser init acme
```

**Step 2 — Create teams and define permissions.** Some team should never commit to team memory? Some team should never commit to org memory? Specify it here:

```bash
factraiser add-team platform --write-org true    # platform may publish to org memory
factraiser add-team hr --write-team false        # HR notes stay personal
factraiser add-user alice --team platform
factraiser add-user carol --team hr
```

**Step 3 — Define your guardrails** in `factraiser.yaml` (defaults shown):

```yaml
guardrails:
  blocked_categories: [pii, secrets, hr, legal]
  custom_blocklist: []          # org-specific terms to keep out of shared memory
```

**Step 4 — Connect Claude.** Add to your Claude Code / Claude Desktop MCP config:

```json
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
```

Each user connects with their own `FACTRAISER_USER`, and the tiers, permissions, and guardrails apply automatically.

## CLI

```text
factraiser init <org>            create org config + memory repository
factraiser add-team <name>       add a team (--write-team/--write-org override defaults)
factraiser add-user <u> --team   add a user to a team
factraiser status                org, teams, memory counts
factraiser search <q> --user u   search memory as a user
factraiser scan <file|->         guardrail-scan content before sharing
factraiser stats                 per-memory usage and outcome aggregates
factraiser insights              Claude-generated readout of shared memory
factraiser serve                 run the MCP server (stdio)
```

`factraiser insights` uses the Anthropic API (`pip install -e '.[insights]'` and set `ANTHROPIC_API_KEY`) to read all shared memory and report cross-team themes, contradictions, candidates for promotion to org memory, and knowledge gaps.

## Development

```bash
pip install -e '.[dev]'
pytest
```

## Roadmap

- Outcome loop phases 2–3: usefulness-weighted ranking, compost/promotion reports, private evals, trace export (`docs/design/outcome-loop.md`)
- Auto-summarized chat capture into personal memory
- Embedding-based retrieval (the `recall` MCP surface stays the same)
- Git-native sync: push/pull the memory repo, promotion via pull request
- LLM-assisted guardrails (Claude classifies borderline content before it lands in shared tiers)
- Web interface for org/team administration
