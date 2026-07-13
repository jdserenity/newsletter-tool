# Architecture (human-readable)

What this app is, how the pieces fit, and how to run it. Confirmed facts only. Agent-dense detail lives in `scaffold/ARCH-LLM.md`. Lessons/traps live in `scaffold/PROJECT-KNOWLEDGE.md`.

## What it is

**More Mentally Stable X Experience** — a personal web app that turns chosen X (Twitter) accounts into clean **newsletters** (once or twice a week). You browse them on a webpage (or via RSS), mark posts and whole editions as read, and stay logged off X without losing the signal.

Not email. Not multi-user. Hosted on your VPS as a subdomain.

```
  X API (bearer)              Your browser (signed-in)
        │                              │
        ▼                              ▼
   scheduled fetch ──────────► SQLite  ◄──── like / dislike / settings
   (store tweets)                │
        │                        ├── homepage carousel
        ▼                        ├── /settings (cadence, append unread)
   build editions ───────────────┤
                                 └── public RSS + edition links
```

## Main screens

| Screen | What you see |
| --- | --- |
| **Landing** `/` (signed out) | Public artistic page: product name, short pitch, pricing (“API Costs + 1USD service fee. Extremely reasonable.”), Enter with X. Footer attribution with X profile links (full company name + motto links to the company account). Signed-in visitors never see this — same URL shows Home. |
| **Home** `/` (signed in) | Horizontal carousel: one card per tracked account (toggles, API cost, latest edition’s posts). Extra “Add account” card with cost estimate. |
| **Settings** `/settings` | Newsletter cadence (once/week or twice/week Mon+Thu; default twice), whether unread tweets carry into the next edition (default yes), list/remove accounts, month’s total API spend. Header button becomes **Home**. |
| **Edition** `/editions/{id}` | Single period for RSS deep links (public). Like/dislike only if signed in. |
| **RSS** `/feeds/{id}.xml` | Public feed per account (no login cookie). |

**Reading flow:** each tweet shows meta on the left (kind, date, stats, link). On the right, **X** then **✓** sit together — X dislikes (local bucket for later suggestions), ✓ likes on X when you click. Either marks the tweet read (dims and sinks to the bottom). Re-clicking undoes it. When every tweet is handled, the big newsletter checkmark moves to the **top** of the card so you can dismiss the whole week without scrolling. Empty weeks keep that checkmark at the bottom.

**Carousel:** scroll sideways between accounts; scroll inside a card for long weeks. Toolbar toggles and like/dislike save in place (no full page reload). On a phone, each card is nearly full-screen width with snap-between-cards scrolling; the tall desktop toolbar stacks so toggles stay tappable.

**Home screen icon:** same cream serif **Y** as the browser tab favicon (iOS “Add to Home Screen” uses the Apple touch icon / web app manifest, not the small tab icon alone).

## How the system is built

One Python **FastAPI** app does everything: pages, RSS, scheduled fetch.

| Piece | Job |
| --- | --- |
| `app/fetch/` | Talk to X (read posts, cost estimate). Respect per-account filters. Record cost rows. |
| `app/db.py` | SQLite: accounts, tweets, editions, costs, OAuth, likes/dislikes, read state, global app settings. |
| `app/newsletter.py` | Turn stored tweets into newsletter items (no network). |
| `app/main.py` + templates | Web UI. |
| `app/rss.py` | Feeds from stored editions only. |
| `app/scheduler.py` | Mon (+ Thu when twice-weekly) 06:00 UTC fetch (also `news-manual-fetch`). |
| `app/user_actions.py` | Owner like/unlike on X (checkmark click). |
| `app/auth.py` | Sign in with X (OAuth). RSS and edition links stay public. |

**Database file:** path from `DATABASE_PATH`, default `~/.local/share/newsletter-tool/newsletter.db` (outside the git folder so worktrees share data).

**Settings that matter for cost:** replies and retweets can be skipped at the API (never downloaded, never billed). Quote tweets are always fetched; turning quotes off only hides them when building the newsletter.

## Credentials (two kinds)

1. **App token** (`X_BEARER_TOKEN`) — weekly fetch and estimates; not “you” as a user.
2. **Your X login** (OAuth client id/secret, callback URL, session secret) — web sign-in; checkmark uses it to like tweets on X when you click.

## Run it

```bash
./scripts/setup.sh
cp .env.example .env    # fill X + OAuth values
source venv/bin/activate
news-dev                # local web server
pytest                  # tests
news-manual-fetch       # pull current period + build newsletters
news-db-status          # what’s in the database
```

**VPS:** one uvicorn process, env vars set (including a stable `DATABASE_PATH`), production OAuth callback registered in the X Developer Console, reverse proxy from your subdomain to the app port.
