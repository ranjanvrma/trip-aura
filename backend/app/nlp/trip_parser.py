"""Natural-language trip description -> structured TripRequest fields.

Example: "4 days in Lisboa with my wife, vegetarian, we love museums, street art and
sunsets, budget 900 euros, staying at Hotel Avenida Palace, relaxed pace, mostly metro"

Rule-based (regex + lexicons + typo-tolerant matching + the GeoNames city index), so
it works offline and deterministically. Every extracted field is reported in
`understood`, and anything ambiguous in `notes`, so the user can check the form.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.core.currencies import SUPPORTED_CURRENCIES
from app.nlp.interests import THESAURUS, normalise_interest
from app.providers.open.wikimedia import fold
from app.schemas.trip import PRESET_INTERESTS

NUMBER_WORDS = {"one": 1, "a": 1, "an": 1, "two": 2, "couple of": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14}
_NUM = r"(\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
CURRENCY_WORDS = {
    "₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "rupee": "INR", "rupees": "INR",
    "$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD", "bucks": "USD",
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "quid": "GBP",
    "¥": "JPY", "jpy": "JPY", "yen": "JPY", "baht": "THB", "thb": "THB", "aud": "AUD", "cad": "CAD",
    "chf": "CHF", "francs": "CHF", "sgd": "SGD", "yuan": "CNY", "rmb": "CNY", "won": "KRW", "lira": "TRY",
    "rand": "ZAR", "ringgit": "MYR", "pesos": "MXN",
}
DIETS = {
    "jain": "jain", "vegan": "vegan", "plant based": "vegan", "plant-based": "vegan",
    "eggetarian": "eggetarian", "eggitarian": "eggetarian", "vegetarian": "vegetarian", "veggie": "vegetarian",
    "pure veg": "vegetarian", "veg only": "vegetarian", "no meat": "vegetarian", "non veg": "non_vegetarian",
    "non-veg": "non_vegetarian", "non vegetarian": "non_vegetarian", "non-vegetarian": "non_vegetarian",
    "eat meat": "non_vegetarian", "meat lover": "non_vegetarian", "seafood": "non_vegetarian",
}
FOOD_CATS = {
    "street food": "street_food", "street-food": "street_food", "cafe": "cafes", "cafes": "cafes", "coffee": "cafes",
    "fine dining": "fine_dining", "fancy restaurants": "fine_dining", "michelin": "fine_dining",
    "local food": "local_cuisine", "local cuisine": "local_cuisine", "local dishes": "local_cuisine",
    "authentic food": "local_cuisine", "cheap eats": "budget_restaurants", "budget food": "budget_restaurants",
    "budget restaurants": "budget_restaurants", "cheap food": "budget_restaurants",
}
TRANSPORT = {
    "walk": "walking", "walking": "walking", "on foot": "walking", "metro": "metro", "subway": "metro",
    "underground": "metro", "tube": "metro", "bus": "bus", "buses": "bus", "train": "train", "trains": "train",
    "cab": "cab", "cabs": "cab", "taxi": "cab", "taxis": "cab", "uber": "cab", "ola": "cab", "grab": "cab",
    "auto": "auto", "autos": "auto", "rickshaw": "auto", "tuk tuk": "auto", "tuk-tuk": "auto",
    "car": "personal_vehicle", "drive": "personal_vehicle", "driving": "personal_vehicle",
    "rental car": "personal_vehicle", "own vehicle": "personal_vehicle", "scooter": "personal_vehicle",
    "bike": "personal_vehicle", "public transport": ["metro", "bus"], "public transit": ["metro", "bus"],
}
PACES = {
    "relaxed": "relaxed", "relaxing": "relaxed", "slow": "relaxed", "chill": "relaxed", "easy going": "relaxed",
    "leisurely": "relaxed", "laid back": "relaxed", "no rush": "relaxed",
    "moderate": "moderate", "balanced": "moderate", "normal pace": "moderate",
    "packed": "packed", "busy": "packed", "fast paced": "packed", "fast-paced": "packed", "see everything": "packed",
    "as much as possible": "packed", "action packed": "packed", "hectic": "packed",
}
ACCOM_TYPES = {"hotel": "hotel", "airbnb": "airbnb", "hostel": "hostel", "dorm": "dorm", "guesthouse": "hotel",
               "guest house": "hotel", "homestay": "private_property", "apartment": "airbnb", "villa": "private_property",
               "friend's place": "private_property", "friends place": "private_property", "resort": "hotel"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], start=1)}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class ParseResult:
    fields: dict = field(default_factory=dict)
    understood: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    city: dict | None = None


def _num(tok: str) -> int | None:
    tok = tok.strip().lower()
    if tok.isdigit():
        return int(tok)
    return NUMBER_WORDS.get(tok)


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def _amount(raw: str, suffix: str | None) -> float:
    v = float(raw.replace(",", ""))
    s = (suffix or "").lower()
    if s in ("k", "thousand"):
        v *= 1000
    elif s in ("lakh", "lakhs", "lac"):
        v *= 100_000
    elif s in ("m", "mn", "million"):
        v *= 1_000_000
    return v


def parse_budget(text: str) -> tuple[float, str | None] | None:
    sym = r"(₹|\$|€|£|¥|rs\.?|inr|usd|eur|gbp|jpy)"
    amt = r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lac|m|mn|million)?\b"
    words = "|".join(sorted((re.escape(w) for w in CURRENCY_WORDS if w.isalpha() and len(w) > 2), key=len, reverse=True))
    patterns = [
        rf"{sym}\s*{amt}",                                     # $600, rs 40,000, € 2k
        rf"{amt}\s*({words}|{sym})",                           # 600 euros, 40k inr
        rf"budget\D{{0,15}}?{amt}",                            # budget of 600 (no currency)
    ]
    t = text.lower()
    for i, p in enumerate(patterns):
        m = re.search(p, t)
        if not m:
            continue
        if i == 0:
            cur, value, suf = m.group(1), m.group(2), m.group(3)
        elif i == 1:
            value, suf, cur = m.group(1), m.group(2), m.group(3)
        else:
            value, suf, cur = m.group(1), m.group(2), None
        code = CURRENCY_WORDS.get(cur.strip(".") if cur else "", None) if cur else None
        if cur and not code:
            code = CURRENCY_WORDS.get(cur)
        return _amount(value, suf), code
    return None


def parse_date(text: str, today: dt.date) -> dt.date | None:
    t = text.lower()
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", t) \
        or re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m:
        a, b = m.group(1), m.group(2)
        day, mon = (int(a), MONTHS[b]) if a.isdigit() else (int(b), MONTHS[a])
        year = today.year if (mon, day) >= (today.month, today.day) else today.year + 1
        try:
            return dt.date(year, mon, day)
        except ValueError:
            return None
    if _has(t, "tomorrow"):
        return today + dt.timedelta(days=1)
    if _has(t, "today"):
        return today
    m = re.search(r"\b(?:this|next|on)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", t)
    if m:
        target = WEEKDAYS.index(m.group(1))
        delta = (target - today.weekday()) % 7 or 7
        return today + dt.timedelta(days=delta)
    if _has(t, "next weekend") or _has(t, "this weekend"):
        return today + dt.timedelta(days=(5 - today.weekday()) % 7 or 7)
    return None


def _find_city(text: str, city_index) -> dict | None:
    if city_index is None:
        return None
    # 1) explicit "in/to/visit X" phrases, longest capitalised chunk first
    cands = re.findall(r"\b(?:in|to|visit|visiting|explore|exploring|trip to|holiday in|vacation in)\s+"
                       r"([A-ZÀ-ɏ][\wÀ-ɏ'.-]*(?:\s+[A-ZÀ-ɏ][\wÀ-ɏ'.-]*){0,3})", text)
    # 2) lower-case "to new york city" style phrases after a travel preposition
    cands += re.findall(r"\b(?:in|to|visit|visiting|explore|exploring)\s+((?:[a-zà-ɏ][\wà-ɏ'.-]*\s*){1,3})",
                        text)
    # 3) any capitalised phrase
    cands += re.findall(r"\b([A-ZÀ-ɏ][\wÀ-ɏ'.-]+(?:\s+[A-ZÀ-ɏ][\wÀ-ɏ'.-]+){0,2})", text)
    skip = {"i", "we", "my", "our", "budget", "staying", "hotel", "airbnb", "hostel", "vegetarian", "vegan", "jain",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"} | set(MONTHS)
    for chunk in cands:
        words = chunk.split()
        for n in range(len(words), 0, -1):  # longest prefix first ("New York City" before "New")
            phrase = " ".join(words[:n])
            if fold(phrase) in skip or len(phrase) < 3:
                continue
            exact = city_index.exact(phrase)          # name or alternate name ("Lisboa", "Bombay")
            if exact:
                return exact.to_dict()
            if len(phrase) >= 5:                       # typo tolerance ("Barcelonna")
                c = city_index.best_match(phrase)
                if c and fuzz.ratio(fold(phrase), fold(c.name)) >= 85:
                    return c.to_dict()
    return None


def _match_terms(text: str, table: dict) -> list:
    found = []
    for phrase in sorted(table, key=len, reverse=True):
        if _has(text, phrase):
            val = table[phrase]
            for v in (val if isinstance(val, list) else [val]):
                if v not in found:
                    found.append(v)
    return found


def parse_trip_text(text: str, city_index=None, today: dt.date | None = None) -> ParseResult:
    today = today or dt.date.today()
    res = ParseResult()
    raw = text.strip()
    t = " " + fold(raw) + " "
    f = res.fields

    # destination
    city = _find_city(raw, city_index)
    if city:
        res.city = city
        f["destination_city"] = city["query"]
        res.understood.append(f"Destination: {city['display']}")

    # days
    m = re.search(rf"\b{_NUM}\s*(?:-\s*)?(day|days|night|nights)\b", t)
    if m and _num(m.group(1)):
        n = _num(m.group(1))
        days = n + 1 if m.group(2).startswith("night") else n
        f["num_days"] = max(1, min(14, days))
        res.understood.append(f"{f['num_days']} day(s)")
    elif _has(t, "long weekend"):
        f["num_days"] = 3
        res.understood.append("3 days (long weekend)")
    elif _has(t, "weekend"):
        f["num_days"] = 2
        res.understood.append("2 days (weekend)")
    elif re.search(r"\b(a|one) week\b", t):
        f["num_days"] = 7
        res.understood.append("7 days")
    elif re.search(r"\b(two|2) weeks\b", t):
        f["num_days"] = 14
        res.understood.append("14 days")

    # travellers
    m = re.search(rf"\b(?:we are|we're|group of|family of|party of)?\s*{_NUM}\s*(people|persons|adults|travell?ers|"
                  r"friends|of us|pax|guests)\b", t)
    m2 = re.search(r"\b(?:family|group|party) of (\d+)\b", t)
    if m2:
        f["travelers"] = int(m2.group(1))
    elif m and _num(m.group(1)):
        f["travelers"] = _num(m.group(1))
    elif re.search(r"\b(with my|with our) (wife|husband|partner|girlfriend|boyfriend|spouse)\b|\bcouple\b|\bhoneymoon\b", t):
        f["travelers"] = 2
    elif re.search(r"\b(solo|alone|by myself|on my own)\b", t):
        f["travelers"] = 1
    if "travelers" in f:
        f["travelers"] = max(1, min(20, f["travelers"]))
        res.understood.append(f"{f['travelers']} traveller(s)")

    # budget
    b = parse_budget(raw)
    if b:
        amount, code = b
        f["budget"] = round(amount, 2)
        if code and code in SUPPORTED_CURRENCIES:
            f["currency"] = code
        elif code:
            res.notes.append(f"Currency {code} is not supported; pick one in the form.")
        res.understood.append(f"Budget {amount:,.0f} {f.get('currency', '(currency not stated)')}")
        if re.search(r"\b(per day|a day|daily|per night)\b", t) and "num_days" in f:
            f["budget"] = round(amount * f["num_days"], 2)
            res.understood.append(f"(per-day budget x {f['num_days']} days = {f['budget']:,.0f})")

    # start date
    d = parse_date(raw, today)
    if d:
        f["start_date"] = d.isoformat()
        res.understood.append(f"Starting {d.strftime('%a %d %b %Y')}")

    # accommodation
    m = re.search(r"\b(?:staying|stay|we're staying|i'm staying|booked)\s+(?:at|in)\s+(?:the\s+|a\s+|an\s+)?"
                  r"([^,.;\n]{3,80})", raw, flags=re.I)
    if m:
        name = re.split(r"\s+(?:and|with|for|on|from|budget|we|i)\s+", m.group(1).strip(), maxsplit=1)[0]
        f["accommodation"] = {"name_or_address": name.strip()}
        res.understood.append(f"Staying at: {name.strip()}")
    acc_types = _match_terms(t, ACCOM_TYPES)
    if acc_types:
        f.setdefault("accommodation", {})["type"] = acc_types[0]

    # pace, diets, food categories, transport
    paces = _match_terms(t, PACES)
    if paces:
        f["pace"] = paces[0]
        res.understood.append(f"Pace: {paces[0]}")
    diets = _match_terms(t, DIETS)
    if "non_vegetarian" in diets and "vegetarian" in diets and not re.search(r"\bvegetarian\b", t.replace("non vegetarian", "").replace("non-vegetarian", "")):
        diets.remove("vegetarian")
    if diets:
        f["food_preferences"] = diets
        res.understood.append("Food: " + ", ".join(diets))
    cats = _match_terms(t, FOOD_CATS)
    if cats:
        f["food_categories"] = cats
        res.understood.append("Food types: " + ", ".join(c.replace("_", " ") for c in cats))
    modes = _match_terms(t, TRANSPORT)
    if re.search(r"\b(no|avoid|hate|without)\s+(cabs?|taxis?|uber)\b", t):
        modes = [x for x in modes if x != "cab"]
    if modes:
        f["transport_modes"] = modes
        res.understood.append("Transport: " + ", ".join(modes))

    # interests: presets/thesaurus anywhere + free phrases after "love/like/into/interested in"
    interests: list[str] = []
    vocab = {p.replace("_", " "): p for p in PRESET_INTERESTS}
    for phrase in sorted(list(vocab) + list(THESAURUS), key=len, reverse=True):
        if _has(t, phrase):
            mapped, _ = normalise_interest(phrase)
            key = vocab.get(phrase)
            if key and key not in interests:
                interests.append(key)
            elif not key and phrase not in interests:
                interests.append(phrase.replace(" ", "_"))
                for x in mapped:
                    if x not in interests:
                        interests.append(x)
    for m in re.finditer(r"\b(?:love|loves|like|likes|into|interested in|enjoy|enjoys|fan of|keen on|want to see)\s+"
                         r"([^.;\n]+)", t):
        for part in re.split(r",|\band\b|\bor\b|/", m.group(1)):
            p = part.strip(" .!")
            p = re.sub(r"^(the|some|lots of|a lot of|good|great|old)\s+", "", p)
            if not p or len(p) > 30 or len(p.split()) > 3 or parse_budget(p) or p in DIETS or p in FOOD_CATS:
                continue
            if any(ch.isdigit() for ch in p) or re.match(
                    r"^(from|on|in|for|with|to|at|by|during|next|this|staying|stay|stays|booked|budget|we|i|our|my|"
                    r"mostly|prefer|pace)\b", p):
                continue  # dates, places, accommodation and other clauses, not interests
            if _match_terms(" " + p + " ", TRANSPORT) or _match_terms(" " + p + " ", PACES):
                continue
            mapped, corrected = normalise_interest(p)
            if corrected:
                if corrected not in interests:
                    interests.append(corrected)
                if corrected != p.replace(" ", "_"):
                    res.notes.append(f"Read '{p}' as '{corrected.replace('_', ' ')}'.")
            else:
                key = p.replace(" ", "_")
                if key not in interests:
                    interests.append(key)
                for x in mapped:
                    if x not in interests:
                        interests.append(x)
    # typo-tolerant pass over single words ("musuems" -> museums)
    for w in set(re.findall(r"[a-z]{5,}", t)):
        if w in vocab or w in THESAURUS:
            continue
        guess = fuzzy_preset(w)
        if guess and guess not in interests and fuzz.ratio(w, guess.replace("_", " ")) < 100:
            interests.append(guess)
            res.notes.append(f"Read '{w}' as '{guess.replace('_', ' ')}'.")
    if interests:
        f["interests"] = interests
        res.understood.append("Interests: " + ", ".join(i.replace("_", " ") for i in interests))

    if "destination_city" not in f:
        res.notes.append("No destination city recognised - type it in the form.")
    if "budget" in f and "currency" not in f:
        res.notes.append("Budget amount found but no currency - check the currency field.")
    return res


def fuzzy_preset(word: str) -> str | None:
    best = process.extractOne(fold(word), [p.replace("_", " ") for p in PRESET_INTERESTS], scorer=fuzz.ratio,
                              score_cutoff=82)
    return best[0].replace(" ", "_") if best else None
