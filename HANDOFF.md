# HANDOFF: TripAura

> **Purpose:** everything a developer or AI coding agent needs to continue this project without the original conversation.
> **Rule:** update this file in the **same commit** as any change to code, config, deployment or project decisions (see [How to update this file](#how-to-update-this-file)).

**Last updated:** 2026-11-08 · **Branch:** `main` · **Latest change:** repo docs restructure + this handoff (follows `16ca811`)
**Authors:** Ranjan Verma (GitHub `ranjanvrma`) and Chinmay Dahiya

---

## 1. TL;DR (read this if nothing else)

- TripAura plans day-by-day trips for **any city worldwide** from **free open data** (no API key needed). FastAPI backend, React/Vite/TS frontend.
- **Done and working locally:** planning engines, open-data pipeline, NLP features (city autocomplete, trip-description parser, semantic matching, sentiment), budget, live location. **112 backend tests pass**; the frontend builds.
- **Deployment is configured but NOT live yet.** Chosen stack: **Vercel** (frontend) + **Modal** (backend) + **Neon** (Postgres). Neon project exists (created by Ranjan, region AWS US East 1). Modal account, Modal secret, GitHub secrets and the Vercel project are **still to be done** ([§8](#8-deployment-status)).
- **Next planned work:** finish deployment, then a **premium animated UI redesign** of the frontend ([§9](#9-open-tasks--next-steps)).
- **Hard rules:** never add AI/assistant names or `Co-Authored-By` lines for AI tools to commits, code or docs; never commit secrets; never silently replace failed live data with mock data; keep ratings and the suitability score separate.

---

## 2. Catch up in 5 minutes

```bash
git pull
git log --oneline -15            # what changed recently (messages are descriptive)
```
1. Read this file top to bottom, especially [§8](#8-deployment-status) and [§9](#9-open-tasks--next-steps).
2. Skim [README.md](README.md), then [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the code you'll touch.
3. Run the app and tests ([§6](#6-run-test-build)). If tests fail on a fresh clone, fix that first.
4. Enable the commit reminder once per clone: `git config core.hooksPath .githooks`.

---

## 3. What the product does

Input: accommodation (any address, or pinned from autocomplete), destination city, start date, days (1–14), travellers, total budget + currency (31 supported), optional accommodation cost, interests (presets + custom text), diets, food categories, transport modes, pace (relaxed/moderate/packed), "end each day at hotel", "fit to budget". Or a free-text description ("4 days in Lisbon with my wife, vegetarian, budget 900 euros...") that fills the form.

Output (`Itinerary` schema): per day a timeline of start → breakfast → activities → lunch → rest → activities → dinner → back to hotel, each with times, place, travel leg (chosen mode + alternatives + reasons), costs (verified vs estimated); food recommendations with evidence-based dishes; budget summary (per day/category, savings suggestions); unscheduled-but-good places; warnings, disclaimers, data attributions. Live mode: distance to next stop, refreshed estimates, alerts.

Original brief highlights that still govern decisions: modular providers; mock/demo mode clearly labelled; **never fabricate Google ratings**; two separate ratings (external rating vs our suitability score); only call a dish "popular" with evidence; distinguish verified prices from estimates; LLM optional and never required by the engines.

---

## 4. Architecture in one screen

```
frontend (Vercel)  --HTTPS-->  backend FastAPI (Modal)  -->  Neon Postgres (trips + city cache)
                                   |
        open data, fetched in PARALLEL per new city, cached 30 days:
        Overture Maps (DuckDB over S3) · Wikidata SPARQL · OSM Overpass (3 queries, 25 s cap) · Wikivoyage
        + GeoNames city index (offline) · Photon (address autocomplete) · Nominatim (fallback geocoding)
        + Frankfurter ECB rates (currency) · optional Google Places (ratings enrichment)
```

Backend layout (`backend/app/`):
| Folder | Responsibility | Key files |
|---|---|---|
| `core/` | settings (env vars), errors, logging, geo/time utils, currencies | `config.py` (every setting + default) |
| `providers/` | data sources behind interfaces in `base.py` | `open/city_store.py` (parallel city loader + cache + merge), `open/overture.py`, `open/wikimedia.py`, `open/osm.py` (tag + opening_hours parser), `open/providers.py` (geocoder/places), `heuristic_routes.py`, `google/*`, `mock/*` |
| `engines/` | pure planning logic (no network) | `itinerary.py` (anchor + greedy + 2-opt, opening hours, meals, rests), `recommendation.py` (0–5 score, weights), `food.py` (diet filter, dishes, sentiment-gated evidence), `transport.py`, `budget.py`, `costs.py` (country price index + FX), `pace.py`, `fares.py` |
| `nlp/` | text intelligence | `city_index.py` (GeoNames, fuzzy), `trip_parser.py`, `interests.py` (typos + thesaurus), `semantic.py` (fastembed), `sentiment.py`, `registry.py` (singletons) |
| `services/` | orchestration | `itinerary_service.py` (the main pipeline), `places_service.py`, `fx_service.py`, `enrichment.py` (Google), `ai_service.py` (optional LLM summary), `location_service.py`, `providers.py` (factory by `DATA_MODE`) |
| `routers/` | HTTP API | `trips.py`, `location.py`, `geo.py`, `nlp.py`, `meta.py`, `routes.py`, `deps.py` |
| `db/` | SQLAlchemy | `models.py`: `Trip`, `CityDataset` (`DATASET_VERSION` in `city_store.py` invalidates caches) |

Frontend (`frontend/src/`): `pages/PlannerPage.tsx` (DescribeTrip + TripForm + saved trips), `pages/TripPage.tsx` (day cards, map, details, live panel, budget, food); `components/` (Autocomplete, TripForm, DayCard, PlaceDetails, RatingBadges, RestaurantList, BudgetSummary, LiveLocationPanel, DataSourceBanner, map/{MapView, LeafletMap, GoogleMap}); `services/api.ts`; `types/index.ts` mirrors backend schemas; `App.tsx` retries `/api/meta/status` while the backend wakes up. Styling is plain CSS in `index.css` (intentionally basic; redesign pending).

Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/CONFIGURATION.md](docs/CONFIGURATION.md), [docs/API.md](docs/API.md).

---

## 5. Key decisions and why (do not undo without a reason)

| Decision | Why |
|---|---|
| **No scraping**; open data + optional Google API | Google ToS forbid scraping; open sources are legal and free |
| `DATA_MODE=open` is the default | Works worldwide without keys; `live` needs Google billing; `mock` is Jaipur-only for tests |
| Overture is the primary place layer, OSM is best-effort | Public Overpass servers are frequently overloaded (502/429/timeouts); Overture (S3) is reliable |
| All city sources load **in parallel**, OSM capped at **25 s** | Fresh Rome trip went 245 s → 37 s; Modal web requests are cut at 150 s |
| Slim Overture columns + one shared DuckDB with HTTP/object caches | First S3 read ~40% faster (83 s → 49 s measured) |
| Shallow copies of cached places, **never mutate shared lists/dicts** | Deep copy cost 0.7 s per trip; mutation would corrupt the city cache (test guards this) |
| City names resolve from the offline GeoNames index | Saves a Nominatim call (1 req/s policy) per trip |
| Wikimedia needs a contact URL in `OPEN_USER_AGENT` | Returns HTTP 403 otherwise |
| Suitability score never uses external ratings | Brief requirement; enforced by a test |
| "Popular" dish = ≥2 non-negative review mentions; "guide" = Wikivoyage; else "suggestion" | Brief requires evidence; sentiment filter avoids counting complaints |
| Assumed-free entry only for squares/parks/monuments/worship, labelled as assumption; ticketed types (museum, castle, monastery, tower...) never assumed free | Avoids fake "free" claims |
| Backend host = **Modal** | Needs ~750 MB RAM peak; Render/Koyeb free = 512 MB; Hugging Face Docker became paid; Oracle Always Free rejected Ranjan's Indian debit card; Google Cloud declined by the team |
| Database = **Neon** (not Render Postgres) | Render free Postgres expires after 30 days; Modal has no persistent disk |
| No AI-assistant attribution anywhere in the repo or commits | Explicit owner instruction |

---

## 6. Run, test, build

```bash
# backend (Windows paths; use .venv/bin/... on macOS/Linux)
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000     # http://127.0.0.1:8000/docs
.venv/Scripts/python -m pytest -q                                      # 112 passed, fully offline
# frontend
cd frontend && npm install && npm run dev                               # http://localhost:5173 (proxies /api)
npm run build                                                           # type-check + production build
```
- Tests force `DATA_MODE=mock`, `SEMANTIC_ENABLED=false`, `WARMUP_ON_START=false` (see `backend/tests/conftest.py`), use fake cities, a fake GeoNames table and `httpx.MockTransport`. Never let a test hit the network.
- First real trip to a new city downloads data (30–60 s); the GeoNames index (~4 MB) and embedding model (~65 MB) download into `backend/data/` on first use (`scripts/prefetch.py` does it ahead of time).
- Python: developed on 3.14 locally; CI, Docker and Modal use **3.12**. Node: 22 in CI.

---

## 7. Configuration and secrets

All settings: `backend/app/core/config.py` and [docs/CONFIGURATION.md](docs/CONFIGURATION.md). Frontend: `VITE_API_BASE_URL` (backend URL in production, empty locally), optional `VITE_GOOGLE_MAPS_API_KEY`.

Secrets are **never** committed (`.gitignore` blocks `.env*` except `*.env.example`). Where they live:
| Secret | Where |
|---|---|
| Neon `DATABASE_URL` | Modal secret `trip-aura-env` (to be created) |
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`, `OPEN_USER_AGENT` | Modal secret `trip-aura-env` |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | GitHub Actions secrets (to be created) |
| `MODAL_ENABLED=true` | GitHub Actions variable (to be created) |
| `VITE_API_BASE_URL` | Vercel project env var (to be created) |
| Google / LLM keys | not used yet (optional features) |

---

## 8. Deployment status

| Piece | Status | Notes |
|---|---|---|
| GitHub repo `ranjanvrma/trip-aura` | ✅ pushed by Ranjan up to `16ca811` (newer local commits may need pushing) | |
| CI (`.github/workflows/ci.yml`) | ✅ configured | tests (py 3.12) + frontend build on push/PR |
| Neon Postgres | ✅ project created (AWS US East 1) | connection string kept privately by Ranjan |
| Modal backend (`backend/modal_app.py`, `deploy-backend-modal.yml`) | ⏳ code ready, **never deployed** | needs Modal account, secret `trip-aura-env`, GitHub secrets/variable; first build 5–8 min; URL `https://<workspace>--trip-aura-api.modal.run` |
| Vercel frontend (`frontend/vercel.json`) | ⏳ not created | root dir `frontend`, env `VITE_API_BASE_URL` |
| Oracle VPS path (`deploy/oracle/`, `deploy-backend-oracle.yml`) | 💤 kept as alternative | sign-up failed (card); skipped unless `ORACLE_HOST` variable is set |
| Render (`render.yaml`) | 💤 paid alternative | Standard plan only (512 MB too small) |

Step-by-step: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Unverified until first deploy: the Modal image build (prefetch step), Postgres in production, CORS with the real Vercel URL.

---

## 9. Open tasks / next steps

1. **Finish deployment** (Modal + Vercel, see §8), then verify end to end (health, city autocomplete, a fresh-city trip under 150 s).
2. **UI redesign (next big task, requested by the owners):** premium, product-grade UI with animations, transitions, micro-interactions, responsive layout. Keep the data contract (`frontend/src/types/index.ts`) and honesty labels (rating source badges, "estimate" tags, attributions footer). Consider a progress indicator for first-time city loading.
3. **Credit Chinmay in GitHub contributors:** he should commit with his GitHub email, or commits can carry `Co-authored-by: Chinmay Dahiya <his-github-email>` (email still unknown).
4. Nice to have: async city loading with progress polling (removes any 150 s risk), a real routing engine (`ROUTING_ENGINE=osrm` exists but uses public demo servers), GTFS transit, LICENSE file (owners to choose), Google key integration testing (code exists, untested against live Google).

---

## 10. Known limitations and gotchas

- Public Overpass servers often fail → hours/fees/diet tags missing for some places (warnings are shown). Not a bug.
- Overture has no ratings, hours or fees; Google enrichment only runs with a key.
- Travel times are heuristic estimates (no live traffic) in open mode.
- Bumping `DATASET_VERSION` (`providers/open/city_store.py`) forces every cached city to rebuild; do it when the dataset shape or merge logic changes.
- The OSM `opening_hours` parser supports the common subset; seasons/sunrise rules become "unknown".
- Modal HTTP requests are cut at 150 s; city loading is ~30–60 s now, keep it that way.
- Windows dev: `.gitattributes` forces LF for `*.sh`, `Dockerfile`, `Caddyfile`, YAML.
- Mock mode supports only Jaipur and INR (by design).

---

## 11. Conventions

- **Commits:** imperative subject ≤ 72 chars, body explaining what and why; **update HANDOFF.md in the same commit**; no AI attribution lines. Each author commits with their own GitHub email.
- **Python:** type hints, Pydantic schemas in `app/schemas`, network code only in `providers/`/`services/`, engines stay pure and testable; add a test for every behaviour change.
- **Frontend:** typed API calls in `services/api.ts`; keep `types/index.ts` in sync with backend schemas.
- **Honesty:** label sources (`DataSource`), `verified` vs estimate on money, warnings instead of silent fallbacks.

---

## 12. Change log (newest first)

| Date | Commit | Change |
|---|---|---|
| 2026-11-08 | (this commit) | Short README + `docs/`; HANDOFF.md, AGENTS.md, CONTRIBUTING.md; pre-commit handoff reminder; PR template; Dependabot; removed AI-tool naming from the repo (local assistant settings folder untracked, no default LLM model id); tidier `.gitignore` |
| 2026-11-08 | `16ca811` | Modal deployment; parallel city loading (245 s → 37 s); OSM 25 s cap; slim Overture + shared DuckDB; offline city resolution; shallow copies; startup warm-up; 112 tests |
| 2026-11-08 | `c767eec` | Oracle Cloud VPS deployment (compose + Caddy HTTPS, setup/update scripts, SSH deploy); HF removed |
| 2026-11-08 | `71edc7d` | Dockerfile, CI, Postgres support, CORS regex, Vercel config, authors |
| 2026-11-07 | `4c69c52` | Stop tracking `tsconfig.tsbuildinfo` |
| 2026-11-07 | `8501d6d` | City autocomplete, address suggestions, trip-description parser, typo-tolerant + semantic interests, review sentiment |
| 2026-11-07 | `353b86d` | Worldwide open-data mode (Overture, Wikidata, OSM, Wikivoyage), cost model + FX, Google enrichment |
| 2026-11-07 | `e492999` | Initial app: engines, mock Jaipur data, Google-ready providers, React frontend |

---

## How to update this file

With **every commit** that changes behaviour, config, deployment or plans:
1. Update the header (`Last updated`, `Latest change`).
2. Edit the sections your change affects (status tables in §8, tasks in §9, decisions in §5, gotchas in §10).
3. Add a row at the top of the change log (§12); use "(this commit)" and fix it to the hash in the next commit if you like.
4. Keep it factual and current: delete what's no longer true instead of appending contradictions.

The pre-commit hook (`git config core.hooksPath .githooks`) blocks commits that change files without staging `HANDOFF.md`; bypass only for trivial commits with `SKIP_HANDOFF=1 git commit ...`.
