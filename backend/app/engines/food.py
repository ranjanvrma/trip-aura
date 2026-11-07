"""Food recommendation engine.

- Dietary compatibility is a hard filter with explicit confidence levels.
- Dishes are called "popular" ONLY when at least two separate reviews mention
  them. One mention is reported as "mentioned"; cuisine-based ideas without
  review evidence are labelled "suggestion".
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from app.core.geo import haversine_km
from app.engines.recommendation import ScoringContext, score_food_place
from app.schemas.common import LatLng
from app.schemas.itinerary import DishSuggestion, FoodRecommendation
from app.schemas.place import Place, SuitabilityScore

# name -> diet tags it satisfies ("veg" implies vegetarian, "vegan" fully plant-based,
# "jain" no root vegetables/onion/garlic when prepared that way, "egg", "nonveg")
DISHES: dict[str, set[str]] = {
    "dal baati churma": {"veg", "jain"}, "gatte ki sabzi": {"veg"}, "ker sangri": {"veg", "vegan", "jain"},
    "laal maas": {"nonveg"}, "pyaaz kachori": {"veg", "vegan"}, "mirchi vada": {"veg", "vegan"},
    "ghevar": {"veg", "jain"}, "rabri": {"veg", "jain"}, "lassi": {"veg", "jain"}, "kesar lassi": {"veg", "jain"},
    "masala chai": {"veg", "jain"}, "kulhad chai": {"veg", "jain"}, "dahi bhalle": {"veg"},
    "chole bhature": {"veg"}, "paratha": {"veg"}, "masala dosa": {"veg", "vegan"}, "idli": {"veg", "vegan", "jain"},
    "filter coffee": {"veg"}, "thali": {"veg"}, "jain thali": {"veg", "jain"}, "momos": {"veg", "nonveg"},
    "chicken momos": {"nonveg"}, "seekh kebab": {"nonveg"}, "kebab": {"nonveg"}, "butter chicken": {"nonveg"},
    "biryani": {"nonveg", "veg"}, "egg bhurji": {"egg", "nonveg"}, "eggs benedict": {"egg", "nonveg"},
    "pancakes": {"egg", "veg"}, "vegan pancakes": {"veg", "vegan"}, "avocado toast": {"veg", "vegan"},
    "pizza": {"veg", "nonveg"}, "pasta": {"veg", "nonveg"}, "millet bowl": {"veg", "vegan"},
    "cold coffee": {"veg"}, "samosa": {"veg", "vegan"}, "pav bhaji": {"veg"}, "paneer tikka": {"veg"},
    "falafel": {"veg", "vegan"}, "ramen": {"nonveg", "veg"}, "sushi": {"nonveg"}, "croissant": {"veg", "egg"},
    # worldwide additions (diet tags describe the usual preparation; always check locally)
    "pastel de nata": {"veg", "egg"}, "pasteis de nata": {"veg", "egg"}, "pasteis de belem": {"veg", "egg"},
    "caldo verde": {"nonveg", "veg"}, "sardines": {"nonveg"}, "ginjinha": {"veg", "vegan"}, "bacalhau": {"nonveg"}, "francesinha": {"nonveg"}, "bifana": {"nonveg"},
    "paella": {"nonveg"}, "tapas": {"veg", "nonveg"}, "churros": {"veg", "egg"}, "gazpacho": {"veg", "vegan"},
    "tortilla espanola": {"veg", "egg"}, "patatas bravas": {"veg", "vegan"}, "jamon": {"nonveg"},
    "risotto": {"veg", "nonveg"}, "gelato": {"veg"}, "tiramisu": {"veg", "egg"}, "lasagne": {"nonveg", "veg"},
    "carbonara": {"nonveg", "egg"}, "margherita": {"veg"}, "focaccia": {"veg", "vegan"}, "arancini": {"veg", "nonveg"},
    "crepe": {"veg", "egg"}, "croque monsieur": {"nonveg"}, "baguette": {"veg", "vegan"}, "ratatouille": {"veg", "vegan"},
    "macarons": {"veg", "egg"}, "bouillabaisse": {"nonveg"}, "escargots": {"nonveg"}, "onion soup": {"veg"},
    "bratwurst": {"nonveg"}, "pretzel": {"veg", "vegan"}, "schnitzel": {"nonveg", "egg"}, "currywurst": {"nonveg"},
    "strudel": {"veg"}, "sachertorte": {"veg", "egg"}, "goulash": {"nonveg"}, "pierogi": {"veg", "nonveg"},
    "fish and chips": {"nonveg"}, "full english breakfast": {"nonveg", "egg"}, "scones": {"veg", "egg"},
    "sunday roast": {"nonveg"}, "pad thai": {"nonveg", "egg", "veg"}, "green curry": {"nonveg", "veg"},
    "tom yum": {"nonveg"}, "som tam": {"nonveg", "veg"}, "mango sticky rice": {"veg", "vegan"},
    "pho": {"nonveg"}, "banh mi": {"nonveg"}, "spring rolls": {"veg", "nonveg"}, "dim sum": {"nonveg", "veg"},
    "dumplings": {"veg", "nonveg"}, "peking duck": {"nonveg"}, "hot pot": {"nonveg", "veg"}, "baozi": {"veg", "nonveg"},
    "tempura": {"nonveg", "veg", "egg"}, "udon": {"veg", "nonveg"}, "okonomiyaki": {"nonveg", "egg"},
    "takoyaki": {"nonveg"}, "matcha": {"veg", "vegan", "jain"}, "bibimbap": {"veg", "nonveg", "egg"},
    "kimchi": {"veg", "vegan"}, "bulgogi": {"nonveg"}, "tteokbokki": {"veg"}, "tacos": {"nonveg", "veg"},
    "guacamole": {"veg", "vegan"}, "enchiladas": {"nonveg", "veg"}, "mole": {"nonveg"}, "tamales": {"nonveg", "veg"},
    "ceviche": {"nonveg"}, "empanadas": {"nonveg", "veg"}, "asado": {"nonveg"}, "feijoada": {"nonveg"},
    "pao de queijo": {"veg", "egg"}, "acai": {"veg", "vegan"}, "baklava": {"veg"}, "doner kebab": {"nonveg"},
    "meze": {"veg", "nonveg"}, "simit": {"veg", "vegan"}, "turkish delight": {"veg", "vegan"},
    "souvlaki": {"nonveg"}, "moussaka": {"nonveg"}, "gyros": {"nonveg"}, "spanakopita": {"veg", "egg"},
    "hummus": {"veg", "vegan"}, "shawarma": {"nonveg"}, "tabbouleh": {"veg", "vegan"}, "manakish": {"veg"},
    "tagine": {"nonveg", "veg"}, "couscous": {"veg", "vegan", "nonveg"}, "mint tea": {"veg", "vegan", "jain"},
    "koshari": {"veg", "vegan"}, "injera": {"veg", "vegan"}, "jollof rice": {"nonveg", "veg"},
    "nasi goreng": {"nonveg", "egg"}, "satay": {"nonveg"}, "rendang": {"nonveg"}, "laksa": {"nonveg"},
    "nasi lemak": {"nonveg", "egg"}, "hainanese chicken rice": {"nonveg"}, "chilli crab": {"nonveg"},
    "adobo": {"nonveg"}, "momo": {"veg", "nonveg"}, "dal bhat": {"veg", "vegan"}, "hoppers": {"veg", "egg"},
    "kottu": {"nonveg", "egg", "veg"}, "vada pav": {"veg", "vegan"}, "pani puri": {"veg", "vegan"},
    "butter naan": {"veg"}, "rogan josh": {"nonveg"}, "dosa": {"veg", "vegan"}, "uttapam": {"veg", "vegan"},
    "burger": {"nonveg", "veg"}, "bagel": {"veg", "vegan"}, "cheesecake": {"veg", "egg"}, "barbecue": {"nonveg"},
    "poutine": {"veg"}, "meat pie": {"nonveg"}, "pavlova": {"veg", "egg"}, "stroopwafel": {"veg", "egg"},
    "waffles": {"veg", "egg"}, "frites": {"veg", "vegan"}, "smorrebrod": {"nonveg", "veg"}, "cinnamon bun": {"veg", "egg"},
}
CUISINE_SUGGESTIONS: dict[str, list[str]] = {
    "rajasthani": ["dal baati churma", "gatte ki sabzi", "ker sangri", "laal maas"],
    "north_indian": ["paneer tikka", "chole bhature", "paratha"],
    "south_indian": ["masala dosa", "idli", "filter coffee"],
    "street_food": ["pyaaz kachori", "samosa", "pav bhaji"],
    "sweets": ["ghevar", "rabri"], "cafe": ["cold coffee", "croissant"], "mughlai": ["seekh kebab", "biryani"],
    "chinese": ["dumplings", "dim sum"], "italian": ["pizza", "pasta", "risotto"], "vegan": ["millet bowl", "falafel"],
    "jain": ["jain thali"], "tea": ["masala chai"], "drinks": ["lassi"],
    "indian": ["thali", "paneer tikka", "biryani"], "portuguese": ["pastel de nata", "bacalhau", "bifana"],
    "spanish": ["tapas", "paella", "patatas bravas"], "tapas": ["tapas", "patatas bravas"],
    "french": ["crepe", "onion soup", "ratatouille"], "crepe": ["crepe"], "german": ["bratwurst", "schnitzel", "pretzel"],
    "austrian": ["schnitzel", "strudel"], "british": ["fish and chips", "sunday roast"], "fish_and_chips": ["fish and chips"],
    "pizza": ["margherita"], "thai": ["pad thai", "green curry", "som tam"], "vietnamese": ["pho", "banh mi"],
    "japanese": ["ramen", "tempura", "udon"], "sushi": ["sushi"], "ramen": ["ramen"], "korean": ["bibimbap", "kimchi"],
    "mexican": ["tacos", "guacamole", "enchiladas"], "peruvian": ["ceviche"], "argentinian": ["asado", "empanadas"],
    "brazilian": ["feijoada", "pao de queijo"], "turkish": ["meze", "baklava", "doner kebab"], "kebab": ["doner kebab"],
    "greek": ["souvlaki", "moussaka", "spanakopita"], "lebanese": ["hummus", "falafel", "manakish"],
    "middle_eastern": ["hummus", "falafel", "shawarma"], "moroccan": ["tagine", "couscous", "mint tea"],
    "ethiopian": ["injera"], "indonesian": ["nasi goreng", "satay"], "malaysian": ["nasi lemak", "laksa"],
    "singaporean": ["hainanese chicken rice", "laksa"], "nepalese": ["momo", "dal bhat"], "sri_lankan": ["hoppers", "kottu"],
    "american": ["burger", "cheesecake"], "burger": ["burger"], "bbq": ["barbecue"], "coffee_shop": ["croissant"],
    "bakery": ["croissant"], "ice_cream": ["gelato"], "dessert": ["gelato"], "vegetarian": ["falafel", "hummus"],
    "chinese_restaurant": ["dumplings"], "dumpling": ["dumplings"], "noodle": ["udon"],
}
DIET_TO_TAG = {"vegetarian": "veg", "vegan": "vegan", "jain": "jain", "eggetarian": "egg", "non_vegetarian": "nonveg"}


@dataclass
class DietCheck:
    ok: bool
    confidence: str          # "confirmed" | "likely" | "unverified"
    reasons: list[str]


def diet_check(place: Place, diets: list[str]) -> DietCheck:
    if not diets:
        return DietCheck(True, "confirmed", [])
    d = place.diet
    search_tags = {c.removeprefix("search:") for c in place.categories if c.startswith("search:")}
    reasons: list[str] = []
    confidence = "confirmed"
    for diet in diets:
        if diet == "non_vegetarian":
            continue  # any restaurant works; non-veg options are a bonus
        if d is None or not d.known:
            if diet in search_tags:
                confidence = "likely"
                reasons.append(f"Returned by a '{diet}' search; menu not verified")
                continue
            if diet == "vegetarian" and d is not None and d.vegetarian_options:
                continue
            confidence = "unverified"
            reasons.append(f"No verified {diet.replace('_', ' ')} information")
            continue
        if diet == "vegetarian":
            if not (d.vegetarian_only or d.vegetarian_options):
                return DietCheck(False, "confirmed", ["No vegetarian options"])
            reasons.append("Pure vegetarian" if d.vegetarian_only else "Has vegetarian options")
        elif diet in ("vegan", "jain"):
            has = d.vegan_options if diet == "vegan" else d.jain_options
            label = "vegan options" if diet == "vegan" else "Jain food"
            if not has:
                if diet in search_tags:
                    confidence = "likely"
                    reasons.append(f"Returned by a {diet} food search; menu not verified")
                    continue
                return DietCheck(False, "confirmed", [f"No {label}"])
            reasons.append(f"{label[0].upper() + label[1:]} available")
        elif diet == "eggetarian":
            if not (d.vegetarian_options or d.vegetarian_only or d.egg_options):
                return DietCheck(False, "confirmed", ["No vegetarian or egg options"])
            reasons.append("Egg dishes available" if d.egg_options else "Vegetarian options (no egg dishes listed)")
        else:
            reasons.append(f"Custom preference '{diet}' could not be checked automatically")
            confidence = "unverified" if confidence == "confirmed" else confidence
    if "non_vegetarian" in diets and d is not None and d.non_veg:
        reasons.append("Serves non-vegetarian dishes")
    return DietCheck(True, confidence, reasons)


def food_match_component(place: Place, req_categories: list[str], check: DietCheck) -> float:
    if req_categories:
        base = 1.0 if any(c in place.food_categories for c in req_categories) else 0.35
    else:
        base = 0.65
    bonus = {"confirmed": 0.0, "likely": -0.1, "unverified": -0.25}[check.confidence]
    if "brand" in place.external_ids:
        bonus -= 0.1   # chains are fine, but local places fit a trip better
    return max(0.0, min(1.0, base + bonus))


def _dish_allowed(dish: str, diets: list[str]) -> bool:
    """Unknown dishes are allowed only when the user has no strict diet (we cannot verify ingredients)."""
    from app.providers.open.wikimedia import fold

    tags = DISHES.get(fold(dish), set())
    strict = [DIET_TO_TAG[d] for d in diets if d in DIET_TO_TAG and d != "non_vegetarian"]
    if not strict:
        return True
    for tag in strict:
        if tag == "egg":
            if not tags & {"veg", "egg"}:
                return False
        elif tag not in tags:
            return False
    return True


def _mentions(place: Place) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    for review in place.reviews:
        text = review.text.lower()
        hits = [d for d in DISHES if re.search(rf"\b{re.escape(d)}\b", text)]
        # prefer the longest match ("kesar lassi" over "lassi") within one review
        hits = [h for h in hits if not any(h != o and h in o for o in hits)]
        for h in hits:
            found[h].append(review.text)
    return found


def dish_suggestions(place: Place, diets: list[str]) -> list[DishSuggestion]:
    out: list[DishSuggestion] = []
    for dish, texts in sorted(_mentions(place).items(), key=lambda kv: -len(kv[1])):
        if not _dish_allowed(dish, diets):
            continue
        source = place.reviews[0].source if place.reviews else None
        status = "popular" if len(texts) >= 2 else "mentioned"
        out.append(DishSuggestion(name=dish.title(), status=status, evidence=[t[:140] for t in texts[:2]],
                                  evidence_source=source, mention_count=len(texts)))
    have = {d.name.lower() for d in out}
    for cuisine in place.cuisines:
        for dish in CUISINE_SUGGESTIONS.get(cuisine, []):
            if dish not in have and _dish_allowed(dish, diets):
                out.append(DishSuggestion(name=dish.title(), status="suggestion", evidence=[],
                                          evidence_source=None, mention_count=0))
                have.add(dish)
    return out[:5]


def city_popular_dishes(places: list[Place], diets: list[str]) -> list[DishSuggestion]:
    """Dishes mentioned in reviews of at least two different places."""
    by_dish: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for p in places:
        for dish, texts in _mentions(p).items():
            by_dish[dish].append((p.name, texts[0]))
    out = []
    for dish, refs in sorted(by_dish.items(), key=lambda kv: -len(kv[1])):
        if len(refs) < 2 or not _dish_allowed(dish, diets):
            continue
        src = places[0].reviews[0].source if places and places[0].reviews else None
        out.append(DishSuggestion(name=dish.title(), status="popular",
                                  evidence=[f"{name}: \"{text[:100]}\"" for name, text in refs[:3]],
                                  evidence_source=src, mention_count=len(refs)))
    return out[:8]


@dataclass
class FoodCandidate:
    place: Place
    check: DietCheck
    base_score: SuitabilityScore
    food_match: float


class FoodEngine:
    def __init__(self, ctx: ScoringContext, places: list[Place]):
        self.ctx = ctx
        self.candidates: list[FoodCandidate] = []
        self.rejected: list[tuple[Place, str]] = []
        for p in places:
            chk = diet_check(p, ctx.req.food_preferences)
            if not chk.ok:
                self.rejected.append((p, "; ".join(chk.reasons)))
                continue
            fm = food_match_component(p, ctx.req.food_categories, chk)
            self.candidates.append(FoodCandidate(p, chk, score_food_place(p, ctx, fm, chk.reasons), fm))

    def pick(self, meal: str, near: LatLng, minute: int, weekday: int, exclude: set[str],
             max_km: float = 3.0, max_cost: float | None = None,
             duration: int = 45) -> tuple[FoodCandidate, SuitabilityScore] | None:
        """Best open restaurant for this meal near `near`. Expands the radius if needed."""
        for radius in (max_km, max_km * 2, max_km * 4):
            best: tuple[float, FoodCandidate, SuitabilityScore] | None = None
            for c in self.candidates:
                p = c.place
                if p.id in exclude or (p.best_time and meal not in p.best_time):
                    continue
                if max_cost is not None and p.avg_cost_per_person and p.avg_cost_per_person.amount > max_cost:
                    continue
                if not is_open_for(p, weekday, minute, duration):
                    continue
                km = haversine_km(near.lat, near.lng, p.location.lat, p.location.lng)
                if km > radius:
                    continue
                s = score_food_place(p, self.ctx, c.food_match, c.check.reasons, origin=near)
                if best is None or s.score > best[0]:
                    best = (s.score, c, s)
            if best:
                return best[1], best[2]
        return None

    def recommendations(self, limit: int = 10) -> list[FoodRecommendation]:
        ranked = sorted(self.candidates, key=lambda c: -c.base_score.score)[:limit]
        return [FoodRecommendation(place=c.place, suitability=c.base_score, meal_types=c.place.best_time,
                                   dishes=dish_suggestions(c.place, self.ctx.req.food_preferences),
                                   diet_match=c.check.reasons + [f"Diet info: {c.check.confidence}"])
                for c in ranked]


def is_open_for(place: Place, weekday: int, minute: int, duration: int) -> bool:
    from app.core.timeutil import hm_to_min

    oh = place.opening_hours
    if oh is None or not oh.known:
        return True
    for r in oh.weekly.get(weekday, []):
        if hm_to_min(r.open) <= minute and minute + duration <= hm_to_min(r.close):
            return True
    return False
