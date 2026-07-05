"""Small text helpers shared across the engine and adapters."""

from __future__ import annotations

import re

_WHITESPACE_PATTERN = re.compile(r"\s+")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str) -> str:
    """Collapse runs of whitespace and strip the ends."""

    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def slugify(value: str) -> str:
    """Return a lowercase ASCII-ish slug safe for generated filenames."""

    slug = _SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "unknown"
