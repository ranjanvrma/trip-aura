# HANDOFF: TripAura

> **Purpose:** everything a developer or AI coding agent needs to continue this project without the original conversation.
> **Rule:** update this file in the **same commit** as any change to code, config, deployment or plans (see [How to update this file](#how-to-update-this-file)).

**Last updated:** 2026-11-12 · **Branch:** `main` · **Latest change:** corrected project status and follow-up tasks after auditing the tracked repository files
**Authors:** Ranjan Verma (GitHub `ranjanvrma`) and Chinmay Dahiya

---

## 0. If you are an AI agent, read this first

1. Read this whole file, then `README.md` (architecture + setup), then run `git log --oneline -15`.
2. CI runs the offline backend suite and frontend production build. The latest known backend result is **130 passing**; the frontend build also passed in CI.
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
  - budget
  - browser-local saved trips (no account or email needed), security headers and request limits
  - **redesigned frontend**: light-mode bento layout, 3D globe, command menu, sheets, toasts with undo, Terms/Privacy/404 pages
  - **130 backend tests pass**, the frontend builds, and CI runs on every push
- **Deployed:** the public Vercel site and Azure backend are live (see [§8](#8-deployment-status)). Trip generation uses the public preview endpoint; the browser stores saved plans locally.

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
| Shared helpers | `core/text.py` (`fold`: accent-insensitive matching), `core/geo.py` (`haversine_km`, `degree_span`), `core/timeutil.py` (`utc_now`), `core/security.py` (`exception_response`), `providers/base.py` (`RouteResult.unavailable`), `engines/costs.py` (`CostModel.fallback`). `engines/` imports nothing from `services/` (type hints only) |
| Pipeline | `services/itinerary_service.py` (geocode → candidates → semantic match → schedule → budget → enrich → optional LLM summary) |
| City data | `providers/open/city_store.py`: parallel loader (ThreadPoolExecutor) for Overture/Wikidata/3×OSM/Wikivoyage, merge (`merge_places`, accent-insensitive name + distance), SQLite/Postgres cache (`CityDataset`, `DATASET_VERSION=6`) |
| Sources | `providers/open/overture.py` (slim columns, shared DuckDB with HTTP/object caches), `open/wikimedia.py` (SPARQL notable places, Wikivoyage dishes), `open/osm.py` (tags, `opening_hours` parser, fees, diet), `open/providers.py` (geocoder uses GeoNames index first, Nominatim fallback), `heuristic_routes.py` |
| Engines | `engines/itinerary.py` (anchor + greedy + 2-opt, opening windows, meals, rests, near-duplicate removal), `recommendation.py` (weights 0.3/0.2/0.2/0.1/0.1/0.1, semantic boost), `food.py` (diet checks, dish lexicon, sentiment-gated evidence), `transport.py`, `budget.py`, `costs.py` (country price index + ECB FX; curated India table), `pace.py`, `fares.py` |
| NLP | `nlp/city_index.py` (GeoNames cities15000, fuzzy), `trip_parser.py`, `interests.py`, `semantic.py` (fastembed bge-small), `sentiment.py`, `registry.py` |
| API | `routers/` trip preview, geo autocomplete, NLP parsing, metadata, and routing. Sign-in, sessions, server-side saved trips, idempotency records and live location were removed (old tables in existing databases are simply unused). Security that remains: Origin check on POST, per-IP rate limits (`generate` 6/min on `/api/trips/preview`), security headers, input limits, safe URLs; CORS without credentials |
| API and security | `routers/` contains itinerary generation (`/api/trips/preview`), geo autocomplete, NLP parsing, status/options and routing; `core/security.py` provides security headers, origin checks and per-IP limits. Account routes are not mounted. |
| Frontend | `App.tsx` (lazy routes, server wake-up retry), `components/layout/` (header, mobile menu sheet, footer, scroll progress, route chunk preloading), `pages/` (Planner, Trip, Trips, Legal, NotFound), `components/` (CommandMenu, globe, form, day cards and map), `lib/localTrips.ts` (saved itineraries in local storage), `lib/trips.ts` (delete + undo), `services/api.ts` (public API calls), `vite.config.ts` (production CSP and pre-rendered route heads) |
| Repo tooling | `.github/workflows/ci.yml` (tests + build), `.github/dependabot.yml` (minor/patch only), `.github/pull_request_template.md`, `.githooks/pre-commit` (HANDOFF check) |
| Production-ready code kept | Postgres support (`db/database.py` normalises `postgres://` URLs), `CORS_ORIGIN_REGEX`, startup warm-up (`WARMUP_ON_START`), DuckDB memory caps; Azure deployment files and workflow are present; live deployment details are in §8 |

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
.venv/Scripts/python -m pytest -q                                      # 130 passed, offline (last recorded CI run)
cd frontend && npm install && npm run dev                               # http://localhost:5173 (proxies /api)
npm run build
```
- Tests force `DATA_MODE=mock`, `SEMANTIC_ENABLED=false` and `WARMUP_ON_START=false` (`backend/tests/conftest.py`), and use fake cities and a fake GeoNames table.
- **First real trip to a new city:** takes 30–60 s. The GeoNames index (~4 MB) and model (~65 MB) download into `backend/data/` on first use.
- **Versions:** Python 3.14 locally; CI uses 3.12 (the planned container too). Node 22 in CI.

---

## 7. Configuration and secrets

Settings: `backend/app/core/config.py` (main ones in README → *Configuration*). Frontend: `VITE_API_BASE_URL` (backend URL in production; empty locally), optional `VITE_GOOGLE_MAPS_API_KEY`.

Secrets are never committed (`.gitignore` blocks `.env*` except `*.env.example`). Live credentials belong only in provider settings; never copy their values into this file. Current deployment configuration:
| Setting / secret | Where |
|---|---|
| Postgres `DATABASE_URL` (Neon, pooled) | Azure Container App secret |
| `CORS_ORIGINS`, `OPEN_USER_AGENT`, `DATA_MODE` | Azure Container App environment |
| `AZURE_CREDENTIALS` (service principal JSON) | GitHub Actions secret; `AZURE_ENABLED=true` is a repository variable |
| `VITE_API_BASE_URL` | Vercel environment variable; set empty to use the same-origin rewrite |
| Google / LLM keys | optional, unused (`ANTHROPIC_MODEL` has no default) |

No email or sign-in provider configuration is needed. `APP_ENV=production`, `CORS_ORIGINS`, `TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_COUNT`, `RATE_LIMIT_ENABLED`, and `DOCS_ENABLED` control the API deployment. `DATABASE_URL` is used for the shared city cache; saved user itineraries are not written to that database.

Lesson from the trial: **never screenshot or paste connection strings or the service-principal JSON.** Both leaked once and had to be rotated.

---

## 8. Deployment status

**Live; last checked 2026-11-10.**
- Website: [https://trip-aura-cr.vercel.app/](https://trip-aura-cr.vercel.app/), hosted on Vercel.
- Backend: [Azure Container Apps](https://trip-aura-api.ambitiousocean-4195e155.koreacentral.azurecontainerapps.io), Korea Central. The image built from `c55f12c` was deployed successfully by GitHub Actions after Azure credentials were corrected. This is the last deployment revision recorded here; verify whether later backend commits, including current `main`, have rolled out.
- `GET /api/health` and `GET /api/meta/status` respond successfully. The website loads and its API requests pass CORS. Security response headers are present.
- The owner confirmed the public site can reach the API after the Azure CORS update. The API health and status endpoints responded successfully.
- Google Maps enrichment is optional and currently off; open-data mode is active.

The backend workflow builds and deploys on pushes to `main` that change `backend/**` or the workflow itself, when `AZURE_ENABLED=true` and `AZURE_CREDENTIALS` are configured. The frontend uses Vercel's same-origin `/api/*` rewrite; `VITE_API_BASE_URL` should remain blank for that setup. Trips remain in each user's browser and do not sync across devices.

**Deployment resources:** Vercel hosts the frontend; Azure Container Apps runs the backend (1 vCPU / 2 GiB, scale-to-zero, max one replica); GitHub Actions builds and deploys the image to GHCR; Neon provides Postgres. Never commit or paste provider secrets.

**Earlier deployment trial (2026-11-08):** its resources were deleted before the current deployment. Its old restoration steps are historical and should not be rerun; current deployment files are already in the repository.

**Other follow-ups:**
- Owners to review the Terms and Privacy pages (`frontend/src/pages/LegalPages.tsx`); they describe real data flows but have not been lawyer-reviewed.
- Place photos and BlurHash placeholders (Wikidata P18 / Wikimedia Commons are possible sources).
- A true per-stage progress indicator for first-time city loading needs async backend loading.
- Lottie is not used; current animation uses Motion, GSAP and CSS.
- Credit Chinmay in GitHub contributors by using his GitHub email or a `Co-authored-by` trailer if desired.
- Nice to have: async city loading, real routing, GTFS transit, a LICENSE file, and testing Google enrichment with a real key.

CI (`ci.yml`) runs tests and the frontend build on every push.

---

## 9. Open tasks / next steps

1. **Verify the current production revision.** Confirm whether the Azure deployment workflow completed for the latest backend changes after `c55f12c`; if not, run the workflow or redeploy through the configured pipeline, then check `/api/health`, `/api/meta/status`, and a browser API request from the Vercel site. Do not recreate Azure, Neon, or Vercel resources; they are already configured.
2. **UI follow-ups** (the redesign itself is done):
   - **Owners to review the Terms and Privacy pages** (`frontend/src/pages/LegalPages.tsx`). They describe the real data flows but aren't lawyer-reviewed. Contact is via GitHub issues; there's no public email or phone yet, so "clickable email/phone" is not implemented.
   - Place photos (and BlurHash placeholders for them): the data has no images yet; Wikidata P18 / Wikimedia Commons is the free source. Only the globe uses a blurred placeholder today.
   - A true per-stage progress indicator for first-time city loading (needs async loading on the backend).
   - Lottie: not used. Animations are Motion (sheets, toasts, menus), GSAP (scroll reveals, parallax, globe turns) and CSS. Add Lottie only with self-made or properly licensed animation files.
3. **Credit Chinmay in GitHub contributors:** he commits with his GitHub email (his email is still unknown).
4. **Dependabot PRs:** merge the green ones (#1–#3 GitHub Actions bumps, #5/#7/#9 backend minimums). Close #4 (React 19), #6 (react-leaflet 5) and #8 (Vite plugin 6): those are major upgrades that need their own change. React Router was moved to 7.18.5 in the redesign (fixes an open-redirect advisory). Majors are now ignored by `dependabot.yml`.
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
- Saved itineraries live in local storage for this browser profile and device. Clearing site data or using another browser removes access to those plans. Previously server-saved trips do not automatically migrate into local storage.
- Animations are throttled in a hidden or background browser tab, so overlays can look stuck in automated screenshots; that's the browser, not the app.
- `prefers-reduced-motion` turns off the globe spin, scroll reveals, parallax and view transitions.

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
| 2026-11-12 | (this commit) | Audit tracked repository files and reconcile README/HANDOFF status, test count, deployment verification, and next steps. |
| 2026-11-10 | `e6de362` | Remove the leftover sign-in code after `7113855`: auth/email/idempotency/live-location routers, services, models, errors and settings, the saved-trip API (only `POST /api/trips/preview` remains), CORS credentials; tests rewritten for the public flow (`test_security.py`), CI green again; unused frontend CSS removed. 130 tests |
| 2026-11-10 | `7113855` | Remove sign-in and save generated itineraries in browser storage; update privacy, deployment, and setup docs |
| 2026-11-10 | `34ddc15` | Add Vercel security headers and long-lived cache for hashed assets; dependency audits clean |
| 2026-11-10 | `fa15814` | Whole-codebase cleanup, no behaviour change: dead code, unused settings paths and duplicated logic removed, shared helpers added (see §4 "Shared helpers"), regexes compiled once, faster city merging and fuzzy search. Bugs fixed: trip parser listed corrected interests in random order; address suggestions returned 500 for Photon features without coordinates; frontend sheet stole focus on re-render, Google/Leaflet maps re-fit or re-centred on every re-render, empty "Tags:" row. 161 tests |
| 2026-11-10 | `27450b2` | Add same-origin Vercel API rewrite; document blank `VITE_API_BASE_URL` and email provider setup |
| 2026-11-10 | `37ae7d8` | Update the Vercel domain to `trip-aura-cr.vercel.app`; document Azure CORS and domain verification steps |
| 2026-11-10 | `d65f949` | README and HANDOFF: document the live deployment, verified health/connectivity, and remaining production sign-in setup |
| 2026-11-10 | `368143f` | Production CSP allows Google Maps hosts; records the live deployment check |
| 2026-11-10 | `c55f12c` | UI redesign (light-mode bento, globe, command menu, sheets, toasts with undo, legal and 404 pages, favicons, per-route heads, CSP); email-code sign-in, per-user trips, account deletion; CSRF, idempotency keys, rate limits, security headers, input limits, injection audit; React Router 7.18.5 |
| 2026-11-10 | `2bf9321` | Restore the tested Azure deployment files and resume the deployment plan |
| 2026-11-10 | `b9ffe2b` | README: link author names to their GitHub profiles |
| 2026-11-10 | `6da2943` | README: fix backend/frontend startup working directories and clarify local-only commits |
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
