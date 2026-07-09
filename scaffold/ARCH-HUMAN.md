# Architecture (human-readable)

What this app is, how the pieces fit, and how to run it. Confirmed facts only. Agent-dense detail lives in `scaffold/ARCH-LLM.md`. Lessons/traps live in `scaffold/PROJECT-KNOWLEDGE.md`.

## What it is

**More Mentally Stable X Experience** — a personal web app that turns chosen X (Twitter) accounts into clean **weekly newsletters**. You browse them on a webpage (or via RSS), mark posts and whole weeks as read, and stay logged off X without losing the signal.

Not email. Not multi-user. Hosted on your VPS as a subdomain.

```
  X API (bearer)              Your browser (signed-in)
        │                              │
        ▼                              ▼
   weekly fetch ─────────────► SQLite  ◄──── mark-read / settings
   (store tweets)                │
        │                        ├── homepage carousel
        ▼                        ├── /settings
   build editions ───────────────┤
        │                        └── public RSS + edition links
        ▼
   paced likes / follows (your OAuth)
```

## Main screens

| Screen | What you see |
| --- | --- |
| **Home** `/` | Horizontal carousel: one card per tracked account (toggles, API cost, this week’s posts). Extra “Add account” card with cost estimate. |
| **Settings** `/settings` | List accounts, remove them, month’s total API spend. Header button becomes **Home**. |
| **Edition** `/editions/{id}` | Single week for RSS deep links (public). Mark-read only if signed in. |
| **RSS** `/feeds/{id}.xml` | Public feed per account (no login cookie). |

**Reading flow:** check off individual tweets (they dim and sink to the bottom). When every tweet is checked, the big newsletter checkmark moves to the **top** of the card so you can dismiss the whole week without scrolling. Empty weeks keep that checkmark at the bottom.

**Carousel:** scroll sideways between accounts; scroll inside a card for long weeks. Toolbar toggles and checkmarks save in place (no full page reload).

## How the system is built

One Python **FastAPI** app does everything: pages, RSS, weekly fetch, likes/follows.

| Piece | Job |
| --- | --- |
| `app/fetch/` | Talk to X (read posts, cost estimate). Respect per-account filters. Record cost rows. |
| `app/db.py` | SQLite: accounts, tweets, editions, costs, OAuth, likes, read state. |
| `app/newsletter.py` | Turn stored tweets into newsletter items (no network). |
| `app/main.py` + templates | Web UI. |
| `app/rss.py` | Feeds from stored editions only. |
| `app/scheduler.py` | Monday 06:00 UTC weekly job (also `news-manual-fetch`). |
| `app/user_actions.py` | Follow on add; like newsletter posts on a slow background queue. |
| `app/auth.py` | Sign in with X (OAuth). RSS and edition links stay public. |

**Database file:** path from `DATABASE_PATH`, default `~/.local/share/newsletter-tool/newsletter.db` (outside the git folder so worktrees share data).

**Settings that matter for cost:** replies and retweets can be skipped at the API (never downloaded, never billed). Quote tweets are always fetched; turning quotes off only hides them when building the newsletter.

## Credentials (two kinds)

1. **App token** (`X_BEARER_TOKEN`) — weekly fetch and estimates; not “you” as a user.
2. **Your X login** (OAuth client id/secret, callback URL, session secret) — web UI, follow, like.

## Run it

```bash
./scripts/setup.sh
cp .env.example .env    # fill X + OAuth values
source venv/bin/activate
news-dev                # local web server
pytest                  # tests
news-manual-fetch       # pull this week + build + likes
news-db-status          # what’s in the database
```

**VPS:** one uvicorn process, env vars set (including a stable `DATABASE_PATH`), production OAuth callback registered in the X Developer Console, reverse proxy from your subdomain to the app port.
