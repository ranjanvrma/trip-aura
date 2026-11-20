"""Free signals of how real and how notable a place is, read from open data alone.

Open map data is uneven. Overture's machine tagging can file a travel agency as a cafe, most small eateries carry no
diet tag at all, and a city has dozens of neighbourhood parks that all match an interest in "parks" equally well. These
helpers let the planner tell them apart without any paid service:

- `looks_like_eatery`: a food place whose name says it is something else (a travel agency, a clinic, a salon).
- `name_diet_hint`: what an eatery's name says about its food ("Bar", "Chicken Corner", "Pure Veg", "भोजनालय").
- `notability`: 0 to 1 from facts the data already holds: a Wikidata entry, how many Wikipedia languages cover the
  place, whether two independent sources list it, and a known brand.
- `is_minor_park`: a park with none of that, typically a neighbourhood or sector park.
- `looks_like_sight`: not a rental, and not a neighbourhood or junction that open data filed as a historic site.

None of this changes the suitability score that is shown to the traveller: it only decides which places are offered,
and anything read from a name is labelled as a guess.
"""
from __future__ import annotations

import math
import re

from app.core.text import fold
from app.schemas.place import Place, PlaceKind

_SPLIT = re.compile(r"[\s,.;:!?/\\&()\[\]'’\"|+_-]+")

# names that say the place is not an eatery, whatever its category says
NOT_EATERY = {
    "travel", "travels", "traveller", "tour", "tours", "tourism", "yatra", "yatras", "agency", "agencies",
    "consultancy", "consultants", "hospital", "clinic", "diagnostics", "pathology", "dental", "school", "academy",
    "institute",
    "coaching", "bank", "atm", "salon", "parlour", "parlor", "spa", "pharmacy", "medical", "medicos", "chemist",
    "garage", "motors", "automobiles", "hardware", "electronics", "electricals", "mobiles", "jewellers", "jewelers",
    "furniture", "properties", "realty", "builders", "tailors", "boutique", "laundry", "gym", "fitness", "printers",
    # Hindi, as written in Devanagari
    "यात्रा", "ट्रेवल्स", "ट्रैवल्स", "टूर्स", "अस्पताल", "क्लिनिक", "स्कूल", "बैंक", "मेडिकल",
}
BAR = {"bar", "bars", "pub", "pubs", "brewery", "brewpub", "taproom", "tavern", "liquor", "wine", "wines", "beer",
       "beers", "daru", "theka", "बार", "ठेका", "शराब"}
NON_VEG = {"chicken", "mutton", "meat", "meats", "fish", "seafood", "kebab", "kebabs", "kabab", "kababs", "beef",
           "pork", "lamb", "butcher", "nonveg", "steakhouse", "steak", "steaks", "chicken's",
           # the words that name meat places in other languages travellers meet often
           "presunto", "presuntos", "carne", "carnes", "churrasco", "churrasqueira", "marisqueira", "marisco",
           "mariscos", "frango", "peixe", "jamon", "jamones", "asador", "pollo", "pollos", "wurst", "bratwurst",
           "schnitzel", "kebap", "चिकन", "मटन", "मीट"}
VEG = {"veg", "vegetarian", "vegan", "shudh", "vaishno", "vaishnav", "bhojnalaya", "haldiram", "haldirams",
       "bikanervala", "saravana", "udupi", "jain", "शुद्ध", "वैष्णो", "भोजनालय", "शाकाहारी"}
# a place to stay is never a sight, however well it is matched to Wikidata
LODGING = {"apartment", "apartments", "apartamento", "apartamentos", "flat", "flats", "homestay", "guesthouse",
           "hostel", "hostels", "airbnb", "rooms", "suites", "residency", "pg"}
# names of neighbourhoods and road junctions: a sight only when the data knows more about it (Chandni Chowk does)
LOCALITY = {"nagar", "chowk", "colony", "sector", "mohalla", "vihar", "enclave", "society", "puram", "kunj", "basti",
            "extension", "township", "नगर", "चौक", "कॉलोनी", "सेक्टर"}
# shops and businesses that open data filed as a sight ("Pujan Bhandar", "Commercial Complex")
SHOP = {"bhandar", "traders", "trader", "enterprises", "store", "stores", "shop", "shops", "showroom", "dealers",
        "wholesale", "commercial", "pvt", "ltd", "भंडार", "भण्डार", "स्टोर"}
# a sector, block or numbered park: "Sector 14 Park", "Park No. 3", "Block C Park"
_MINOR_PARK = re.compile(r"\b(sector|sec|block|ward|phase|colony|pocket|park\s*no)\b|\d", re.I)


def name_tokens(name: str) -> set[str]:
    """Words of a name, both as written (for scripts that folding would damage, like Devanagari) and folded."""
    raw = [t for t in _SPLIT.split(name.lower()) if t]
    return set(raw) | {fold(t) for t in raw}


def looks_like_eatery(place: Place) -> bool:
    return not (name_tokens(place.name) & NOT_EATERY)


def name_diet_hint(place: Place) -> str | None:
    """'bar', 'nonveg' or 'veg' when the name says so; None when it says nothing. "Non veg" is non-vegetarian."""
    tokens = name_tokens(place.name)
    if tokens & BAR:
        return "bar"
    if tokens & NON_VEG or {"non", "veg"} <= tokens:
        return "nonveg"
    if tokens & VEG:
        return "veg"
    return None


def notability(place: Place) -> float:
    """0 to 1: how sure the open data is that this is a real, known place worth a visit."""
    ids = place.external_ids
    score = 0.0
    if "wikidata" in ids:
        score += 0.35
    if place.prominence:
        score += min(0.4, 0.1 * math.log2(1 + place.prominence))   # 15 Wikipedia languages or more: the full 0.4
    if place.is_famous:
        score += 0.25
    if len({"osm", "overture", "wikidata"} & ids.keys()) >= 2:      # listed by two independent sources
        score += 0.15
    if ids.get("brand"):
        score += 0.1
    return min(1.0, score)


def is_minor_park(place: Place) -> bool:
    """A park the data knows nothing special about, or one named after a sector or block."""
    if place.kind != PlaceKind.PARK:
        return False
    return notability(place) < 0.2 or (bool(_MINOR_PARK.search(place.name)) and notability(place) < 0.35)


def looks_like_sight(place: Place) -> bool:
    """False for a rental listed as a sight, and for a neighbourhood, junction or shop ("Rishi Nagar", "Camp Chowk",
    "Pujan Bhandar") that open data filed as a sight with nothing else known about it. Parks are judged by
    is_minor_park instead."""
    tokens = name_tokens(place.name)
    if tokens & LODGING:
        return False
    if tokens & SHOP and place.kind != PlaceKind.PARK and notability(place) < 0.35:
        return False
    if place.kind != PlaceKind.PARK and tokens & LOCALITY and notability(place) < 0.35:
        return False
    return True
