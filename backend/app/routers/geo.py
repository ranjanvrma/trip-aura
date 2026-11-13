"""Autocomplete: city names (offline GeoNames index) and addresses near a city (Photon).

Nominatim's usage policy does not allow autocomplete, so addresses use Photon
(komoot's OSM geocoder built for search-as-you-type).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.core.errors import ProviderRequestError
from app.core.geo import degree_span, haversine_km
from app.core.text import fold
from app.nlp.registry import get_city_index

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/cities")
def city_suggestions(q: str = Query(min_length=2, max_length=100), limit: int = Query(8, ge=1, le=15)) -> dict:
    cities = get_city_index().search(q, limit)
    return {"query": q, "results": [c.to_dict() for c in cities],
            "attribution": "City data © GeoNames (CC BY 4.0)"}


# OSM tags for places to stay; these rank above streets and shops with a similar name
LODGING = {"hotel", "hostel", "guest_house", "motel", "apartment", "chalet", "resort", "camp_site"}
NEAR_KM = 40          # "in the destination"
FAR_KM = 150          # dropped when there are matches nearer than NEAR_KM


def _photon(url: str, ua: str, params: dict) -> list[dict]:
    r = httpx.get(url, params=params, timeout=8, headers={"User-Agent": ua})
    r.raise_for_status()
    return r.json().get("features", [])


def _suggestion(feat: dict) -> dict | None:
    p = feat.get("properties") or {}
    coords = (feat.get("geometry") or {}).get("coordinates") or []
    # skip features without a usable point (null geometry, short or non-numeric coordinates)
    if len(coords) < 2 or not all(isinstance(c, (int, float)) for c in coords[:2]):
        return None
    lng, lat = coords[:2]
    street = " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    parts = [p.get("name"), street, p.get("district") or p.get("locality"), p.get("city"), p.get("country")]
    label = ", ".join(dict.fromkeys(x for x in parts if x))
    if not label:
        return None
    return {"label": label, "name": p.get("name") or street or label, "lat": lat, "lng": lng,
            "kind": p.get("osm_value") or p.get("type")}


def rank_addresses(items: list[dict], q: str, lat: float | None, lng: float | None, limit: int) -> list[dict]:
    """Merge, de-duplicate and order suggestions: names that contain every typed word (anywhere, not only at the
    start) first, then places to stay, then nearer places. Far-away matches go when local ones exist."""
    words = fold(q).split()
    seen: set[tuple] = set()
    scored: list[tuple[float, int, dict]] = []
    for order, it in enumerate(items):
        key = (fold(it["name"]), round(it["lat"], 3), round(it["lng"], 3))
        if key in seen:
            continue
        seen.add(key)
        dist = haversine_km(lat, lng, it["lat"], it["lng"]) if lat is not None and lng is not None else None
        name = fold(it["name"])
        match = 3 if words and all(w in name for w in words) else 1 if any(w in name for w in words) else 0
        score = match + (2 if it.get("kind") in LODGING else 0) + (2 if dist is not None and dist <= NEAR_KM else 0)
        scored.append((-score, order, {**it, "_dist": dist}))
    if any(x[2]["_dist"] is not None and x[2]["_dist"] <= NEAR_KM for x in scored):
        scored = [x for x in scored if x[2]["_dist"] is None or x[2]["_dist"] <= FAR_KM]
    scored.sort(key=lambda x: (x[0], x[1]))
    return [{k: v for k, v in it.items() if k != "_dist"} for _, _, it in scored[:limit]]


@router.get("/addresses")
def address_suggestions(q: str = Query(min_length=2, max_length=100),
                        lat: float | None = Query(None, ge=-90, le=90),
                        lng: float | None = Query(None, ge=-180, le=180),
                        city: str | None = Query(None, max_length=100),
                        limit: int = Query(6, ge=1, le=10)) -> dict:
    """Two searches run together when the destination is known: one limited to the area around it, and one with the
    city name added (Photon's location bias alone lets "inn" match a river in Austria for a trip to Jaipur)."""
    s = get_settings()
    base: dict = {"limit": 10, "lang": "en"}
    queries: list[dict] = []
    if lat is not None and lng is not None:
        dlat, dlng = degree_span(lat, NEAR_KM)
        queries.append({**base, "q": q, "bbox": f"{lng - dlng},{lat - dlat},{lng + dlng},{lat + dlat}"})
        base.update({"lat": lat, "lon": lng, "zoom": 12, "location_bias_scale": 0.3})
    town = (city or "").split(",")[0].strip()
    queries.append({**base, "q": f"{q} {town}" if town and fold(town) not in fold(q) else q})
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        futures = [pool.submit(_photon, s.photon_url, s.open_user_agent, p) for p in queries]
    features: list[dict] = []
    errors: list[Exception] = []
    for f in futures:
        try:
            features += f.result()
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(exc)
    if len(errors) == len(futures):
        exc = errors[0]
        raise ProviderRequestError(f"Address suggestions are unavailable ({exc.__class__.__name__})") from exc
    items = [x for x in map(_suggestion, features) if x]
    return {"query": q, "results": rank_addresses(items, q, lat, lng, limit),
            "attribution": "Search by Photon, data © OpenStreetMap contributors"}
