# Deployment

The recommended free setup (no credit card anywhere):

| Part | Host | Why |
|---|---|---|
| Frontend (React/Vite) | **Vercel**, Hobby plan (free) | Static site, global CDN, redeploys automatically from GitHub |
| Backend (FastAPI) | **Modal** (serverless containers, $30 free credit every month) | Enough memory for the backend (~750 MB peak measured). Scales to zero when idle, so credit is only used while requests run (a 2 GB / 1 CPU container is roughly $0.06 per active hour). Free hosts with 512 MB (Render, Koyeb) are too small, and Hugging Face Docker is now paid |
| Database | **Neon** Postgres, free plan (1 GB) | Durable storage for saved trips and cached cities. Modal containers have no permanent disk |

How fast it is:
- **First trip to a brand-new city:** about 35–40 s (measured locally for Rome). All sources load in parallel, and OpenStreetMap is capped at 25 s.
- **Every later trip there:** about 1–2 s.
- **After idle time:** the backend sleeps 5 minutes after the last request. The next request waits a few seconds while a container starts; the site shows "Connecting to the TripAura server…" during that time.
- **Request limit:** Modal cuts any web request off at 150 s, which the loading above stays well inside.

Files: `backend/modal_app.py` (Modal app definition) and `.github/workflows/deploy-backend-modal.yml` (auto-deploy).

### 1. Database (Neon)
Create a project (region **AWS US East 1**), click **Connect**, turn on **connection pooling**, and copy the connection string. That's your `DATABASE_URL`.

### 2. Modal account and settings (~5 minutes)
1. Sign up at [modal.com](https://modal.com) with GitHub. The Starter plan is free and includes $30 of compute credit each month.
2. Create the app's settings: **Secrets → Create new secret → Custom**. Name it exactly **`trip-aura-env`** and add:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | your Neon connection string |
   | `CORS_ORIGINS` | your Vercel URL, e.g. `https://trip-aura.vercel.app` (use `http://localhost:5173` until you have it) |
   | `CORS_ORIGIN_REGEX` | `https://trip-aura-.*\.vercel\.app` (optional; allows Vercel preview links) |
   | `OPEN_USER_AGENT` | `TripAura/1.0 (+https://github.com/ranjanvrma/trip-aura)` |

3. Create an API token: **Settings → API Tokens → New token**. Copy the **Token ID** (`ak-...`) and **Token Secret** (`as-...`).

### 3. Deploy from GitHub
1. In the GitHub repo, go to **Settings → Secrets and variables → Actions** and add:
   - **Secret** `MODAL_TOKEN_ID`
   - **Secret** `MODAL_TOKEN_SECRET`
   - **Variable** `MODAL_ENABLED` = `true`
2. Go to **Actions → "Deploy backend (Modal)" → Run workflow**. The first build takes about 5–8 minutes because it bakes the city list and AI model into the image. Later deploys reuse cached layers.
3. The log ends with the URL: `https://<your-modal-username>--trip-aura-api.modal.run`. It's also shown under **Apps → trip-aura-api** in the Modal dashboard.
4. Check it: `<url>/api/health` should return `{"status":"ok"}`, and `<url>/docs` shows the API.

From then on, every push to `main` that changes `backend/` redeploys automatically.

To deploy from your PC instead: `pip install modal`, run `modal token new` (it opens a browser login), then from the `backend/` folder run `modal deploy modal_app.py`.

### 4. Frontend (Vercel)
1. **Add New → Project**, import the repo, and set **Root Directory** to `frontend`. Framework: Vite.
2. Add the environment variable `VITE_API_BASE_URL` = your Modal URL (no trailing slash).
3. **Deploy**. Then set `CORS_ORIGINS` in the Modal secret to the Vercel URL and redeploy the backend (**Actions → Deploy backend (Modal) → Run workflow**). Secrets are read when a container starts.

### 5. Check it end to end
- Open the Vercel URL. You should see the "Worldwide open data" banner.
- Type "Lis" in the city box; Lisbon should appear.
- Generate a 2-day trip.
- If the site can't reach the backend, check `VITE_API_BASE_URL`, `CORS_ORIGINS` (exact URL, no trailing slash), and the app's logs in the Modal dashboard.

**Cost control:** usage is shown under Modal's **Usage** page. The app runs at most one container (`max_containers=1`) and sleeps after 5 idle minutes, so a project like this uses a small fraction of the $30 monthly credit. If the credit ever runs out, the backend pauses until the next month; nothing is charged on the free plan.

### Alternatives
- **Any Linux server or VPS** (Oracle Cloud Always Free, a home server, etc.): `deploy/oracle/` has a Docker Compose setup with Caddy for automatic HTTPS. `setup.sh` installs everything on Ubuntu, and `.github/workflows/deploy-backend-oracle.yml` redeploys over SSH. Oracle's sign-up needs a credit card, and often rejects Indian debit cards.
- **Render (paid):** `render.yaml` deploys the Docker image on the Standard plan (2 GB). The free and Starter plans (512 MB) are too small.

### Continuous integration
`.github/workflows/ci.yml` runs the backend tests (Python 3.12) and the frontend build on every push and pull request. Each deploy workflow runs only after it has been configured (`MODAL_ENABLED` or `ORACLE_HOST`).
