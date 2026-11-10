"""Interest normalisation: typo-tolerant mapping of free text onto preset interests,
plus a small thesaurus so custom phrases ("history buff", "temples", "hiking")
also count towards the matching preset categories."""
from __future__ import annotations

from rapidfuzz import fuzz, process

from app.core.text import fold
from app.schemas.trip import PRESET_INTERESTS

# phrase -> preset interests it implies
THESAURUS: dict[str, list[str]] = {
    "history": ["history", "monuments"], "history buff": ["history", "monuments", "museums"],
    "historical": ["history", "monuments"], "heritage": ["history", "architecture", "monuments"],
    "temples": ["religious_sites"], "temple": ["religious_sites"], "churches": ["religious_sites", "architecture"],
    "mosques": ["religious_sites", "architecture"], "spiritual": ["religious_sites"], "religion": ["religious_sites"],
    "galleries": ["art"], "gallery": ["art"], "paintings": ["art", "museums"], "street art": ["art", "photography"],
    "hiking": ["nature", "adventure"], "trekking": ["nature", "adventure"], "outdoors": ["nature", "parks"],
    "beaches": ["nature"], "beach": ["nature"], "gardens": ["parks", "nature"], "garden": ["parks", "nature"],
    "animals": ["wildlife"], "zoo": ["wildlife"], "safari": ["wildlife", "adventure"], "birds": ["wildlife", "nature"],
    "forts": ["monuments", "history"], "castles": ["monuments", "history", "architecture"],
    "palaces": ["monuments", "architecture"], "buildings": ["architecture"], "skyline": ["architecture", "photography"],
    "views": ["photography"], "sunset": ["photography"], "sunsets": ["photography"], "instagram": ["photography"],
    "bazaar": ["markets", "shopping"], "bazaars": ["markets", "shopping"], "souvenirs": ["shopping", "markets"],
    "malls": ["shopping"], "theatre": ["cultural_centres"], "theater": ["cultural_centres"], "music": ["cultural_centres"],
    "culture": ["cultural_centres", "museums"], "festivals": ["cultural_centres"], "bars": ["nightlife"],
    "clubs": ["nightlife"], "party": ["nightlife"], "thrill": ["adventure"], "sports": ["adventure"],
    "kids": ["parks", "wildlife"], "science": ["museums"],
}


# "religious sites" -> "religious_sites": presets as they appear in free text
PRESETS_SPACED: dict[str, str] = {p.replace("_", " "): p for p in PRESET_INTERESTS}
_VOCABULARY = list(PRESETS_SPACED) + list(THESAURUS)


def normalise_interest(raw: str) -> tuple[list[str], str | None]:
    """-> (preset interests it maps to, corrected preset if it was a typo of one)."""
    t = fold(raw.replace("_", " ")).strip()
    if not t:
        return [], None
    if t in PRESETS_SPACED:
        return [PRESETS_SPACED[t]], None
    if t in THESAURUS:
        return list(THESAURUS[t]), None
    best = process.extractOne(t, _VOCABULARY, scorer=fuzz.ratio, score_cutoff=82)
    if best:
        key = best[0]
        if key in PRESETS_SPACED:
            return [PRESETS_SPACED[key]], PRESETS_SPACED[key]
        return list(THESAURUS[key]), None
    return [], None


def expand_interests(interests: list[str]) -> tuple[list[str], dict[str, str]]:
    """Returns (interests with typos corrected and implied presets added, {original: correction})."""
    out: list[str] = []
    corrections: dict[str, str] = {}
    for i in interests:
        mapped, corrected = normalise_interest(i)
        if corrected:
            corrections[i] = corrected
            if corrected not in out:
                out.append(corrected)
            continue
        if i not in out:
            out.append(i)
        for m in mapped:
            if m not in out:
                out.append(m)
    return out, corrections


# Descriptive phrases so short preset labels embed well for semantic matching
INTEREST_PHRASES = {
    "museums": "museum with exhibitions and collections", "monuments": "historic monument or landmark",
    "cultural_centres": "cultural centre, theatre or performance venue", "nature": "nature, scenery and green spaces",
    "parks": "public park or garden", "shopping": "shopping street, mall or boutiques",
    "architecture": "remarkable architecture and buildings", "photography": "scenic viewpoint, photogenic spot",
    "adventure": "adventure and outdoor activities", "history": "history and historic sites",
    "religious_sites": "temple, church, mosque or shrine", "art": "art gallery and artworks",
    "markets": "local market or bazaar", "wildlife": "zoo, wildlife and animals", "nightlife": "bars and nightlife",
}


def interest_phrase(interest: str) -> str:
    return INTEREST_PHRASES.get(interest, interest.replace("_", " "))
