# Instructions for AI coding agents

You are working on **TripAura** (FastAPI backend + React/Vite/TypeScript frontend). Before doing anything:

1. **Read [HANDOFF.md](HANDOFF.md) completely.** It holds the current state, decisions, open tasks and gotchas. Then run `git log --oneline -15`.
2. Read only the docs you need: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/CONFIGURATION.md](docs/CONFIGURATION.md), [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md), [docs/API.md](docs/API.md).
3. Make sure tests pass before and after your change: `cd backend && .venv/Scripts/python -m pytest -q` and `cd frontend && npm run build`.

## Rules

- **Update HANDOFF.md in the same commit as every change** (header, affected sections, change-log row). A pre-commit hook enforces this when enabled (`git config core.hooksPath .githooks`).
- **No AI attribution anywhere:** no `Co-Authored-By` lines for AI tools, no assistant/tool names in code, docs, comments or commit messages.
- **Never commit secrets.** Real values live in Modal secrets, GitHub Actions secrets and Vercel env vars (see HANDOFF §7).
- Don't push or deploy unless the human asks; commit locally with clear messages.
- Keep the honesty rules: label data sources, keep external ratings separate from the suitability score, mark estimates, never silently replace failed live data with mock data.
- Tests must stay offline (fakes and `httpx.MockTransport`); add tests for behaviour changes.
- Engines (`backend/app/engines/`) stay pure: no network calls there.
- Don't mutate cached place objects in place (shared with the city cache); reassign fields instead.
- Bump `DATASET_VERSION` in `backend/app/providers/open/city_store.py` when the cached city data shape or merge logic changes.
