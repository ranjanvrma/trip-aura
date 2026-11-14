# HANDOFF: TripAura

> **Purpose:** everything a developer or AI coding agent needs to continue this project without the original conversation.
> **Rule:** update this file in the **same commit** as any change to code, config, deployment or plans (see [How to update this file](#how-to-update-this-file)).

**Last updated:** 2026-11-14 · **Branch:** `main` · **Latest change:** **v2.4.1**: the home page's \"how it works\" section is cut down to the four steps beside one route demo
**Authors:** Ranjan Verma (GitHub `ranjanvrma`) and Chinmay Dahiya

---

## 0. If you are an AI agent, read this first

1. Read this whole file, then `CLAUDE.md` (the working guide: folder map, commands, coding and design rules, pitfalls, done checklist), then `README.md` (architecture + setup), then run `git log --oneline -15`. This file says what is true now; `CLAUDE.md` says how to work. If they disagree, this file wins.
2. CI runs the offline backend suite and frontend production build. The latest known backend result is **131 passing**; the frontend build also passed in CI.
3. **Rules:**
   - Update **HANDOFF.md in every commit** (header, affected sections, change-log row). The hook `.githooks/pre-commit` enforces it once `git config core.hooksPath .githooks` is set.
   - **No AI attribution anywhere:** no `Co-Authored-By` lines for AI tools, no assistant or tool names in code, docs or commit messages. The one exception is the file name `CLAUDE.md`, which coding tools look for by that name; its contents name no tool.
   - **Never commit secrets** (see §7 for where they live).
   - **Documentation lives only in `README.md`, `HANDOFF.md` and `CLAUDE.md`.** The owners asked for no other doc files: keep the README short, put status and depth here, and keep `CLAUDE.md` for how to work (update it only when the rules or the structure change).
   - Never push code; the human owner pushes their local commits. Deploy only when a human asks.
   - **Every release gets a version** (§13): bump `frontend/package.json` and `backend/app/main.py`, add the row to §13, create an annotated `vX.Y.Z` tag on the release commit, and push with `--follow-tags`. Docs-only commits get no version.
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
  - **131 backend tests pass**, the frontend builds, and CI runs on every push
- **Deployed:** the public Vercel site and Azure backend are live (see [§8](#8-deployment-status)). Trip generation uses the public preview endpoint; the browser stores saved plans locally.

---

## 2. Catch up in 5 minutes

```bash
git pull
git log --oneline -15
git config core.hooksPath .githooks     # once per clone
```
1. Read §8 (deployment status) and §9 (what's next).
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
- **Visuals and summary:** a map, place details and an optional AI-written overview based only on the generated itinerary facts.

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
| Engines | `engines/itinerary.py` (anchor + greedy + 2-opt, opening windows, meals, rests, near-duplicate removal), `recommendation.py` (weights 0.3/0.2/0.2/0.1/0.1/0.1, semantic boost), `food.py` (diet checks, dish lexicon, sentiment-gated evidence), `transport.py`, `budget.py`, `costs.py` (country price index + FX: ECB first, ExchangeRate-API for other currencies; curated India table), `pace.py`, `fares.py`, `style.py` (trip style: lowest cost, mid-range, premium) |
| NLP | `nlp/city_index.py` (GeoNames cities15000, fuzzy), `trip_parser.py`, `interests.py`, `semantic.py` (fastembed bge-small), `sentiment.py`, `registry.py` |
| API | `routers/` trip preview, geo autocomplete, NLP parsing, metadata, and routing. Sign-in, sessions, server-side saved trips, idempotency records and live location were removed (old tables in existing databases are simply unused). Security that remains: Origin check on POST, per-IP rate limits (`generate` 6/min on `/api/trips/preview`), security headers, input limits, safe URLs; CORS without credentials |
| API and security | `routers/` contains itinerary generation (`/api/trips/preview`), geo autocomplete, NLP parsing, status/options and routing; `core/security.py` provides security headers, origin checks and per-IP limits. Account routes are not mounted. |
| Frontend | `App.tsx` (lazy routes, server wake-up retry), `pages/` (Planner, Trip, Trips, Legal, NotFound), `components/` grouped by feature: `planner/` (form, describe box, progress panel), `trip/` (ticket header, day cards and ribbon, place details, budget charts, food), `globe/` (three.js Earth, lazy chunk), `map/`, `layout/` (shell, command menu, banners), `ui/` (sheet, skeleton, key, autocomplete, retry notice), `art/` (seeded contour artwork); `lib/localTrips.ts` (saved itineraries in local storage), `lib/trips.ts` (delete + undo), `services/api.ts` (public API calls), `vite.config.ts` (production CSP, pre-rendered route heads, version injection) |
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
| Docs only in README.md + HANDOFF.md + CLAUDE.md | Owner instruction. `CLAUDE.md` was added on 2026-11-13 at the owner's request so any coding tool or new contributor works the same way |
| No AI-tool attribution in repo or commits | Owner instruction |

---

## 6. Run, test, build

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000     # http://127.0.0.1:8000/docs
.venv/Scripts/python -m pytest -q                                      # 131 passed, offline (last recorded CI run)
cd frontend && npm install && npm run dev                               # http://localhost:5173 (proxies /api)
npm run build
```
- Tests force `DATA_MODE=mock`, `SEMANTIC_ENABLED=false` and `WARMUP_ON_START=false` (`backend/tests/conftest.py`), and use fake cities and a fake GeoNames table.
- **First real trip to a new city:** usually 10 to 20 s (measured 15 to 19 s locally; it was about 50 s before v2.3.0). The GeoNames index (~4 MB) and model (~65 MB) download into `backend/data/` on first use.
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
- The planner now shows an indeterminate generation panel with elapsed time and explanatory steps. A true per-stage progress indicator still needs async backend loading and status polling.
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
   - The current generation panel explains the work and shows elapsed time, but cannot report actual backend stages. True per-stage progress needs async loading and status polling.
   - Lottie: not used. Animations are Motion (sheets, toasts, menus), GSAP (scroll reveals, parallax, globe turns) and CSS. Add Lottie only with self-made or properly licensed animation files.
3. **Owner's feature backlog:** the planned releases are listed at the end of §13, in order. Next up is another way into a plan besides the planner (guided chat or picking on the map).
4. **Credit Chinmay in GitHub contributors:** he commits with his GitHub email (his email is still unknown).
5. **Dependabot:** review the currently open dependency PRs in GitHub. Minor and patch upgrades are grouped; major upgrades are ignored and should be considered separately with any required code changes.
6. **Nice to have:**
   - async city loading with progress polling
   - real routing (`ROUTING_ENGINE=osrm` exists; it uses public demo servers)
   - GTFS transit
   - a LICENSE file (owners to choose)
   - testing Google enrichment with a real key

---

## 10. Known limitations and gotchas

- Public Overpass servers often fail, so hours, fees and diet tags can be missing (warnings are shown).
- **Still open from the review** (minor, performance only): each place query in open mode re-filters the whole city list; in live or OSRM mode the transport options for a leg are fetched one after another; dish matching scans reviews twice. None changes a plan.
- **For Chinmay, `TRUSTED_PROXY_COUNT`:** with 1 behind Vercel plus Azure, every visitor shares one rate-limit bucket (the address seen is Vercel's); with 2, a caller who goes straight to the Azure URL can choose its own bucket with a forged `X-Forwarded-For`. Please check which value production uses; the clean fix is to stop the Azure app from accepting direct traffic.
- Overture has no ratings, hours or fees; Google enrichment runs only with a key.
- Travel times are heuristic in open mode (no live traffic).
- Exchange rates: ECB covers about 30 currencies; the other 120 come from ExchangeRate-API's open endpoint, which is rate limited and asks for attribution (rates are cached 12 hours per process, and the itinerary credits it). A few currencies (Venezuela, and Zimbabwe where USD is used) have parallel or unofficial rates, so treat those estimates loosely.
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
| 2026-11-14 | (this commit) | **v2.4.1.** At the owner's request the home page's "See how a plan comes together" section (three demo cards above a row of four steps) is reduced to "How a plan is made": the four steps as a short numbered list beside the one demo that shows something real, the route reordering on seven Lisbon places (52.2 km listed, 27.7 km reordered). The budget-by-style and pace demos and their CSS are removed; the trip page shows both for every real plan. Checked in headless Edge at 1440 and 390 px: no console errors, no overflow |
| 2026-11-14 | `ee71ac2` | **v2.4.0.** At the owner's request: **light only.** The dark theme, the toggle (bar, phone menu, command menu), `lib/theme.ts`, `public/theme-init.js`, the night Google map style and the dark day colours are removed; the light tokens are now the only `:root` block. A visitor who had chosen dark gets light (the old `tripaura.theme` key is simply ignored). Overlay and pin shadows were softened for paper. **Globe:** the NASA satellite globe is replaced by the original clear style (v1.0 colours: pale sea, sage land, dot pattern, soft lit side) with every country outlined: `landMask.ts` now loads Natural Earth `countries-50m` (110m on slow links), fills land from its `land` object and draws the `countries` mesh (borders and coastlines) as lines just above the surface. `world-atlas` and `topojson-client` are back; `globe/textures/` is gone. Footer and README credit Natural Earth instead of NASA. **Footer:** the large TripAura wordmark was nearly invisible on paper; it is now teal, fading downwards. Privacy page no longer mentions a saved theme. Checked in headless Edge at 1440 and 390 px: home, globe turned to Paris, trip page, footer; no console errors, no overflow |
| 2026-11-14 | `96e7d8b` | **v2.3.1.** The rest of the review. **Scheduler** (`engines/itinerary.py`): with lunch still to come, a sight must end by 14:30, and from 12:00 a sight that would run past 13:30 waits until after lunch (lunch may move to 11:30 to make room; a sight that cannot fit is listed as unscheduled with the reason); a stay more than 40 minutes from the last sight gets the ride home before dinner and dinner nearby, and the planner leaves room for that ride, so days no longer run past midnight; a park rest now has its walk or ride and must be open on arrival. **Data:** a city built while a source was down is rebuilt once in the background after 30 minutes; OSRM routing falls back to the distance estimate for a failed leg (10 s timeout) and pauses for 5 minutes after three failures; Google enrichment runs 6 lookups at a time, stops at the first quota or permission error, and remembers places with no Google match for a day (Google's terms do not allow caching ratings). **Budget step:** "prefer cheaper restaurants" now also uses price-level estimates, so it works with open data. **Speed:** restaurants are ranked with the score's arithmetic and the full score is built only for the winner; attraction scores are computed once per request. Measured on cached Lisbon, 7 days: 2.3 s to 1.0 s; with budget fitting 6.3 s to 1.2 s. **Frontend:** finishing a plan after you have left the planner shows "Open" in a notice instead of pulling you to it. 10 new tests (174), including one that checks the faster restaurant ranking always picks what the full scoring would |
| 2026-11-14 | `5a53009` | **v2.3.0.** Speed and a full review. **New-city time:** measured where the 50 s went: the essential sources took about 7 s and the rest was waiting on a failing Overpass, past its own 25 s budget. Now `city_store.build` waits for Overture, Wikidata and Wikivoyage, gives OSM a 4 s grace (`OSM_GRACE_SECONDS`), builds the plan, and `_upgrade_when_ready` merges a late OSM answer and re-saves the city; start-up also warms the Overture file index (`overture.warm_up`: first city read 11 s to 5.5 s). Measured new-city plans: 15 to 19 s. **Review:** two independent reviewers read every backend and frontend file; fixed from their reports: `/api/routes/compare` could start unlimited city loads (now under the generation limit); a malformed OSM `charge` tag could break every trip to a city, and fees were misread (`1,500 JPY` as 1.5, `$` always USD); an unavailable transport mode could win as a 0-minute free leg; meals could be placed after closing time once travel was counted; lunch right after breakfast on empty days; a park used as a rest and again as a sight; rest-park fees missing from totals; the meal price cap compared two currencies; a city built while a source was down was kept 30 days (now 1 day); three caches grew without limit; a far-future start date and an unknown currency on route comparison returned 500; loose name matching could attach another business's Google rating; the embedding cache could fail the request that cleared it; the trip-text parser invented budgets ("bars 3", "4 wonderful") and read "100 euros a day" as one day; a cache-database error failed a built trip. Frontend: the planner reset to step 1 when the tab regained focus; Next did nothing when a hidden step was invalid; Ctrl+P printed a blank page; trip-page state leaked between trips; the Google map refitted on tab focus; a stuck autocomplete spinner and lists opening under the wrong field; "today" was UTC; a full browser storage lost the new plan (the oldest trips now make room); regenerate could bring back a deleted trip; a stay pin kept from the previous city; the dropdown and command menu were silent or leaky for keyboard and screen-reader users; the departure board could crash in demo mode; plus an error boundary so a page crash shows a message. `DATASET_VERSION` is 7 (cities rebuild once). 24 new tests (164). What was found and not fixed is listed in §10 |
| 2026-11-14 | `1e085c0` | **v2.2.0.** Real-Earth globe. The stylised teal globe is replaced by satellite imagery: NASA Blue Marble for the day side, Black Marble city lights for the night side, a water mask for the sun's glint on the sea, and a cloud composite (a typical sky, not live weather). The shader (`globe/shaders.ts`) lights it from the real subsolar point as before, with a twilight band and a blue atmosphere at the limb; it is the same in dark and light themes. Imagery lives in `globe/textures/` (four JPEGs, about 0.9 MB, resized from the files shipped in the MIT-licensed three-globe package; NASA imagery is public domain) and loads with the lazy globe chunk; if it fails the globe draws as a plain blue ball. Removed: the Natural Earth land mask, land dots and graticule, and the `world-atlas` and `topojson-client` packages (the globe's JS is about 170 kB gzipped smaller). Footer and README credit NASA. Checked in headless Edge in both themes and at 390 px, with a destination on the day side (Tokyo) and one on the night side (New York) |
| 2026-11-14 | `f91abae` | **v2.1.0.** Light theme. A sun or moon button in the top bar, a row in the phone menu and a command ("Switch to light theme") flip the whole site between the dark default and a light, warm-paper theme. `lib/theme.ts` sets `data-theme` on `<html>`, updates the browser's theme colour, saves the choice under `tripaura.theme` in local storage and notifies listeners (`useTheme`); `public/theme-init.js` applies the saved choice before first paint (a file, not an inline script, because of the CSP). The light palette is a second token block in `index.css`; the page grain, glows, shadows, map tile filter and text on day colours became tokens. Day colours have a deeper set for light, the Google base map drops its night style, and the globe and the departure board stay dark in both themes. Privacy page mentions the saved theme. Checked in headless Edge in both themes at 1440 and 390 px: toggle, reload keeps the choice, home, planner, trip, command menu, legal; no console or CSP errors, no overflow |
| 2026-11-14 | `4b2d0df` | **v2.0.0.** Complete redesign, frontend only. **Look:** dark "night flight" theme replaces the light atlas (new tokens in `index.css`; ember for the main action, aurora teal for links and selected states; Inter for words, JetBrains Mono for data; Fraunces removed); globe recoloured for night with the destination in ember; Leaflet tiles and the Google base map are night-styled; logo, favicon and theme colour updated. **Home:** hero with a split-flap departure board in the headline (click a city to plan it), a quick-start bar (city + days), the globe, and the data sources; three working demos (`home/Showcase`: 2-opt route ordering on real Lisbon places, the Jaipur demo's budget by trip style, an illustrated day by pace); the describe box as its own band; saved trips as passes. **Planner:** `TripForm` is now five questions, one at a time (where, when, budget, tastes, getting around), each validated before the next, with `planner/BoardingPass` filling in beside it; `ui/Select` (searchable listbox) replaces the browser select for currency, `ui/Stepper` for days and travellers, `.pick` cards for style and pace. **Trip and other pages:** ticket, timeline, budget, saved trips (`trip/TripPass`), legal and 404 restyled; the PDF keeps its paper colours through print-only token overrides. **Build:** `assetsInlineLimit: 0`, because an inlined font subset was blocked by the CSP. Links to `/#plan` scroll to the planner. Checked in headless Edge at 1440 and 390 px: planner end to end (a real Lisbon plan), place details, command menu, regenerate, delete and undo, PDF layout, production preview with no CSP or console errors, no horizontal overflow. Backlog items done: designed dropdowns, step-by-step form, more interactive site |
| 2026-11-14 | `d2ad81e` | **v1.3.1.** Auto-rickshaws only where they exist: a Lisbon plan used them because the form's default modes included `auto`. `engines/transport.py` now has `AUTO_COUNTRIES` (South and Southeast Asia, parts of Africa and Latin America, where autos, tuk-tuks, keke or moto-taxis are everyday rides) and `local_modes`: elsewhere the planner swaps `auto` for `cab`, drops autos from the fallback rides, and adds a warning; the saved request keeps what the traveller asked for. Unknown country: left as asked. The form's default modes are walking, metro and bus (the Jaipur demo keeps autos). Checked live: Lisbon with autos asked for plans walking, metro and cabs. Two new tests |
| 2026-11-14 | `ef55403` | **v1.3.0.** Download as PDF: a "Download PDF" button on the trip ticket (and a command-menu entry) mounts `components/trip/TripPrint.tsx` into `<body>` and opens the browser's print dialog, where "Save as PDF" writes the file; the page title becomes the suggested file name ("TripAura - 2 days in Lisbon"). Print styles at the end of `index.css` hide the app and lay the document out on A4: cover (title, dates, stay, travellers, pace, style, four totals, budget table with published vs estimated amounts, budget notes), one section per day (time, stop, ride with minutes and km, cost marked "est." when estimated, place notes), then food to try, data notes and sources. Chosen over a PDF library because the free ones cannot draw Turkish, Japanese or the rupee sign without bundling large fonts; the browser uses the site's own fonts and every script. Nothing is sent anywhere. Checked by printing a real Lisbon plan with headless Edge (4 pages) |
| 2026-11-14 | `3d89aad` | **v1.2.0.** Trip style: new `trip_style` request field (`budget`, `mid` default, `premium`), a "How to spend the budget" control in the form, listed in `/api/meta/options`, and read from descriptions ("cheap", "on a budget", "luxury", "5 star"...; "budget" alone still means an amount). `engines/style.py` holds the profiles. Lowest cost judges meals and entry fees against half the usual allowance and weights transport toward cost; premium marks down the cheapest restaurants and weights transport toward time. Only the budget component of the score and the transport choice change; score weights and honesty rules are untouched, and the budget is still the ceiling. Non-default styles add a note to the budget. On the Jaipur demo data a 2-day plan comes to 2,832 / 3,235 / 3,410 INR. Stays are not priced by the app, so the style does not pick hotels. Also: number fields (days, travellers, budget, stay cost) use a new `ui/NumberInput` that can be emptied while typing, so clearing one no longer leaves a 0 that turns 2 into "02"; the local currency option reads "JPY (local)" so it fits the field. Three new tests |
| 2026-11-14 | `75561d1` | **v1.1.2.** Smarter hotel search (`routers/geo.py`). Photon's location bias was too weak: "inn" for a Jaipur trip returned the Inn river in Austria and villages in Myanmar. Once a destination is chosen, the form now sends its name (`city`), and the backend runs two Photon searches in parallel: one limited to a 40 km box around the city, one with the city name added. Results are merged, duplicates dropped, and ranked: names containing every typed word anywhere (not only at the start) first, then places to stay, then places within 40 km; matches over 150 km away are dropped when local ones exist. If one search fails the other is still used. Checked live: "inn" now lists 99 Inn, Broadway Inn, Golden Inn... in Jaipur and Crown Inn, Grace Inn in Karachi. One new test |
| 2026-11-14 | `96db37f` | **v1.1.1.** Fix: the planner only accepted the 31 ECB currencies, so Karachi (PKR) and most of Asia, Africa and Latin America got no suggestion and could not be planned in their own money. `core/currencies.py` now maps every country to the currency travellers mostly pay in (150 currencies) and is the single source: the accepted list, the form options and the new `currency` field on city suggestions (the frontend table from v1.1.0 is gone). `FxService` loads ECB rates (Frankfurter) and ExchangeRate-API's open endpoint (`FX_OPEN_URL`, no key) and prefers ECB; if one source is down the other is used, if both are down the request fails as before. Conversion notes say which rate was used, and trips whose currency needs the second source credit it in their attributions. Terms and Privacy name both rate sources. Two new tests; checked with a real Karachi trip in PKR |
| 2026-11-14 | `1d32b40` | **v1.1.0.** Currency suggestion: picking a city (from the list, a quick-start city or a typed description) offers that country's currency as a one-click button under the Currency field, and marks it in the list as "used in <country>". Nothing changes until the traveller clicks, and any other currency can still be chosen. The country-to-currency table is `frontend/src/lib/localCurrency.ts` and covers only currencies the planner accepts, so countries with an unsupported currency get no suggestion. Frontend only |
| 2026-11-13 | `7538486` | **v1.0.2.** Footer lists Ranjan Verma and Chinmay Dahiya with GitHub and LinkedIn links (README Authors too). `vite.config.ts` restarts the dev server when `package.json` changes, so a version bump reaches the footer without a manual restart (the version was frozen at server start, so v1.0.1 still showed 1.0.0 locally) |
| 2026-11-13 | `55e787c` | **v1.0.1.** Interface pass: removed template tells (uppercase tile labels, dash eyebrows, icon fact list, Keyboard and How-it's-built tiles, shortcut badges inside fields, pinned data banner); sentence-case serif headings; plainer copy; quick-start cities in the hero (looked up in the city index, fill the form and turn the globe); data note moved under the submit button; home layout is now hero, planning column, side column; quiet entrance motion (ticket, day ribbons, budget ring and bars), smooth scrolling, all off under reduced motion. Components grouped by feature (`planner/`, `trip/`, `ui/`, `layout/`), `Kbd` in its own file, dead CSS removed. README rewritten without the "AI-powered" tagline, with app and release links |
| 2026-11-13 | `ea37847` | **v1.0.0.** Complete redesign: travel-atlas palette (paper, deep teal, terracotta), full-width hero with a real 3D globe (Natural Earth land, live day/night from the sun's position, drag to turn, destination pin and saved-trip pins, lazy chunk; detailed coastline, lighter one on slow connections), ticket-style trip header with real totals, day ribbons, budget ring and per-day bars, seeded contour artwork on trip cards, dark teal footer with the version, new logo colours and icons. Version system added (§13), past milestones tagged |
| 2026-11-13 | `712cc2b` | Reconcile HANDOFF with the latest GitHub changes: remove stale live-location output, describe the indeterminate generation panel accurately, and replace outdated Dependabot PR numbers with a current review task. |
| 2026-11-13 | `c705060` | Add `CLAUDE.md`, the working guide (what the project is, folder map, commands, coding, design, honesty and security rules, known pitfalls, done checklist); README and HANDOFF §0 point to it; docs rule now allows this third file |
| 2026-11-13 | `6c3d0f0` | Interface polish, ten fixes: Generate button no longer floats over the form; open-data banner is one quiet line (demo-mode and error banners unchanged); trip warnings and disclaimers fold into one plain sentence with details (`data-notes`); removed the dead live-location tile; dates read "Sat, 12 Dec" (`fmtDay`); stops show a duration instead of a repeated time range and period tag, and each diet fact appears once (`extraNotes` in `DayCard`); unrated places show no badge in lists (`hideEmpty`, place details still say "No rating"); parser plurals ("4 days", "2 travellers", tested); custom chips use an "Add your own" chip instead of three input rows; a `GeneratingPanel` replaces the form while a plan is built (elapsed time, no fake percentage). All routes and external links re-checked. 131 tests |
| 2026-11-12 | `635eb3d` | Audit tracked repository files and reconcile README/HANDOFF status, test count, deployment verification, and next steps. |
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

## 13. Versions and releases

TripAura uses semantic versioning, `vMAJOR.MINOR.PATCH`:
- **MAJOR**: a change in what the product is or how people use it (a new trip model such as multi-destination trips, a redesign that changes the flows, anything that breaks saved trips or the API).
- **MINOR**: a new feature that fits the current flows (a currency suggestion, a trip-style option, a new chart).
- **PATCH**: fixes and polish with no new feature.
- Docs-only or tooling-only commits get no version.

**Where the version lives:** `frontend/package.json` (`version`, shown in the site footer through `__APP_VERSION__` in `vite.config.ts`) and `backend/app/main.py` (`FastAPI(version=...)`, shown in the API docs). Keep the two equal.

**Releasing (whoever pushes does this):**
1. Bump both version fields and add a row below, in the same commit as the change log row in §12.
2. Tag that commit: `git tag -a vX.Y.Z -m "vX.Y.Z: one-line summary"`.
3. Push the commit and its tag together: `git push origin main --follow-tags`.
4. On GitHub: **Releases → Draft a new release → choose the tag → Generate release notes**, edit the notes into plain words, then **Publish release**.

**History** (tags on `main`; the 0.x tags were added on 2026-11-13 to past milestones):

| Version | Commit | Date | What it is |
|---|---|---|---|
| v2.4.1 | (this commit) | 2026-11-14 | Simpler "How a plan is made" section on the home page |
| v2.4.0 | `ee71ac2` | 2026-11-14 | Light theme only; clear globe with country borders; visible footer wordmark |
| v2.3.1 | `96e7d8b` | 2026-11-14 | Rest of the review fixed; planning about twice as fast |
| v2.3.0 | `5a53009` | 2026-11-14 | New city in about 15 s (was 50 s); full code review, about 30 defects fixed |
| v2.2.0 | `1e085c0` | 2026-11-14 | The globe is the real Earth: NASA imagery, clouds, night lights |
| v2.1.0 | `f91abae` | 2026-11-14 | Light theme with a toggle; dark stays the default |
| v2.0.0 | `4b2d0df` | 2026-11-14 | Complete redesign: night look, step-by-step planner with a boarding pass, designed dropdowns, interactive home |
| v1.3.1 | `d2ad81e` | 2026-11-14 | No auto-rickshaws in cities without them; cabs planned instead |
| v1.3.0 | `ef55403` | 2026-11-14 | Download a trip as a PDF |
| v1.2.0 | `3d89aad` | 2026-11-14 | Trip style (lowest cost, mid-range, premium); number fields fixed |
| v1.1.2 | `75561d1` | 2026-11-14 | Hotel search stays in the destination and matches words anywhere in a name |
| v1.1.1 | `96db37f` | 2026-11-14 | Every country's currency supported (150), so the suggestion works everywhere |
| v1.1.0 | `1d32b40` | 2026-11-14 | Destination currency suggested in the trip form, one click to use it |
| v1.0.2 | `7538486` | 2026-11-13 | Author credits with GitHub and LinkedIn; version shows correctly in local dev |
| v1.0.1 | `55e787c` | 2026-11-13 | Interface pass without template-looking elements, quick-start cities, components grouped by feature, quieter motion |
| v1.0.0 | `ea37847` | 2026-11-13 | Public-ready redesign: real 3D globe, atlas look, ticket header, day ribbons, budget charts; version system |
| v0.7.1 | `6c3d0f0` | 2026-11-13 | Ten interface fixes (form, notices, dates, waiting panel) |
| v0.7.0 | `e6de362` | 2026-11-10 | No accounts: trips saved in the browser; sign-in code removed |
| v0.6.0 | `c55f12c` | 2026-11-10 | First redesign; security hardening |
| v0.5.0 | `4017c8b` | 2026-11-08 | Azure Container Apps deployment setup |
| v0.4.0 | `16ca811` | 2026-11-08 | City loading about 6x faster (parallel sources) |
| v0.3.0 | `8501d6d` | 2026-11-07 | City autocomplete, trip-text parser, semantic interests |
| v0.2.0 | `353b86d` | 2026-11-07 | Worldwide open-data mode, cost model and currency conversion |
| v0.1.0 | `e492999` | 2026-11-07 | First planner: engines, Jaipur demo data, Google-ready providers |

**Planned** (from the owner's backlog, in order): another way in besides the planner (guided chat or picking on the map); a graph-based planning engine; **v3.0.0 multi-destination trips** (A to B to C).

---

## How to update this file

With **every commit** that changes behaviour, config, deployment or plans:
1. Update the header (`Last updated`, `Latest change`).
2. Edit the affected sections (§8 status, §9 tasks, §5 decisions, §10 gotchas).
3. Add a row at the top of §12; use "(this commit)", and replace older "(this commit)" entries with their hash.
4. Delete what's no longer true instead of appending contradictions.
