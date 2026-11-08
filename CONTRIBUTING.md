# Contributing

TripAura is built by **Ranjan Verma** and **Chinmay Dahiya**. These steps keep both of us (and any AI assistant either of us uses) in sync.

## 1. Catch up before you start

```bash
git pull
git log --oneline -15
```
Then read **[HANDOFF.md](HANDOFF.md)**. It's the single source of truth for what's done, what's in progress, why things are the way they are, and what to do next. If you use an AI assistant, point it at [AGENTS.md](AGENTS.md) first.

One-time setup per clone (enables the HANDOFF reminder hook):
```bash
git config core.hooksPath .githooks
```

## 2. Work

- Setup, running and tests: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
- Keep tests offline and add one for every behaviour change.
- Never commit secrets (`.env` files are ignored; only `*.env.example` is tracked).

## 3. Commit (and update the handoff)

Every commit that changes code, config, deployment or plans **must also update `HANDOFF.md`**:
1. Header: `Last updated` date and `Latest change`.
2. The sections your change affects (deployment status, open tasks, decisions, gotchas).
3. A new row at the top of the change log.

The pre-commit hook stops the commit if `HANDOFF.md` isn't staged. For truly trivial commits (typo fixes), bypass with `SKIP_HANDOFF=1 git commit ...`.

Commit messages: short imperative subject, then a body saying what changed and why. No AI-tool attribution lines.

## 4. Push and deploy

- Pushing to `main` runs CI (backend tests + frontend build).
- Changes under `backend/` redeploy the backend to Modal (once configured); Vercel rebuilds the frontend.
- Use a branch and pull request for bigger changes; the PR template has a HANDOFF checklist.

## Getting credited on GitHub

GitHub's **Contributors** list counts commits whose author email belongs to your GitHub account:
- Set `git config user.email` to your GitHub email (or `ID+username@users.noreply.github.com`) before committing.
- For pair work, end the commit message with `Co-authored-by: Name <github-email>`.
