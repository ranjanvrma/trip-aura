# TripAura

**AI-powered, day-by-day travel itineraries for any city in the world, built from free open data.**

Tell TripAura where you're staying, where you're going, your budget, interests, diet, transport and pace (or just describe the trip in a sentence). It plans each day: sights in a sensible order with opening hours respected, breakfast, lunch and dinner that fit your diet, rest breaks, transport for every leg, and a budget that separates real prices from estimates.

![CI](https://github.com/ranjanvrma/trip-aura/actions/workflows/ci.yml/badge.svg)

## Highlights

- **Worldwide, no API key:** places from Overture Maps, Wikidata, OpenStreetMap and Wikivoyage, loaded on demand and cached per city.
- **Smart planning:** a personal 0–5 fit score for every place, route ordering that avoids backtracking, real opening hours, and pace-aware days.
- **Food that fits:** vegetarian, vegan, Jain, eggetarian and non-veg filters, plus local dishes backed by review or guidebook evidence.
- **Honest numbers:** every rating and price says where it came from; estimates are always labelled.
- **NLP + AI:** city autocomplete, a "describe your trip" box that fills the form, typo-tolerant interests, semantic matching with a local embedding model, and review sentiment.
- **On the go:** live location with distance to the next stop and better-transport alerts.

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | React 18, Vite, TypeScript, Leaflet (Google Maps optional) |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| Data | Overture Maps (DuckDB over S3), Wikidata, OpenStreetMap (Overpass), Wikivoyage, GeoNames |
| NLP / DL | rapidfuzz, fastembed (ONNX `bge-small-en-v1.5`) |
| Hosting | Vercel (frontend), Modal (backend), Neon Postgres (database) |

## Quick start

```bash
# backend (from backend/)
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# frontend (from frontend/, in a second terminal)
npm install
npm run dev
```

Open <http://localhost:5173>, type a city (for example "Lisbon"), pick a hotel and generate. The first trip to a new city takes about 30–60 seconds while its data loads; repeat trips take 1–2 seconds. API docs: <http://127.0.0.1:8000/docs>.

Tests: `cd backend && .venv/Scripts/python -m pytest -q` (112 tests, all offline). Frontend: `npm run build`.

## Deployment

Frontend on **Vercel**, backend on **Modal** ($30 free credit a month, no card), database on **Neon** (free). Pushing to `main` runs CI and redeploys the backend automatically. Step-by-step setup: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation

| Doc | What's inside |
|---|---|
| [HANDOFF.md](HANDOFF.md) | Current state, decisions, open tasks: **read this first to catch up** |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Project structure, data pipeline, planning engines, NLP |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Environment variables, free APIs, optional Google key |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Vercel + Modal + Neon guide, alternatives |
| [docs/API.md](docs/API.md) | REST endpoints |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Install, run, tests in detail |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to catch up, work and commit (and keep HANDOFF.md current) |

## Authors

Built and maintained by **Ranjan Verma** and **Chinmay Dahiya**.

Data © OpenStreetMap contributors (ODbL), Overture Maps Foundation, Wikidata (CC0), Wikivoyage (CC BY-SA), GeoNames (CC BY). Every itinerary shows its sources.
