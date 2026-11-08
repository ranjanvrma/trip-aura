# Architecture

How TripAura is put together: where the code lives, where data comes from, and how a trip is planned.
For settings see [CONFIGURATION.md](CONFIGURATION.md); for hosting see [DEPLOYMENT.md](DEPLOYMENT.md).

## Project structure

```
trip-aura/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, error handlers
│   │   ├── core/                   config (env vars), errors, logging, geo/time helpers
│   │   ├── db/                     SQLAlchemy engine + Trip and CityDataset (open-data cache) models
│   │   ├── schemas/                Pydantic models (trip, place, itinerary, location)
│   │   ├── providers/
│   │   │   ├── base.py             Provider interfaces (Places / Routes / Geocoding)
│   │   │   ├── open/               Worldwide open data: city_store (load + cache), overture, wikimedia
│   │   │   │                       (Wikidata + Wikivoyage), osm (Overpass + tag parsing), http, providers
│   │   │   ├── heuristic_routes.py Distance/speed route estimates using a city's metro/rail stations
│   │   │   ├── google/             Google Maps Platform clients (Places New, Routes, Geocoding, Time Zone)
│   │   │   └── mock/               Demo dataset + mock providers (clearly labelled)
│   │   ├── nlp/                    city_index (GeoNames), trip_parser, interests, semantic (embeddings), sentiment
│   │   ├── services/               places, routes, geocoding, location, fx (exchange rates), enrichment
│   │   │                           (Google ratings), AI, orchestration (itinerary_service)
│   │   ├── engines/
│   │   │   ├── recommendation.py   Personalised suitability score (0-5)
│   │   │   ├── itinerary.py        Day planning, 2-opt ordering, opening hours, meals, rests
│   │   │   ├── food.py             Diet filtering, restaurant picks, evidence-based dishes
│   │   │   ├── transport.py        Mode comparison + practical-mode recommendation
│   │   │   ├── budget.py           Costing, verified vs estimated totals, savings suggestions
│   │   │   ├── costs.py            Worldwide cost model: country price index + FX, curated India table
│   │   │   ├── fares.py            Mode speed profiles and heuristic durations
│   │   │   └── pace.py             Relaxed / moderate / packed profiles
│   │   └── routers/                /api/meta, /api/trips, /api/trips/{id}/live, /api/routes
│   ├── tests/                      pytest suite (112 tests, all offline)
│   ├── scripts/prefetch.py         Pre-downloads city index, AI model and DuckDB extension (used in Docker build)
│   ├── modal_app.py                Modal deployment (serverless backend)
│   ├── Dockerfile                  Backend image (VPS / Render / any Docker host)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/                  PlannerPage (form + saved trips), TripPage (results)
│   │   ├── components/             TripForm, ChipSelect, DayCard, PlaceDetails, RatingBadges,
│   │   │                           RestaurantList, BudgetSummary, LiveLocationPanel, DataSourceBanner
│   │   │   └── map/                MapView (picks renderer), LeafletMap, GoogleMap
│   │   ├── hooks/                  useGeolocation, useLiveProgress
│   │   ├── services/api.ts         Typed API client
│   │   └── types/index.ts          Types mirroring the backend schemas
│   ├── vite.config.ts              Dev proxy /api -> 127.0.0.1:8000
│   └── .env.example
├── frontend/vercel.json            Vercel build + SPA routing
├── deploy/oracle/                  Self-hosted VPS deployment (Oracle Cloud or any Ubuntu server): compose, Caddy, scripts
├── .github/workflows/              ci.yml (tests + build), deploy-backend-modal.yml (main), deploy-backend-oracle.yml (VPS)
├── render.yaml                     Render Blueprint (paid alternative backend host)
├── docs/                           Architecture, configuration, deployment, API, development
├── .githooks/pre-commit            Reminds you to update HANDOFF.md with each commit
├── HANDOFF.md                      Current state + context for the next developer or AI agent
├── AGENTS.md                       Rules for AI coding agents working in this repo
└── CONTRIBUTING.md                 How to catch up, work and commit
```

## Data modes

| `DATA_MODE` | Places / routes from | Use it for |
|---|---|---|
| `open` (default) | Overture Maps, Wikidata, OpenStreetMap, Wikivoyage (no key) + optional Google ratings | Any city worldwide |
| `live` | Google Places API (New), Routes API, Geocoding, Time Zone | When a Google key with billing is available |
| `mock` | Bundled Jaipur demo data | Offline tests and demos |

The engines never depend on the source: every provider implements the interfaces in `backend/app/providers/base.py`.

## Worldwide data (open mode)

Nothing is scraped. Steps 1–4 below run **in parallel** (`providers/open/city_store.py`), and results are merged in a fixed order. Each city loads on demand the first time someone plans a trip there, then it's cached in the database for `CITY_CACHE_DAYS` (default 30). All sources are fetched in parallel, so the first trip to a new city takes about 30–60 seconds (Rome: 37 s); later trips there take 1–2 seconds.

| Step | Source | What it gives | If it fails |
|---|---|---|---|
| City lookup | Offline GeoNames index (Nominatim only as fallback) | Coordinates, country, search radius from population | Error only if neither finds the city |
| Accommodation geocoding | Pinned coordinates from the address dropdown, else Nominatim (1 req/s) | Exact start point | Error with a hint to pick from the dropdown |
| 1. Places (primary) | Overture Maps places, read from public files on S3 via DuckDB (slim columns, one shared DuckDB database with HTTP caches) | Restaurants, cafés, museums, parks, historic sites, plazas, beaches, stations, cuisines, chains | Warning; other layers continue |
| 2. Famous sights | Wikidata query service | Notable places nearby, ranked by how many Wikipedia language editions cover them, plus English names and descriptions | Warning ("famous" detection limited) |
| 3. Details (best effort, 25 s budget, 3 parallel queries) | OpenStreetMap via Overpass (three mirrors) | Opening hours, entry fees, vegetarian/vegan/Jain tags, metro vs train stations | Warning; hours and fees stay unknown |
| 4. Local dishes | Wikivoyage "Eat" section | Dish names with a quoted sentence as evidence | Warning |
| Costs | ECB rates via Frankfurter + a hand-kept country price index | Fares, meal and entry estimates in any of 31 currencies | Error only when converting is needed and rates are down |
| Ratings (optional) | Google Places, when `GOOGLE_MAPS_API_KEY` is set | Google rating and reviews for the ~30–40 places in the plan, only when the name matches within 250 m | Warning; places keep "No rating" |

A city fails only when none of steps 1–3 could be reached.

**How the layers combine:**
- Overture is the base layer.
- Wikidata and OSM records are merged into it by matching name (accent-insensitive) within 150–300 m. Unmatched records are added as new places.
- Near-duplicate sights (the same place under two spellings) are removed before scheduling.

**What open data cannot tell you, and how it's shown:**
- **Ratings:** "No rating" unless Google enrichment found a match.
- **Opening hours:** "Not available". The scheduler assumes 09:00–18:00 and says so.
- **Entry fees:** the OSM `fee`/`charge` tags when present. Otherwise "probably free (assumed)" for squares, parks, monuments and places of worship, and a labelled typical estimate for everything else.
- **Diet:** recorded as confirmed, likely or unverified. For strict diets, dishes with unknown ingredients are hidden.
- **Travel times:** estimated from distance and typical speeds, plus a typical rush-hour slowdown, not live traffic. You can set `ROUTING_ENGINE=osrm` to get real road distances.
- **Metro:** only offered when stations are mapped near both ends of a leg.

**Licences and attribution:** every itinerary carries an `attributions` list, shown as a footer in the UI.
- OpenStreetMap is ODbL 1.0, which is share-alike. A database you redistribute that's built from OSM data must stay under ODbL.
- Overture is CDLA-Permissive-2.0, and its Foursquare records are Apache-2.0.
- Wikidata is CC0. Wikivoyage is CC BY-SA 4.0.
- The public Nominatim and Overpass servers are for light use. For production, self-host them or use a paid provider (`NOMINATIM_URL`, `OVERPASS_URLS`).
- Wikimedia requires a contact URL in the User-Agent (`OPEN_USER_AGENT`).

Tested live on 7–8 Nov 2026 with Lisbon (EUR), Tokyo (JPY), Delhi (INR), Madrid and Rome.

## NLP and deep-learning features

| Feature | How it works | Where |
|---|---|---|
| City autocomplete | Offline index of about 34k cities (GeoNames `cities15000`, CC BY 4.0) with local and alternate names. Prefix search ranked by primary name and population, with fuzzy matching for typos (Tokio → Tokyo, Lisboa → Lisbon, Bombay → Mumbai). Takes 15–100 ms | `nlp/city_index.py`, `GET /api/geo/cities?q=` |
| Address suggestions | Photon (OpenStreetMap search-as-you-type), biased to the chosen city. Picking a result pins exact coordinates, so no separate geocoding step is needed | `GET /api/geo/addresses?q=&lat=&lng=` |
| "Describe your trip" | Rule-based parser (regex, lexicons, typo tolerance, the city index) that fills the form. It handles days or nights, travellers ("with my wife", "family of 4"), budgets in any form ("Rs 25k", "€1.5k", "$80 per day"), dates ("12 Dec", "next friday"), hotel, pace, diet, food types, transport (including "no taxis" and "public transport") and interests. Everything it extracted is listed, plus notes on anything it couldn't work out | `nlp/trip_parser.py`, `POST /api/nlp/parse-trip` |
| Typo-tolerant interests | Typos are corrected (musuems → museums) and a thesaurus expands phrases ("temples" → religious sites, "history buff" → history + monuments + museums). Corrections appear as itinerary warnings | `nlp/interests.py` |
| Semantic interest matching (DL) | Local sentence-embedding model (BAAI/bge-small-en-v1.5, ONNX via fastembed, ~65 MB, CPU). It compares each interest with each candidate place's name, description and categories, so "street art" can match a mural district with no shared keyword. Matches are labelled "AI text matching" in the reasons | `nlp/semantic.py`, `services/itinerary_service.py` |
| Review sentiment (NLP + DL) | Each review sentence is scored with a negation-aware lexicon combined with zero-shot embedding polarity. A dish counts as "popular" only from non-negative mentions, so "the biryani was cold and bland" isn't evidence | `nlp/sentiment.py`, `engines/food.py` |

The embedding model downloads on first use into `backend/data/models`. If it can't load, matching falls back to keywords, and `/api/meta/status` → `nlp.semantic_matching` shows which mode is active. The GeoNames files download on the first city search into `backend/data/geonames`.

## How a trip is planned

**Trip input:** any accommodation type (hotel, Airbnb, hostel, dorm, private property, address) with optional exact coordinates. Also destination, start date, days (1–14), travellers, budget and currency, optional accommodation cost, and multi-select interests, diets, food categories and transport modes. Each list also takes custom entries. You pick the pace and can toggle "fit to budget".

**Itinerary engine** (`engines/itinerary.py`):
- Each day starts and ends at the accommodation (optional), with breakfast, lunch and dinner inside realistic windows.
- Activities are placed in the morning, afternoon or evening, each with a visit duration. Rest breaks go after lunch (at a nearby park when one exists), plus waits for opening times and free time before dinner.
- Opening hours are enforced per weekday, including split hours and closed days. Visits never overrun closing time, and missing hours are flagged instead of assumed silently.
- Sequencing minimises travel:
  - A "day anchor" (the best place, ignoring distance) is chosen first.
  - A greedy pass builds the day around it, penalising travel time and waiting.
  - A 2-opt pass then removes crossing routes.
- Planning uses quick estimates. A second pass rebuilds the day with real route results; any stop that no longer fits is dropped and reported.
- Famous places outside your interests can still be scheduled. They are labelled "Beyond your interests".
- Pace profiles control day length, maximum activities, walking limit, rest time and meal lengths.

**Two separate ratings:**
- `external_rating`: Google rating and review count in live mode (`verified=true`). In mock mode it's a "Demo rating (mock data, not from Google)".
- `suitability`: our own 0–5 score built from interest match (30%), budget compatibility (20%), distance (20%), transport preferences (10%), time availability and opening days (10%), and pace (10%). It comes with a component breakdown and plain-language reasons. External ratings are never an input, and a test checks this.

**Food** (`engines/food.py`):
- Diet is a hard filter (vegetarian, vegan, Jain, eggetarian, non-veg, and combinations). Each match has a confidence level: confirmed, likely (only the search matched), or unverified.
- Restaurants are picked per meal, near your current stop, open at that time, with no repeats.
- A dish is called **popular** only when ≥2 separate reviews mention it, and the evidence quotes are shown. One mention is labelled "mentioned". Dishes inferred from the cuisine are labelled "suggestion". Dishes that don't fit your diet are filtered out.

**Transport** (`engines/transport.py`):
- For every leg it compares your preferred modes, plus walking for short hops.
- Walks longer than the pace allows, unavailable metro or train, and trips over 2.5 h are marked impractical.
- The recommended mode balances time, cost (against what your budget allows per leg) and preference. Alternatives are listed with reasons.
- If none of your preferred modes is practical, it falls back to another mode and says so.

**Budget** (`engines/budget.py`):
- Totals by category, per day and remaining budget.
- Verified amounts (provider fares or amounts you entered) are tracked separately from estimates.
- When the plan is over budget or nearly so, it suggests concrete savings with amounts: cheaper transport per leg, free nearby attractions, cheaper restaurants.
- `fit_to_budget` re-plans in up to 3 stricter steps (cheaper transport and meals, then skipping high entry fees, then one activity fewer per day).

**GPS / live updates:**
- `useGeolocation` uses `watchPosition` only while you have it switched on, and calls `clearWatch` as soon as you switch it off.
- `POST /api/trips/{id}/live` returns:
  - straight-line distance to the next stop
  - refreshed estimates for each mode (traffic-aware in live mode)
  - alerts for a better alternative, a ±20% traffic change, arrival, and low GPS accuracy
- The browser re-checks after you move 50 m and every 2 minutes. Browser notifications are opt-in.
- Coordinates are not stored.

**Persistence:** trips and cached cities are saved in SQLite locally or Postgres (Neon) in production. You can list, view, regenerate and delete them.

**Honesty rules:**
- Every response carries `data_source`, and every rating and price carries its source and a `verified` flag.
- In live mode a missing key returns **503** and a failed Google call returns **502**. Neither ever falls back silently to mock data.
- Mock mode rejects other cities and non-INR currencies with a clear 422.
