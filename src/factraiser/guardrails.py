"""Guardrails: keep PII, secrets, HR and legal matter out of shared memory.

Personal memory is never filtered. Writes to team or org memory are scanned
and blocked if they contain content in a blocked category; the findings are
returned so the caller (usually the LLM) can redact and retry.

These checks are pattern-based and intentionally conservative-but-imperfect —
the README's caveat applies: give the AI context, don't rely on this as the
only line of defense.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Guardrails


@dataclass
class Finding:
    category: str  # pii | secrets | hr | legal | custom
    label: str
    excerpt: str


_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("US social security number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone number", re.compile(r"(?<![\d.])(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")),
    ("credit card number", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
]

_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}")),
    ("API key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password assignment", re.compile(r"(?i)\bpassword\s*[:=]\s*\S+")),
]

_HR_KEYWORDS = [
    "salary", "compensation package", "performance review", "performance improvement plan",
    "termination", "disciplinary", "layoff", "severance", "harassment complaint",
]

_LEGAL_KEYWORDS = [
    "attorney-client", "litigation", "lawsuit", "subpoena", "settlement agreement",
    "nda violation", "cease and desist", "legal hold",
]


def _luhn_ok(digits: str) -> bool:
    digits = re.sub(r"\D", "", digits)
    if not 13 <= len(digits) <= 16:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _excerpt(text: str, start: int, end: int, radius: int = 20) -> str:
    snippet = text[max(0, start - radius):min(len(text), end + radius)]
    return snippet.replace("\n", " ").strip()


def scan(text: str, guardrails: Guardrails) -> list[Finding]:
    """Scan text and return all findings in the configured blocked categories."""
    findings: list[Finding] = []
    blocked = set(guardrails.blocked_categories)

    if "pii" in blocked:
        for label, pattern in _PII_PATTERNS:
            for m in pattern.finditer(text):
                if label == "credit card number" and not _luhn_ok(m.group()):
                    continue
                findings.append(Finding("pii", label, _excerpt(text, m.start(), m.end())))

    if "secrets" in blocked:
        for label, pattern in _SECRET_PATTERNS:
            for m in pattern.finditer(text):
                findings.append(Finding("secrets", label, _excerpt(text, m.start(), m.end())))

    lowered = text.lower()
    if "hr" in blocked:
        for keyword in _HR_KEYWORDS:
            idx = lowered.find(keyword)
            if idx != -1:
                findings.append(Finding("hr", f"HR-related term {keyword!r}", _excerpt(text, idx, idx + len(keyword))))

    if "legal" in blocked:
        for keyword in _LEGAL_KEYWORDS:
            idx = lowered.find(keyword)
            if idx != -1:
                findings.append(Finding("legal", f"legal term {keyword!r}", _excerpt(text, idx, idx + len(keyword))))

    for term in guardrails.custom_blocklist:
        idx = lowered.find(term.lower())
        if idx != -1:
            findings.append(Finding("custom", f"blocklisted term {term!r}", _excerpt(text, idx, idx + len(term))))

    return findings


def check_for_scope(text: str, scope: str, guardrails: Guardrails) -> list[Finding]:
    """Findings that block a write to `scope`. Personal memory is never filtered."""
    if scope == "personal":
        return []
    return scan(text, guardrails)
