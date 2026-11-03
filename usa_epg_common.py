"""Shared helpers for the USA TV Next playlist and EPG generator."""

from __future__ import annotations

import re
import unicodedata


def clean_channel_name(name: str) -> str:
    """Collapse whitespace and trim a channel name."""
    return re.sub(r"\s+", " ", (name or "").strip())


def slugify(name: str) -> str:
    """Create a stable, readable identifier from a channel name."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    text = text.replace("&", " and ").replace("+", " plus ")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-+", "-", text)
    return text or "channel"


def canonical_id(name: str) -> str:
    """Return the XMLTV id used by both the playlist and the generated guide."""
    return f"{slugify(name)}.us"
