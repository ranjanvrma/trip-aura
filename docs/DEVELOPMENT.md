# Development

## Install

Requires Python 3.11+ (developed on 3.14, CI and Docker use 3.12) and Node 18+ (CI uses 22).

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

In the default open mode, enter any city and a hotel name or address (for example "Lisbon" with "Rossio, Lisbon"). The first trip to a city takes about 30–60 seconds while its data loads.

With `DATA_MODE=mock`, use **Jaipur** and an address such as "Hotel on MI Road". Mock localities include MI Road, C-Scheme, Bani Park, Civil Lines, Amer, Old City, Malviya Nagar and Raja Park. You can also give exact coordinates.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest -q
```

Current result: **112 passed**. The suite runs offline (open-data tests use a fake city and `httpx.MockTransport`; NLP tests use a small fake city table and a stand-in embedding model) and covers:
- **NLP:** city search (prefix ranking, alternate names, typos, country hints), the trip-description parser on varied phrasings, budget and date extraction, interest normalisation, sentiment with negation, negative dish mentions excluded, semantic matching raising suitability, and the `/api/nlp` and `/api/geo` endpoints
- **Open data:** OSM opening-hours parser (overnight spans, wrap-around days, overrides), fee and diet tags, Overture rows, Wikidata type filtering, Wikivoyage dish extraction, place merging, cost model, exchange rates, city cache round-trip, Nominatim parsing, and Google enrichment that only attaches a rating on a close name match
- **Scheduling:** opening windows, split hours, closed days, chronological non-overlapping timelines, start and end at the accommodation, three meals, pace limits, no repeated attractions, rest periods
- **Recommendation scoring:** bounds, weights, interest, budget, distance and pace effects, discovery flag, independence from external ratings
- **Budget:** fares per person vs per vehicle, minimums and caps, entry and meal costing, totals adding up, verified vs estimated split, over-budget suggestions, fit-to-budget
- **Food:** diet filters, evidence rules for dishes
- **Google parsing and errors:** via `httpx.MockTransport`
- **API endpoints:** including live progress and the no-silent-fallback rule

The frontend type-checks and builds with `npm run build`.
