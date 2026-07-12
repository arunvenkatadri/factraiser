"""Validation for names that become filesystem path components.

Users, teams, and memory ids all map to files/directories under the memory
root. Every one must be a single safe path component — no separators, no
`..`, no leading dot — so a hostile name can never escape the root.
"""

from __future__ import annotations

import re

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def check_name(value: str, what: str = "name") -> str:
    """Return `value` if it is a safe single path component, else raise ValueError."""
    if not isinstance(value, str) or not _NAME.match(value):
        raise ValueError(
            f"invalid {what} {value!r}: use letters, digits, '.', '-', '_' "
            "(must start with a letter or digit, max 64 chars)"
        )
    return value
