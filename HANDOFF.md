# HANDOFF: TripAura

> **Purpose:** everything a developer or AI coding agent needs to continue this project without the original conversation.
> **Rule:** update this file in the **same commit** as any change to code, config, deployment or plans (see [How to update this file](#how-to-update-this-file)).

**Last updated:** 2026-11-10 · **Branch:** `main` · **Latest change:** README startup commands now run from the correct project directories; local commits only
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
   - Never push code; the human owner pushes their local commits. Deploy only when a human asks.
   - Keep the honesty rules: label data sources, keep external ratings separate from the suitability score, mark estimates, and never silently replace failed live data with mock data.
   - Tests stay offline (fakes, `httpx.MockTransport`); add a test for every behaviour change.
   - `backend/app/engines/` stays pure (no network).
   - Never mutate cached place objects in place; reassign fields instead.
   - Bump `DATASET_VERSION` in `providers/open/city_store.py` when the cached city data shape or merge logic changes.

---

## 1. TL;DR

- TripAura plans day-by-day trips for **any city worldwide** from **free open data** (no API key). FastAPI backend, React/Vite/TS frontend.
- **Done and working locally:**
  - planning engines and the open-data pipeline
  - NLP features: city autocomplete, trip-text parser, semantic matching, sentiment
  - budget and live location
  - **112 backend tests pass**, the frontend builds, and CI runs on every push
- **Not deployed yet, but we know exactly how.** On 2026-11-08 a trial run proved the whole free setup works (Vercel + Azure for Students + GHCR + Neon). It was then **deliberately removed** (cloud resources deleted, deployment files taken out of the repo) so the real deployment starts clean. The method is in [§8](#8-deployment-status).
- **Next:** deploy following §8 and **re-run every test and check on deploy day** (the trial results are not a substitute), then a **premium animated UI redesign** ([§9](#9-open-tasks--next-steps)).

---

## 2. Catch up in 5 minutes

```bash
git pull
git log --oneline -15
git config core.hooksPath .githooks     # once per clone
```
1. Read §8 (deployment plan) and §9 (what's next).
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
| Repo tooling | `.github/workflows/ci.yml` (tests + build), `.github/dependabot.yml` (minor/patch only), `.github/pull_request_template.md`, `.githooks/pre-commit` (HANDOFF check) |
| Production-ready code kept | Postgres support (`db/database.py` normalises `postgres://` URLs), `CORS_ORIGIN_REGEX`, startup warm-up (`WARMUP_ON_START`), DuckDB memory caps; deployment files removed (see §8 to restore) |

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
| Planned backend host = **Azure Container Apps (Azure for Students)** | Needs ~750 MB RAM. Free 512 MB tiers (Render/Koyeb) are too small, Hugging Face Docker became paid, and Modal and Oracle need a card (Oracle also rejected an Indian debit card). The team declined Google Cloud. Azure for Students needs no card, its monthly free allowance covers ~50 active h, there's a $100/yr backup credit, and a spending limit means it can never bill |
| Image on GHCR (public), not Azure Container Registry | ACR costs money; GHCR is free for public images |
| Container: 1 vCPU / 2 GiB, min 0 / max 1 replicas, no Log Analytics workspace | Fits the free allowance; logs workspace would cost |
| Neon Postgres | Container disks are ephemeral; Render free Postgres expires in 30 days |
| After graduation (Azure for Students ends) | Switch backend to Render free "lite" (`SEMANTIC_ENABLED=false`, `OVERTURE_ENABLED=false`) or a cheap VPS (Docker Compose + Caddy recipe in commit `8443341`, folder `deploy/oracle/`); frontend/db unchanged |
| Deployment torn down after one verified trial; files removed from the repo | Owner decision on 2026-11-08: redo deployment cleanly later, following the proven plan |
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
- **Versions:** Python 3.14 locally; CI uses 3.12 (the planned container too). Node 22 in CI.

---

## 7. Configuration and secrets

Settings: `backend/app/core/config.py` (main ones in README → *Configuration*). Frontend: `VITE_API_BASE_URL` (backend URL in production; empty locally), optional `VITE_GOOGLE_MAPS_API_KEY`.

Secrets are never committed (`.gitignore` blocks `.env*` except `*.env.example`). **There are no live secrets right now:** all cloud accounts' project resources were deleted. When redeploying, they go to:
| Secret | Where (planned) |
|---|---|
| Postgres `DATABASE_URL` (Neon, pooled) | Azure Container App secret `database-url` |
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`, `OPEN_USER_AGENT`, `DATA_MODE` | Container App env vars |
| `AZURE_CREDENTIALS` (service principal JSON, scoped to the resource group) | GitHub Actions secret, plus variable `AZURE_ENABLED=true` |
| `VITE_API_BASE_URL` | Vercel env var |
| Google / LLM keys | optional, unused (`ANTHROPIC_MODEL` has no default) |

Lesson from the trial: **never screenshot or paste connection strings or the service-principal JSON.** Both leaked once and had to be rotated.

---

## 8. Deployment status

**Current state: not deployed. The method is known and proven; the real deployment is the next step.** CI (`ci.yml`) still runs tests + frontend build on every push.

**How we learned it (trial on 2026-11-08):**
- **Built:** the backend image on GHCR, the Azure Container App (Central India, 1 vCPU / 2 GiB, scale to zero), and a Neon Postgres database.
- **Verified:** `/api/health` ok, semantic model loaded, city search ok, a new Lisbon trip in 35 s saved to Postgres, and a cached repeat in 0.4 s.
- **Torn down:** the Azure resource group `trip-aura` and service principal `trip-aura-github`, the GHCR package `trip-aura-api`, the Neon project, and the Vercel project were all deleted by Ranjan.

**How to deploy (free, no card):**
1. **Restore the tested files from git history:**
   ```bash
   git checkout 8443341 -- backend/Dockerfile backend/.dockerignore backend/scripts deploy/azure .github/workflows/deploy-backend-azure.yml frontend/vercel.json
   ```
   Also available in that commit: `backend/modal_app.py` + `deploy-backend-modal.yml` (Modal, needs a card), `deploy/oracle/` + `deploy-backend-oracle.yml` (any VPS: Docker Compose + Caddy HTTPS), and `render.yaml` (paid).
2. **Neon:** create a project and copy the **pooled** connection string.
3. **Image:** push to `main`. The Azure workflow's image job publishes `ghcr.io/<owner>/trip-aura-api`. It is public automatically for a public repo (check: an anonymous manifest request returns 200).
4. **Azure for Students** (college email, no card; the credit renews yearly while a student): in Cloud Shell (Bash) run `deploy/azure/setup.sh` from raw GitHub.
   - It asks for the Neon URL.
   - It **auto-picks an allowed region**: the trial subscription allowed `centralindia eastasia koreacentral malaysiawest southeastasia`, and East US was rejected.
   - It creates the environment (`--logs-destination none`) and the app (`--min-replicas 0 --max-replicas 1`), then prints the backend URL and the service-principal JSON.
5. **GitHub:** secret `AZURE_CREDENTIALS` (that JSON) + variable `AZURE_ENABLED=true`, so later pushes roll out automatically.
6. **Vercel:** root `frontend`, env `VITE_API_BASE_URL` = backend URL. Then `az containerapp update -n trip-aura-api -g trip-aura --set-env-vars CORS_ORIGINS=https://<site>.vercel.app`.

7. **Re-test everything on deploy day.** Treat it as a fresh deployment and do every check again:
   - locally first: `pytest -q` (all tests pass) and `npm run build`
   - GitHub Actions: CI green, and the image job green
   - backend: `GET /api/health` is ok; `GET /api/meta/status` shows the data mode and semantic model; `GET /api/geo/cities?q=lis` returns cities
   - a new trip for an uncached city (about 30–60 s) is saved to Postgres; repeating it is fast (cache hit)
   - frontend on Vercel: autocomplete, "describe your trip", generate, map, budget and saved trips all work; no CORS errors in the browser console
   - cold start: after the app scales to zero, the first request wakes it and the frontend's retry message clears
   - secrets: nothing secret is committed, and none is pasted into chats or screenshots

**Gotchas from the trial (already fixed in commit `8443341`):**
- The Dockerfile must `mkdir` + `chown` the app folder as root before `USER user`.
- `az containerapp revision restart` fails while the app is scaled to zero. To apply a new secret, create a new revision with `az containerapp update ... --set-env-vars SECRET_ROTATED_AT=$(date +%s)`.
- Delete leftovers with `az group delete -n trip-aura --yes` and `az ad app delete --id <appId>` (the service principal). A hidden `ME_*` resource group may also need deleting.

---

## 9. Open tasks / next steps

1. **Deploy** following §8 (restore files from `8443341`, Neon, image, Azure `setup.sh`, GitHub secret/variable, Vercel, CORS), then run the full deploy-day test list (§8 step 7).
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
- When deployed with scale-to-zero, the first request after idle takes ~30–60 s while the container starts (the frontend already retries for 2 min).
- Windows dev: `.gitattributes` forces LF for shell scripts, YAML and the git hooks.
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
| 2026-11-10 | (this commit) | README: fix backend/frontend startup working directories and clarify local-only commits |
| 2026-11-08 | `8ccf288` | Docs: deployment method is known and proven; added deploy-day full re-test checklist (§8 step 7) |
| 2026-11-08 | `665e0ba` | Deployment trial torn down: all cloud resources deleted; removed Dockerfile, deploy scripts, deploy workflows, `modal_app.py`, `render.yaml`, `vercel.json` (restore from `8443341`); README gains *Project status* + *Deployment plan*; HANDOFF §8 is now the redeploy plan |
| 2026-11-08 | `8443341` | HANDOFF: backend live on Azure Central India, verification results (last commit with all deployment files) |
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
