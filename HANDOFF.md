# HANDOFF: TripAura

> **Purpose:** everything a developer or AI coding agent needs to continue this project without the original conversation.
> **Rule:** update this file in the **same commit** as any change to code, config, deployment or plans (see [How to update this file](#how-to-update-this-file)).

**Last updated:** 2026-11-08 · **Branch:** `main` · **Latest change:** backend is LIVE on Azure (Central India); Vercel + GitHub deploy secrets still to do
**Authors:** Ranjan Verma (GitHub `ranjanvrma`) and Chinmay Dahiya

---

## 0. If you are an AI agent, read this first

1. Read this whole file, then `README.md` (architecture + setup), then run `git log --oneline -15`.
2. Run the tests before and after changes: `cd backend && .venv/Scripts/python -m pytest -q` (must stay **112+ passing, offline**) and `cd frontend && npm run build`.
3. **Rules:**
   - Update **HANDOFF.md in every commit** (header, affected sections, change-log row). The hook `.githooks/pre-commit` enforces it once `git config core.hooksPath .githooks` is set.
   - **No AI attribution anywhere:** no `Co-Authored-By` lines for AI tools, no assistant or tool names in code, docs or commit messages.
   - **Never commit secrets** (see §7 for where they live).
   - **Documentation lives only in `README.md` and `HANDOFF.md`.** The owners asked for no extra doc files: keep the README short, and put depth here.
   - Push or deploy only when a human asks.
   - Keep the honesty rules: label data sources, keep external ratings separate from the suitability score, mark estimates, and never silently replace failed live data with mock data.
   - Tests stay offline (fakes, `httpx.MockTransport`); add a test for every behaviour change.
   - `backend/app/engines/` stays pure (no network).
   - Never mutate cached place objects in place; reassign fields instead.
   - Bump `DATASET_VERSION` in `providers/open/city_store.py` when the cached city data shape or merge logic changes.

---

## 1. TL;DR

- TripAura plans day-by-day trips for **any city worldwide** from **free open data** (no API key). FastAPI backend, React/Vite/TS frontend.
- **Working locally:**
  - planning engines and the open-data pipeline
  - NLP features: city autocomplete, trip-text parser, semantic matching, sentiment
  - budget and live location
  - **112 backend tests pass**, and the frontend builds
- **Backend is LIVE** at `https://trip-aura-api.wittysand-9be93277.centralindia.azurecontainerapps.io` (Azure Container Apps, Central India). Frontend (Vercel) not yet deployed.
- Deployment plan: Chosen stack: **Vercel** (frontend) + **Azure Container Apps via Azure for Students** (backend, no card) + **GitHub Container Registry** (image) + **Neon** (Postgres).
  - Neon project exists (created by Ranjan in AWS US East 1).
  - Still to do: Azure, Vercel, and the GitHub secrets ([§8](#8-deployment-status)).
- **Next:** finish deployment, then a **premium animated UI redesign** ([§9](#9-open-tasks--next-steps)).

---

## 2. Catch up in 5 minutes

```bash
git pull
git log --oneline -15
git config core.hooksPath .githooks     # once per clone
```
1. Read §8 (what's live) and §9 (what's next).
2. Run the app and tests (§6). If a fresh clone fails, fix that first.

---

## 3. What the product does

**Input:**
- accommodation: any address, or one pinned from the autocomplete
- destination city and start date
- days (1–14) and travellers
- total budget and currency (31 supported), plus optional accommodation cost
- interests (presets plus custom text), diets, food categories, transport modes
- pace: relaxed, moderate or packed
- toggles: "end each day at hotel" and "fit to budget"
- or free text ("4 days in Lisbon with my wife, vegetarian, budget 900 euros...") that fills the form

**Output** (`Itinerary` schema in `backend/app/schemas/itinerary.py`):
- **Per day:** a timeline of start → breakfast → activities → lunch → rest → activities → dinner → back to hotel. Each entry has times, place, a travel leg (chosen mode, alternatives, reasons) and costs (verified vs estimated).
- **Food:** recommendations with evidence-based dishes.
- **Budget:** per day and per category, with savings suggestions.
- **Also:** unscheduled-but-good places, warnings, disclaimers and data attributions.
- **Live mode:** next-stop distance, refreshed estimates and alerts.

**Original brief rules that still govern decisions:**
- modular providers; demo mode clearly labelled
- **never fabricate Google ratings**
- two separate ratings: external vs our suitability
- a dish is "popular" only with evidence
- verified prices vs estimates
- an LLM is optional, and the engines never depend on it

---

## 4. Architecture

Diagram and request flow: README → *Architecture*. Key files:

| Area | Files |
|---|---|
| Settings | `backend/app/core/config.py` (every env var and default) |
| Pipeline | `services/itinerary_service.py` (geocode → candidates → semantic match → schedule → budget → enrich → optional LLM summary) |
| City data | `providers/open/city_store.py`: parallel loader (ThreadPoolExecutor) for Overture/Wikidata/3×OSM/Wikivoyage, merge (`merge_places`, accent-insensitive name + distance), SQLite/Postgres cache (`CityDataset`, `DATASET_VERSION=6`) |
| Sources | `providers/open/overture.py` (slim columns, shared DuckDB with HTTP/object caches), `open/wikimedia.py` (SPARQL notable places, Wikivoyage dishes), `open/osm.py` (tags, `opening_hours` parser, fees, diet), `open/providers.py` (geocoder uses GeoNames index first, Nominatim fallback), `heuristic_routes.py` |
| Engines | `engines/itinerary.py` (anchor + greedy + 2-opt, opening windows, meals, rests, near-duplicate removal), `recommendation.py` (weights 0.3/0.2/0.2/0.1/0.1/0.1, semantic boost), `food.py` (diet checks, dish lexicon, sentiment-gated evidence), `transport.py`, `budget.py`, `costs.py` (country price index + ECB FX; curated India table), `pace.py`, `fares.py` |
| NLP | `nlp/city_index.py` (GeoNames cities15000, fuzzy), `trip_parser.py`, `interests.py`, `semantic.py` (fastembed bge-small), `sentiment.py`, `registry.py` |
| API | `routers/` trips, location (live), geo (autocomplete), nlp (parse-trip), meta (status/options), routes |
| Frontend | `pages/PlannerPage.tsx` (DescribeTrip + TripForm + saved trips), `pages/TripPage.tsx`, `components/*` (Autocomplete, DayCard, PlaceDetails, map/*, BudgetSummary, LiveLocationPanel...), `services/api.ts`, `types/index.ts` (mirror of backend schemas), `App.tsx` (retries status while backend wakes). Plain CSS in `index.css`, intentionally basic until the redesign |
| Deploy | `backend/Dockerfile` (py3.12, uid 1000, `scripts/prefetch.py` bakes city index + model + DuckDB httpfs), `.github/workflows/deploy-backend-azure.yml`, `deploy/azure/setup.sh`; alternatives: `backend/modal_app.py`, `deploy/oracle/`, `render.yaml` |

---

## 5. Key decisions and why

| Decision | Why |
|---|---|
| No scraping; open data + optional Google API | Google ToS; open sources are legal and free |
| `DATA_MODE=open` default (`live` = Google, `mock` = Jaipur tests) | Worldwide without keys |
| Overture primary, OSM best effort | Public Overpass is often overloaded (502/429/timeouts) |
| Parallel city loading, OSM capped at 25 s | Fresh Rome 245 s → 37 s; keeps requests well under host time limits |
| Slim Overture columns + shared DuckDB caches | First S3 read 83 s → 49 s |
| Shallow copies of cached places, no in-place mutation | Deep copy cost 0.7 s/trip; protects the cache (tested) |
| City names from the offline GeoNames index | Skips a rate-limited Nominatim call |
| `OPEN_USER_AGENT` must contain a contact URL | Wikimedia returns 403 otherwise |
| Suitability never uses external ratings | Brief requirement (tested) |
| Dish "popular" = ≥2 non-negative review mentions; "guide" = Wikivoyage | Evidence-based; sentiment ignores complaints |
| Free entry assumed only for squares/parks/monuments/worship, labelled; ticketed types never | No fake "free" claims |
| Backend host = **Azure Container Apps (Azure for Students)** | Needs ~750 MB RAM. Free 512 MB tiers (Render/Koyeb) are too small, Hugging Face Docker became paid, and Modal and Oracle need a card (Oracle also rejected an Indian debit card). The team declined Google Cloud. Azure for Students needs no card, its monthly free allowance covers ~50 active h, there's a $100/yr backup credit, and a spending limit means it can never bill |
| Image on GHCR (public), not Azure Container Registry | ACR costs money; GHCR is free for public images |
| Container: 1 vCPU / 2 GiB, min 0 / max 1 replicas, no Log Analytics workspace | Fits the free allowance; logs workspace would cost |
| Neon Postgres | Container disks are ephemeral; Render free Postgres expires in 30 days |
| After graduation (Azure for Students ends) | Switch backend to Render free "lite" (`SEMANTIC_ENABLED=false`, `OVERTURE_ENABLED=false`) or a cheap VPS (`deploy/oracle/`); frontend/db unchanged |
| Docs only in README.md + HANDOFF.md | Owner instruction |
| No AI-tool attribution in repo or commits | Owner instruction |

---

## 6. Run, test, build

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000     # http://127.0.0.1:8000/docs
.venv/Scripts/python -m pytest -q                                      # 112 passed, offline
cd frontend && npm install && npm run dev                               # http://localhost:5173 (proxies /api)
npm run build
```
- Tests force `DATA_MODE=mock`, `SEMANTIC_ENABLED=false` and `WARMUP_ON_START=false` (`backend/tests/conftest.py`), and use fake cities and a fake GeoNames table.
- **First real trip to a new city:** takes 30–60 s. The GeoNames index (~4 MB) and model (~65 MB) download into `backend/data/` on first use.
- **Versions:** Python 3.14 locally; CI, Docker and the cloud use 3.12. Node 22 in CI.

---

## 7. Configuration and secrets

Settings: `backend/app/core/config.py` (main ones in README → *Configuration*). Frontend: `VITE_API_BASE_URL`, optional `VITE_GOOGLE_MAPS_API_KEY`.

Secrets are never committed (`.gitignore` blocks `.env*` except `*.env.example`):
| Secret | Where |
|---|---|
| Neon `DATABASE_URL` | Azure Container App secret `database-url` (created by `deploy/azure/setup.sh`) |
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`, `OPEN_USER_AGENT`, `DATA_MODE` | Container App env vars (`az containerapp update --set-env-vars ...`) |
| `AZURE_CREDENTIALS` (service principal JSON, scoped to resource group `trip-aura`) | GitHub Actions secret |
| `AZURE_ENABLED=true` | GitHub Actions variable |
| `VITE_API_BASE_URL` | Vercel env var |
| Google / LLM keys | not used yet (optional; `ANTHROPIC_MODEL` has no default) |

---

## 8. Deployment status

| Piece | Status | Notes |
|---|---|---|
| GitHub repo `ranjanvrma/trip-aura` | ✅ | CI (`ci.yml`): tests + frontend build on push/PR |
| Neon Postgres | ✅ created (AWS US East 1) | connection string held privately by Ranjan |
| Backend image on GHCR | ✅ | `ghcr.io/ranjanvrma/trip-aura-api:latest`, public (inherited from the repo); built by `deploy-backend-azure.yml` |
| Azure for Students | ✅ activated (Ranjan, college account); credit valid until 2027-01-29, renew while a student | |
| Azure Container App `trip-aura-api` (rg `trip-aura`, env `trip-aura-env`) | ✅ **live** in **centralindia** (allowed regions: centralindia, eastasia, koreacentral, malaysiawest, southeastasia; resource group itself is in eastus) | URL `https://trip-aura-api.wittysand-9be93277.centralindia.azurecontainerapps.io`. Verified 2026-11-08: `/api/health` ok, semantic model loaded, city search ok, new Lisbon trip 35 s (saved to Neon), cached repeat 0.4 s |
| GitHub auto-deploy (`AZURE_CREDENTIALS` secret, `AZURE_ENABLED` var) | ⏳ | the first service-principal secret was exposed in a screenshot; reset it (rerun `az ad sp create-for-rbac --name trip-aura-github ... --json-auth`) and store only the new JSON in GitHub |
| Vercel frontend | ⏳ not created | root `frontend`, env `VITE_API_BASE_URL`; then set `CORS_ORIGINS` on the container app |
| Alternatives | 💤 | Modal (`modal_app.py`, needs card), VPS (`deploy/oracle/`), Render (`render.yaml`, paid) |

Unverified until first deploy: the GHCR build, the Azure app creation (region policy on student subscriptions; fallback `LOCATION=centralindia`), cold-start time on Azure, Postgres in production, and CORS with the real Vercel URL.

---

## 9. Open tasks / next steps

1. **Finish deployment:** reset + store `AZURE_CREDENTIALS`, set `AZURE_ENABLED=true`, rotate the Neon password (it was exposed in a screenshot) and update the container secret `database-url`, create the Vercel project, then set `CORS_ORIGINS` on the container app.
2. **UI redesign** (requested by the owners):
   - premium, product-grade look with animations, transitions, micro-interactions and a responsive layout
   - keep the `types/index.ts` contract and the honesty labels: rating source badges, "estimate" tags, attributions footer
   - add a progress indicator for first-time city loading
3. **Credit Chinmay in GitHub contributors:** he commits with his GitHub email, or commits carry `Co-authored-by: Chinmay Dahiya <github-email>` (his email is still unknown).
4. **Dependabot PRs:** merge the green ones (#1–#3 GitHub Actions bumps, #5/#7/#9 backend minimums). Close #4 (React 19), #6 (react-leaflet 5) and #8 (Vite plugin 6): those are major upgrades that break the frontend, so do them during the UI redesign. Majors are now ignored by `dependabot.yml`.
5. **Nice to have:**
   - async city loading with progress polling
   - real routing (`ROUTING_ENGINE=osrm` exists; it uses public demo servers)
   - GTFS transit
   - a LICENSE file (owners to choose)
   - testing Google enrichment with a real key

---

## 10. Known limitations and gotchas

- Public Overpass servers often fail, so hours, fees and diet tags can be missing (warnings are shown).
- Overture has no ratings, hours or fees; Google enrichment runs only with a key.
- Travel times are heuristic in open mode (no live traffic).
- Bumping `DATASET_VERSION` rebuilds every cached city.
- `opening_hours` parser: the common subset only; seasonal and sunrise rules become "unknown".
- Azure for Students subscriptions only allow a few regions; `setup.sh` picks one from `az policy assignment list` (override with `LOCATION=...`).
- Azure scales to zero, so the first request after idle takes ~30–60 s while the image starts (the frontend retries for 2 min).
- Windows dev: `.gitattributes` forces LF for scripts, Dockerfile, Caddyfile, YAML and hooks.
- Mock mode supports Jaipur and INR only (by design).

---

## 11. Conventions

- Commits: imperative subject (≤ 72 chars), a body saying what and why, HANDOFF.md updated, no AI attribution, author email = your GitHub email.
- Python: type hints; Pydantic schemas in `app/schemas`; network code only in `providers/` and `services/`; tests for behaviour changes.
- Frontend: typed calls in `services/api.ts`; keep `types/index.ts` in sync with the backend.
- Honesty: `DataSource` labels; `verified` vs estimate on money; warnings, not silent fallbacks.

---

## 12. Change log (newest first)

| Date | Commit | Change |
|---|---|---|
| 2026-11-08 | (this commit) | HANDOFF: backend live on Azure Central India, verification results, remaining deploy steps |
| 2026-11-08 | `c88cc71` | `deploy/azure/setup.sh`: detect regions allowed by the subscription policy and pick one; reuse an existing resource group |
| 2026-11-08 | `a528f6d` | Dockerfile: create `data/runtime` and chown the app folder as root before `USER user` (the first GHCR build failed); Dependabot ignores semver-major and groups Actions bumps |
| 2026-11-08 | `4017c8b` | Backend host → Azure Container Apps (Azure for Students): GHCR build + Azure deploy workflow, `deploy/azure/setup.sh`. Docs consolidated into README (with architecture diagram) + HANDOFF; removed `docs/`, `AGENTS.md`, `CONTRIBUTING.md` |
| 2026-11-08 | `c4c6eb4` | HANDOFF.md, short README + docs, pre-commit handoff hook, PR template, Dependabot, `.editorconfig`, AI-tool naming removed, tidier `.gitignore` |
| 2026-11-08 | `16ca811` | Modal deployment; parallel city loading (245 s → 37 s); OSM 25 s cap; slim Overture + shared DuckDB; offline city resolution; shallow copies; startup warm-up; 112 tests |
| 2026-11-08 | `c767eec` | Oracle Cloud VPS deployment (compose + Caddy HTTPS, scripts, SSH deploy); Hugging Face removed |
| 2026-11-08 | `71edc7d` | Dockerfile, CI, Postgres support, CORS regex, Vercel config, authors |
| 2026-11-07 | `4c69c52` | Stop tracking `tsconfig.tsbuildinfo` |
| 2026-11-07 | `8501d6d` | City autocomplete, address suggestions, trip-text parser, typo-tolerant + semantic interests, review sentiment |
| 2026-11-07 | `353b86d` | Worldwide open-data mode, cost model + FX, Google enrichment |
| 2026-11-07 | `e492999` | Initial app: engines, mock Jaipur data, Google-ready providers, React frontend |

---

## How to update this file

With **every commit** that changes behaviour, config, deployment or plans:
1. Update the header (`Last updated`, `Latest change`).
2. Edit the affected sections (§8 status, §9 tasks, §5 decisions, §10 gotchas).
3. Add a row at the top of §12; use "(this commit)", and replace older "(this commit)" entries with their hash.
4. Delete what's no longer true instead of appending contradictions.
