"""Download everything the backend fetches lazily, so a container starts warm.

Run at Docker build time (or once on a server):
    python scripts/prefetch.py

- GeoNames city index (city autocomplete, ~4 MB)
- sentence-embedding model (semantic matching, ~65 MB) unless SEMANTIC_ENABLED=false
- DuckDB httpfs extension (Overture Maps queries)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    s = get_settings()
    from app.nlp.city_index import CityIndex

    ix = CityIndex(s.data_dir, s.geonames_url, s.open_user_agent)
    ix.load()
    print(f"city index: {len(ix.cities)} cities")

    if s.semantic_enabled:
        from app.nlp.semantic import SemanticMatcher

        m = SemanticMatcher(s.semantic_model, s.data_dir)
        if not m.available:
            print(f"semantic model: FAILED ({m.status})")
            return 1
        m.similarity(["museums"], ["a museum"])
        print(f"semantic model: {m.status}")

    if s.overture_enabled:
        import duckdb

        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.close()
        print("duckdb httpfs: installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
