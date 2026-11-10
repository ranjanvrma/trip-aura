"""Pure text helpers shared by engines, NLP and providers (no network)."""
from __future__ import annotations

import unicodedata


def fold(s: str) -> str:
    """Lower-case, accent-stripped form for matching ('Pastéis' -> 'pasteis')."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()
