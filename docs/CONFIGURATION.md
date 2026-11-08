# Configuration

All backend settings are environment variables (or `backend/.env`, copied from `backend/.env.example`).
Defaults live in `backend/app/core/config.py`.

## Backend variables

`backend/.env` (copy from `backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATA_MODE` | `open` | `open` (worldwide open data), `live` (Google) or `mock` (Jaipur demo) |
| `GOOGLE_MAPS_API_KEY` | empty | Server key: Places API (New), Routes API, Geocoding API, Time Zone API |
| `GOOGLE_ENRICHMENT` | `true` | In open mode, add Google ratings when a key is set |
| `GOOGLE_HTTP_TIMEOUT_SECONDS` | `10` | Timeout for Google requests |
| `OPEN_USER_AGENT` | `TripAura/0.1 (+https://github.com/ranjanvrma/trip-aura)` | Identifies the app to OSM/Wikimedia. Must include a contact URL or email, or Wikimedia returns HTTP 403 |
| `NOMINATIM_URL` | public Nominatim | Geocoding server (self-host for production) |
| `OVERPASS_URLS` | 3 public mirrors | Comma-separated Overpass endpoints, tried in order |
| `OSM_TIME_BUDGET_SECONDS` | `25` | Time box for the best-effort OSM layer. Its 3 queries run in parallel with Overture, Wikidata and Wikivoyage |
| `WARMUP_ON_START` | `true` | Preload the city index and AI model in the background when the server starts |
| `OVERTURE_ENABLED` / `OVERTURE_RELEASE` | `true` / latest | Overture places layer. The release is auto-detected from the STAC catalog |
| `WIKIVOYAGE_ENABLED` | `true` | Guidebook dish suggestions |
| `CITY_CACHE_DAYS` | `30` | How long a loaded city is reused before refreshing |
| `FX_URL` | Frankfurter (ECB rates) | Exchange rates for non-USD currencies |
| `ROUTING_ENGINE` | `heuristic` | `heuristic` (distance × speed estimates) or `osrm` |
| `OSRM_DRIVING_URL` / `OSRM_WALKING_URL` | public OSRM demo servers | Used when `ROUTING_ENGINE=osrm` (demo servers aren't meant for production) |
| `MAX_CANDIDATE_PLACES` / `MAX_FOOD_CANDIDATES` | `150` / `800` | How many attractions and restaurants the planner considers |
| `SEMANTIC_ENABLED` / `SEMANTIC_MODEL` | `true` / `BAAI/bge-small-en-v1.5` | Local embedding model for semantic interests and sentiment |
| `DATA_DIR` | `backend/data` | Where the GeoNames index and the model are stored |
| `GEONAMES_URL` / `PHOTON_URL` | GeoNames dumps / photon.komoot.io | City index source and address autocomplete server |
| `AI_ENABLED` | `false` | Turns on the optional AI overview |
| `ANTHROPIC_API_KEY` | empty | Needed when `AI_ENABLED=true` |
| `ANTHROPIC_MODEL` | empty | Model id for the overview; required when `AI_ENABLED=true` |
| `DATABASE_URL` | `sqlite:///backend/tripaura.db` | SQLite or Postgres. Hosted `postgres://` URLs (Neon, Render, Supabase) work as-is |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed frontend origins (comma-separated; your Vercel URL in production) |
| `CORS_ORIGIN_REGEX` | empty | Extra allowed origins as a regex, e.g. `https://trip-aura-.*\.vercel\.app` for preview deployments |
| `PORT` | `7860` in Docker | Port the container listens on (Render/Railway/Fly set this themselves) |
| `DUCKDB_MEMORY_LIMIT` / `DUCKDB_THREADS` | `256MB` / `2` | Limits for the Overture query |
| `LOG_LEVEL` | `INFO` | Logging level |

`frontend/.env` (optional, copy from `frontend/.env.example`):

| Variable | Purpose |
|---|---|
| `VITE_GOOGLE_MAPS_API_KEY` | Browser key (restricted by HTTP referrer) for the Maps JavaScript API. Leave it empty to use Leaflet/OSM |
| `VITE_API_BASE_URL` | Backend URL. Leave it empty to use the Vite proxy |

## Free APIs: what you need to sign up for

**Nothing is required.** In the default `open` mode, every data source is free and needs no key or account:

| Service | Used for | Key? | Usage rule to respect |
|---|---|---|---|
| Overture Maps (public S3 files) | Places worldwide | No | Free, open licence |
| Wikidata query service | Famous sights | No | User-Agent must include a contact URL or email (`OPEN_USER_AGENT`) |
| OpenStreetMap Overpass | Opening hours, fees, diet tags, stations | No | Light use; cached for 30 days per city |
| Wikivoyage | Local dishes | No | Same User-Agent rule as Wikidata |
| Nominatim | City and hotel geocoding | No | At most 1 request/second (the app enforces it) |
| Photon (komoot) | Address autocomplete | No | Fair use |
| GeoNames dump | City autocomplete (downloaded once, at build time) | No | CC BY 4.0 attribution (shown in the dropdown) |
| Frankfurter (ECB rates) | Currency conversion | No | Free |
| OpenStreetMap tiles | Map background (Leaflet) | No | Attribution shown; fine for low traffic |

**Optional extras (not free, or free only up to a quota):**
- **Google Maps Platform** (`GOOGLE_MAPS_API_KEY`) adds real Google ratings and reviews to the places in each plan. Google gives a free monthly quota per API, but you need a billing account with a card. Check Google's current pricing before enabling it, and restrict the key to the Places API.
- **Anthropic** (`ANTHROPIC_API_KEY`, `AI_ENABLED=true`) adds an AI-written trip overview. It's paid per use, and the app works fully without it.

## Google Maps Platform (optional)

The code for these is written and unit-tested against mocked HTTP responses, but it hasn't been run against Google's real APIs yet:

- `providers/google/places.py`: Places API (New) Text Search and Place Details, with field masks, rating, reviews, hours, price range and vegetarian flag
- `providers/google/routes.py`: Routes API `computeRoutes` (`TRAFFIC_AWARE` driving, transit with vehicle-type filters for metro, bus and train, transit fares, polylines)
- `providers/google/geocoding.py`: Geocoding API for the city and accommodation, plus the Time Zone API so departure times are local
- `components/map/GoogleMap.tsx`: Maps JavaScript API renderer (markers, polylines, traffic layer, accuracy circle)

There are two ways to use a key:
- **Keep `DATA_MODE=open` and set `GOOGLE_MAPS_API_KEY`.** Open data stays the base layer, and Google adds ratings and reviews to the places in each plan (`services/enrichment.py`, about 30–40 Text Search calls per trip).
- **Set `DATA_MODE=live`.** Google supplies everything: places, routes with live traffic, and geocoding.

`VITE_GOOGLE_MAPS_API_KEY` in `frontend/.env` turns on the Google map renderer in either mode.

Things to check when you connect:
- The field masks match your SKU tier.
- Caching and storage of Places content meets Google's terms. Saved trips currently store place snapshots.
- Cab and auto fares stay estimates, because Google doesn't publish them.
