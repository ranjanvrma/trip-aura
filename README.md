# TripAura: AI-Powered Travel Itinerary Generator

You enter where you're staying, the destination, days, budget, interests, food preferences, transport and pace. TripAura returns a day-wise itinerary with timed activities, meals, rest breaks, transport legs, two separate ratings per place, food and dish recommendations, a budget breakdown and live-location updates.

- **Backend:** Python, FastAPI, SQLAlchemy (SQLite), Pydantic
- **Frontend:** React, Vite, TypeScript (Leaflet/OSM map now; Google Maps JS renderer turns on with a key)
- **Data sources:** `mock` (bundled Jaipur demo data, no keys) or `live` (Google Places API (New), Routes API, Geocoding API, Time Zone API)
- **AI (optional):** Anthropic API writes a short overview from data the engines have already computed. The engines don't depend on it.

---

## Project structure

```
trip-aura/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, error handlers
│   │   ├── core/                   config (env vars), errors, logging, geo/time helpers
│   │   ├── db/                     SQLAlchemy engine + Trip model
│   │   ├── schemas/                Pydantic models (trip, place, itinerary, location)
│   │   ├── providers/
│   │   │   ├── base.py             Provider interfaces (Places / Routes / Geocoding)
│   │   │   ├── google/             Google Maps Platform clients (Places New, Routes, Geocoding, Time Zone)
│   │   │   └── mock/               Demo dataset + mock providers (clearly labelled)
│   │   ├── services/               places, routes, geocoding, location, AI, orchestration (itinerary_service)
│   │   ├── engines/
│   │   │   ├── recommendation.py   Personalised suitability score (0-5)
│   │   │   ├── itinerary.py        Day planning, 2-opt ordering, opening hours, meals, rests
│   │   │   ├── food.py             Diet filtering, restaurant picks, evidence-based dishes
│   │   │   ├── transport.py        Mode comparison + practical-mode recommendation
│   │   │   ├── budget.py           Costing, verified vs estimated totals, savings suggestions
│   │   │   ├── fares.py            Speed profiles and fare tables (estimates)
│   │   │   └── pace.py             Relaxed / moderate / packed profiles
│   │   └── routers/                /api/meta, /api/trips, /api/trips/{id}/live, /api/routes
│   ├── tests/                      pytest suite (64 tests)
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
└── .claude/launch.json             Dev-server definitions (backend, frontend)
```

## Implemented features

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

**Persistence:** trips are saved in SQLite. You can list, view, regenerate and delete them.

**Honesty rules:**
- Every response carries `data_source`, and every rating and price carries its source and a `verified` flag.
- In live mode a missing key returns **503** and a failed Google call returns **502**. Neither ever falls back silently to mock data.
- Mock mode rejects other cities and non-INR currencies with a clear 422.

## Waiting on your Google Maps credentials

The code for these is written and unit-tested against mocked HTTP responses, but it hasn't been run against Google's real APIs yet:

- `providers/google/places.py`: Places API (New) Text Search and Place Details, with field masks, rating, reviews, hours, price range and vegetarian flag
- `providers/google/routes.py`: Routes API `computeRoutes` (`TRAFFIC_AWARE` driving, transit with vehicle-type filters for metro, bus and train, transit fares, polylines)
- `providers/google/geocoding.py`: Geocoding API for the city and accommodation, plus the Time Zone API so departure times are local
- `components/map/GoogleMap.tsx`: Maps JavaScript API renderer (markers, polylines, traffic layer, accuracy circle)

To switch to live data, set `DATA_MODE=live` and `GOOGLE_MAPS_API_KEY` in `backend/.env`, and optionally `VITE_GOOGLE_MAPS_API_KEY` in `frontend/.env`.

Things to check when you connect:
- The field masks match your SKU tier.
- Caching and storage of Places content meets Google's terms. Saved trips currently store place snapshots.
- Cab and auto fares stay estimates, because Google doesn't publish them.

## Environment variables

`backend/.env` (copy from `backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATA_MODE` | `mock` | `mock` or `live` |
| `GOOGLE_MAPS_API_KEY` | empty | Server key: Places API (New), Routes API, Geocoding API, Time Zone API |
| `GOOGLE_HTTP_TIMEOUT_SECONDS` | `10` | Timeout for Google requests |
| `AI_ENABLED` | `false` | Turns on the optional AI overview |
| `ANTHROPIC_API_KEY` | empty | Needed when `AI_ENABLED=true` |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Model for the overview (uses server-side refusal fallback) |
| `DATABASE_URL` | `sqlite:///backend/tripaura.db` | SQLAlchemy URL |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed frontend origins |
| `LOG_LEVEL` | `INFO` | Logging level |

`frontend/.env` (optional, copy from `frontend/.env.example`):

| Variable | Purpose |
|---|---|
| `VITE_GOOGLE_MAPS_API_KEY` | Browser key (restricted by HTTP referrer) for the Maps JavaScript API. Leave it empty to use Leaflet/OSM |
| `VITE_API_BASE_URL` | Backend URL. Leave it empty to use the Vite proxy |

## Installation

Requires Python 3.11+ (tested on 3.14) and Node 18+ (tested on 24).

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
```

(On macOS/Linux use `.venv/bin/python`.)

```bash
cd frontend
npm install
```

## Run

Backend (from `backend/`):

```bash
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Frontend (from `frontend/`):

```bash
npm run dev
```

- App: http://localhost:5173
- API: http://127.0.0.1:8000
- Interactive API docs: http://127.0.0.1:8000/docs

In mock mode, use **Jaipur** as the destination and an address such as "Hotel on MI Road". Mock localities include MI Road, C-Scheme, Bani Park, Civil Lines, Amer, Old City, Malviya Nagar and Raja Park. You can also give exact coordinates.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest -q
```

Current result: **64 passed**. The suite covers:
- **Scheduling:** opening windows, split hours, closed days, chronological non-overlapping timelines, start and end at the accommodation, three meals, pace limits, no repeated attractions, rest periods
- **Recommendation scoring:** bounds, weights, interest, budget, distance and pace effects, discovery flag, independence from external ratings
- **Budget:** fares per person vs per vehicle, minimums and caps, entry and meal costing, totals adding up, verified vs estimated split, over-budget suggestions, fit-to-budget
- **Food:** diet filters, evidence rules for dishes
- **Google parsing and errors:** via `httpx.MockTransport`
- **API endpoints:** including live progress and the no-silent-fallback rule

The frontend type-checks and builds with `npm run build`.

## API summary

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/meta/status` | Data mode, Google and AI configuration |
| GET | `/api/meta/options` | Preset interests, diets, categories, modes |
| POST | `/api/trips` | Generate and save an itinerary |
| POST | `/api/trips/preview` | Generate without saving |
| GET | `/api/trips` / `/api/trips/{id}` | List / get saved trips |
| POST | `/api/trips/{id}/regenerate` | Re-run with the saved request |
| DELETE | `/api/trips/{id}` | Delete a trip |
| POST | `/api/trips/{id}/live` | Live position, then next stop, fresh estimates and alerts |
| POST | `/api/routes/compare` | Compare modes between two points |
