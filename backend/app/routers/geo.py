"""Autocomplete: city names (offline GeoNames index) and addresses near a city (Photon).

Nominatim's usage policy does not allow autocomplete, so addresses use Photon
(komoot's OSM geocoder built for search-as-you-type).
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.core.errors import ProviderRequestError
from app.nlp.registry import get_city_index

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/cities")
def city_suggestions(q: str = Query(min_length=2, max_length=100), limit: int = Query(8, ge=1, le=15)) -> dict:
    cities = get_city_index().search(q, limit)
    return {"query": q, "results": [c.to_dict() for c in cities],
            "attribution": "City data © GeoNames (CC BY 4.0)"}


@router.get("/addresses")
def address_suggestions(q: str = Query(min_length=2, max_length=100),
                        lat: float | None = Query(None, ge=-90, le=90),
                        lng: float | None = Query(None, ge=-180, le=180), limit: int = Query(6, ge=1, le=10)) -> dict:
    s = get_settings()
    params: dict = {"q": q, "limit": limit, "lang": "en"}
    if lat is not None and lng is not None:
        params.update({"lat": lat, "lon": lng, "zoom": 12, "location_bias_scale": 0.3})
    try:
        r = httpx.get(s.photon_url, params=params, timeout=8, headers={"User-Agent": s.open_user_agent})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderRequestError(f"Address suggestions are unavailable ({exc.__class__.__name__})") from exc
    results = []
    for feat in data.get("features", []):
        p = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        # skip features without a usable point (null geometry, short or non-numeric coordinates)
        if len(coords) < 2 or not all(isinstance(c, (int, float)) for c in coords[:2]):
            continue
        lng_, lat_ = coords[:2]
        street = " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
        parts = [p.get("name"), street, p.get("district") or p.get("locality"), p.get("city"), p.get("country")]
        label = ", ".join(dict.fromkeys(x for x in parts if x))
        if not label:
            continue
        results.append({"label": label, "name": p.get("name") or street or label, "lat": lat_, "lng": lng_,
                        "kind": p.get("osm_value") or p.get("type")})
    return {"query": q, "results": results, "attribution": "Search by Photon, data © OpenStreetMap contributors"}
