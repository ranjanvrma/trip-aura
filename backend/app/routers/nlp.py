from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ProviderRequestError
from app.nlp.registry import get_city_index
from app.nlp.trip_parser import parse_trip_text

router = APIRouter(prefix="/api/nlp", tags=["nlp"])


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # a free-text trip description (a short paragraph), longer than the 500-char form fields
    text: str = Field(min_length=3, max_length=2000)


class ParseResponse(BaseModel):
    fields: dict
    understood: list[str]
    notes: list[str]
    city: dict | None


@router.post("/parse-trip", response_model=ParseResponse)
def parse_trip(body: ParseRequest) -> ParseResponse:
    """Turn a free-text trip description into form fields (rule-based NLP, runs offline)."""
    index = get_city_index()
    notes: list[str] = []
    try:
        index.search("ab", 1)  # make sure the index is loaded
    except ProviderRequestError as exc:
        index = None
        notes.append(f"City recognition unavailable: {exc.message}")
    res = parse_trip_text(body.text, index)
    return ParseResponse(fields=res.fields, understood=res.understood, notes=notes + res.notes, city=res.city)
