# Architecture

Confirmed product and system facts for this project. Decisions only — no open questions or lessons learned (those belong in KNOWLEDGE.md).

## Product scope
- Personal tool that turns selected X (Twitter) users' output into clean, filterable, inbox-friendly weekly newsletters, so the owner can log off X without losing high-value signal.
- Product name in the UI: **Newsletter Tool**. Do not use the word "digest" anywhere in the codebase.
- "Inbox-friendly" does not mean email. Email is out of scope.
- Single user for now (the owner). May become a sellable product later; no multi-tenant work yet.
- Accessed via a webpage on the owner's VPS, as a subdomain of the owner's personal domain.
- Owner can add and remove X accounts.
- One weekly newsletter edition per account per week (stored in the `editions` table).
- Per-account granular settings (e.g. include/exclude quote tweets). Settings affect which API calls are made (fetch layer), not just newsletter rendering.
- Per-account visibility into X API cost incurred by that account, computed from rows in the `api_calls` table (no log files).
- Homepage: horizontally scrollable carousel of newsletter cards (one per account). Each card shows settings toggles, API cost, and the latest newsletter inline — no separate account list or detail page.
- RSS feed structure is not finalized (per-account vs consolidated recap). v1 ships per-account feeds at `/feeds/{id}.xml` as the baseline.

## Tech stack
- Backend: Python + FastAPI — one app serves web pages, RSS, and the weekly fetch.
- Database: SQLite (single file). Path from `DATABASE_PATH` in `.env` (or the process environment on the VPS). Default: `~/.local/share/newsletter-tool/newsletter.db` — outside the repo so git worktrees share one database. Raw API responses cached in the DB so newsletters can be rebuilt without refetching.
- Frontend: server-rendered Jinja2 templates; small inline JS for carousel drag-scroll. No JS framework, no build step.
- Scheduling: APScheduler inside the app (weekly fetch, Monday 06:00 UTC). Can be reduced to cron later.
- Hosting: owner's VPS.

## X API (confirmed 2026-07)
- Pay-per-use credits in the Developer Console; legacy subscription tiers are deprecated for new developers.
- Approximate unit costs: $0.005 per post read, $0.010 per user read. Post reads capped at 2M/month.
- Same resource requested twice within 24 hours is charged once (X deduplication).
- Uses X API v2. Auth: `X_BEARER_TOKEN` environment variable.

## System layout
Single repo, single FastAPI app:
1. **Fetch** (`app/fetch/`) — X API v2 client. Per-account settings gate which calls run. Every request writes to `api_calls` (endpoint, units, estimated cost).
2. **Storage** (`app/db.py`) — SQLite schema and queries for accounts, tweets, editions, api_calls.
3. **Newsletter builder** (`app/newsletter.py`) — pure logic: stored tweets + settings → newsletter items. Also filters at build time so settings changes reshape newsletters without refetching.
4. **Web** (`app/main.py`, `app/templates/`) — homepage carousel, per-card settings, edition pages (for RSS deep links), RSS (`app/rss.py`). RSS never hits the X API.
5. **Scheduler** (`app/scheduler.py`) — APScheduler weekly job; also runnable manually via `run_job()`.

## Run locally
```bash
./scripts/setup.sh
cp .env.example .env   # set X_BEARER_TOKEN; optional DATABASE_PATH (see .env.example)
source venv/bin/activate
news-dev
pytest
```

## Deploy (VPS)
App runs as a single uvicorn process. Set `X_BEARER_TOKEN` and `DATABASE_PATH` (e.g. `/var/lib/newsletter-tool/newsletter.db`) in the environment; reverse-proxy the subdomain to the app port.
