"""Org-level insights: have Claude read shared memory and surface patterns.

Optional — requires the `anthropic` package and ANTHROPIC_API_KEY. Used by
`factraiser insights` so admins can get a periodic readout of what the org's
teams are learning, where they conflict, and what deserves promotion to org
memory.
"""

from __future__ import annotations

from .config import OrgConfig
from .store import MemoryStore

MODEL = "claude-opus-4-8"

_SYSTEM = (
    "You are an analyst for an enterprise's shared AI memory. You will be "
    "given every team-level and org-level memory in the organization. "
    "Produce a concise readout: (1) cross-team themes, (2) contradictions or "
    "duplicated effort between teams, (3) team memories valuable enough to "
    "promote to org memory (cite memory ids), and (4) gaps where the org has "
    "no recorded knowledge. Cite memory ids for every claim."
)


def generate_insights(config: OrgConfig, store: MemoryStore) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "insights requires the anthropic package: pip install 'factraiser[insights]'"
        ) from exc

    shared = []
    for team in config.teams:
        shared.extend(store._iter_dir(store.scope_dir("team", team=team)))
    shared.extend(store._iter_dir(store.scope_dir("org")))

    if not shared:
        return "No team or org memory to analyze yet."

    corpus = "\n\n---\n\n".join(m.to_markdown() for m in shared)
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Organization: {config.org}\n\nShared memories:\n\n{corpus}",
            }
        ],
    ) as stream:
        message = stream.get_final_message()
    return next(b.text for b in message.content if b.type == "text")
