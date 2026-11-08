"""Optional Anthropic-powered trip summary.

The LLM only rewrites facts already computed by the engines into a friendly
overview. It never chooses places, scores, prices or ratings, and the itinerary
is complete without it. Failures are reported in `ai_status`, never hidden.
"""
from __future__ import annotations

import json
import logging

from app.core.config import Settings
from app.schemas.itinerary import Itinerary, ItemType

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You write short, friendly travel itinerary overviews. Use ONLY the facts in the JSON the user "
    "provides. Do not add places, dishes, prices, ratings, opening hours or travel times that are not in it. "
    "Ratings come in two kinds that must never be merged: 'external_rating' (from the named provider) and "
    "'suitability' (our personalised score out of 5). If data_source is 'mock', say once that the plan uses "
    "demo data. Mention costs only as estimates unless marked verified. Write 1 short intro paragraph, then "
    "one line per day starting with 'Day N:'. Plain text, under 220 words."
)


def _facts(it: Itinerary) -> dict:
    days = []
    for d in it.days:
        stops = []
        for i in d.items:
            if i.type not in (ItemType.ACTIVITY, ItemType.MEAL) or i.place is None:
                continue
            er = i.place.external_rating
            stops.append({
                "time": i.start, "type": i.type.value, "name": i.place.name,
                "external_rating": ({"provider": er.provider.value, "rating": er.rating} if er and er.rating else None),
                "suitability": i.suitability.score if i.suitability else None,
                "why": (i.suitability.reasons[:2] if i.suitability else []),
            })
        days.append({"day": d.day_number, "weekday": d.weekday, "stops": stops})
    b = it.budget
    return {
        "data_source": it.data_source.value,
        "city": it.request.destination_city, "pace": it.request.pace.value,
        "budget": {"currency": b.currency, "total": b.total_budget, "planned": b.planned_total,
                   "over_budget": b.over_budget, "estimated_part": b.estimated_total},
        "days": days,
        "popular_dishes": [d.name for d in it.popular_dishes],
    }


def summarize(it: Itinerary, settings: Settings) -> tuple[str | None, str]:
    if not settings.ai_enabled:
        return None, "disabled"
    if not settings.anthropic_api_key.strip():
        return None, "not_configured: AI_ENABLED=true but ANTHROPIC_API_KEY is empty"
    if not settings.anthropic_model.strip():
        return None, "not_configured: AI_ENABLED=true but ANTHROPIC_MODEL is empty"
    try:
        import anthropic
    except ImportError:
        return None, "not_configured: anthropic package not installed"

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=1)
    try:
        resp = client.beta.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(_facts(it), ensure_ascii=False)}],
        )
    except anthropic.RateLimitError:
        log.warning("Anthropic rate limited")
        return None, "error: rate limited by Anthropic API"
    except anthropic.APIStatusError as exc:
        log.warning("Anthropic API error %s", exc.status_code)
        return None, f"error: Anthropic API returned {exc.status_code}"
    except anthropic.APIConnectionError:
        log.warning("Anthropic connection error")
        return None, "error: could not reach Anthropic API"

    if resp.stop_reason == "refusal":
        return None, "error: model declined to summarise"
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    return (text or None), ("ok" if text else "error: empty response")
