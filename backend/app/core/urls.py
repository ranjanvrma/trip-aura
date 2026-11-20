"""Sanitising of URLs and identifiers that come from open data before they reach the API output."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_QID = re.compile(r"^Q[1-9][0-9]{0,11}$")
_CONTROL = re.compile(r"[\x00-\x20\x7f]")


def safe_http_url(value: object, max_length: int = 2000) -> str | None:
    """Return the URL if it is an absolute http(s) URL with a host, otherwise None.

    Drops javascript:, data:, protocol-relative and malformed values, and anything containing
    whitespace or control characters."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url or len(url) > max_length or _CONTROL.search(url):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    return url


def wikidata_qid(value: object) -> str | None:
    """'Q42' or None (OSM wikidata tags and SPARQL results are free text)."""
    if not isinstance(value, str):
        return None
    v = value.strip().split(";")[0].strip()
    return v if _QID.match(v) else None


_COMMONS_FILE = re.compile(r"^[^/\\#?<>\[\]{}|\x00-\x1f\x7f]{1,230}\.(jpe?g|png|gif|webp|tiff?|svg)$", re.I)


def commons_file(value: object) -> str | None:
    """The file name of a Wikimedia Commons image ("Hawa Mahal 2011.jpg"), taken from a Wikidata image (P18) value,
    which SPARQL returns as a Special:FilePath URL. None for anything that is not a plain image file name."""
    if not isinstance(value, str):
        return None
    name = unquote(value.strip().rsplit("/", 1)[-1] if "/" in value else value.strip()).replace("_", " ").strip()
    return name if _COMMONS_FILE.match(name) else None
