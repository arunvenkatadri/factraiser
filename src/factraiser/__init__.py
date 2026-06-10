"""Factraiser — tiered AI memory for enterprises.

Memory is organized in three scopes:

- ``personal``: visible only to the author. Never guardrail-filtered.
- ``team``: visible to members of a team. Guardrails apply on write.
- ``org``: visible to everyone in the organization. Guardrails apply on write.

The MCP server (``factraiser.server``) exposes this hierarchy to Claude and
other MCP clients so the LLM can read shared context and commit new learnings
to the right tier, subject to permissions and guardrails.
"""

__version__ = "0.1.0"
