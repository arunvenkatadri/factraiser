"""Keyword search across the memories a user can read.

Deliberately dependency-free: tokenized term matching with title/tag boosts.
Good enough to make `recall` useful out of the box; swap in embeddings later
without changing the MCP surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .store import Memory

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Hit:
    memory: Memory
    score: float


def search(query: str, memories: Iterable[Memory], limit: int = 10) -> list[Hit]:
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []

    hits: list[Hit] = []
    for memory in memories:
        title_tokens = set(_tokens(memory.title))
        tag_tokens = set(_tokens(" ".join(memory.tags)))
        body_tokens = _tokens(memory.content)
        body_set = set(body_tokens)

        score = 0.0
        for token in query_tokens:
            if token in title_tokens:
                score += 3.0
            if token in tag_tokens:
                score += 2.0
            if token in body_set:
                score += 1.0 + 0.1 * min(body_tokens.count(token), 5)
        if score > 0:
            hits.append(Hit(memory=memory, score=score))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
