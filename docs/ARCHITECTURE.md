# Architecture

Confirmed product and system facts for this project. Decisions only — no open questions or lessons learned (those belong in KNOWLEDGE.md).

## Product scope
- Personal tool that turns selected X (Twitter) users' output into clean, filterable, inbox-friendly weekly digests, so the owner can log off X without losing high-value signal.
- "Inbox-friendly" does not mean email. Email is out of scope.
- Single user for now (the owner). May become a sellable product later; no multi-tenant work yet.
- Accessed via a webpage on the owner's VPS, as a subdomain of the owner's personal domain.
- Owner can add and remove tracked X accounts.
- One digest per tracked account per week.
- Per-account granular settings (e.g. include/exclude quote tweets). Settings affect which API calls are made (fetch layer), not just digest rendering.
- Per-account visibility into X API cost incurred by that account, computed from rows in the `api_calls` table (no log files).
- Digests are formatted on the webpage.
- RSS feed structure is not finalized (per-account vs consolidated recap). v1 ships per-account feeds at `/feeds/{id}.xml` as the baseline.

## Tech stack
- Backend: Python + FastAPI — one app serves web pages, RSS, and the weekly fetch.
- Database: SQLite (single file under `data/newsletter.db`). Raw API responses cached in the DB so digests can be rebuilt without refetching.
- Frontend: server-rendered Jinja2 templates; htmx only if needed. No JS framework, no build step.
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
2. **Storage** (`app/db.py`) — SQLite schema and queries for accounts, tweets, digests, api_calls.
3. **Digest builder** (`app/digest.py`) — pure logic: stored tweets + settings → digest items. Also filters at build time so settings changes reshape digests without refetching.
4. **Web** (`app/main.py`, `app/templates/`) — account management, settings, digest pages, RSS (`app/rss.py`). RSS never hits the X API.
5. **Scheduler** (`app/scheduler.py`) — APScheduler weekly job; also runnable manually via `run_job()`.

## Run locally
```bash
pip install -e ".[dev]"
cp .env.example .env   # set X_BEARER_TOKEN in .env (loaded via python-dotenv)
news-dev
pytest
```

## Deploy (VPS)
Not yet documented in detail. App runs as a single uvicorn process; SQLite file lives on disk; set `X_BEARER_TOKEN` in the environment; reverse-proxy the subdomain to the app port.
