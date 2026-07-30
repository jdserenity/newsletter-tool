# Codebase map (human-readable)

Maintainer’s map: which files do what, how data moves, where state lives. Prefer diagrams. Confirmed product/system facts → `scaffold/CODEMAP-LLM.md`. Lessons/traps → `scaffold/PROJECT-KNOWLEDGE.md`. Install/run → root `README.md`.

## What belongs here

- File / module map (roles, not product rules)
- Data and control flow (diagrams preferred)
- Where durable state lives (paths, tables as locations)

Do **not** put here: product pitch, pricing, UI behavior details, API cost rules, credentials how-to, run/deploy commands, glossaries, or lessons — those have other homes (above).

## Flow

```
  X API (bearer)              Browser                         Stripe
        │                        │                              │
        ▼                        ▼                              ▼
   scheduled fetch ──────────► SQLite  ◄──── UI actions       billing
   (store tweets)                │         like/dislike        webhooks
        │                        ├── landing → X OAuth → (pay if needed) → homepage carousel
        ▼                        ├── /settings
   build editions ───────────────┤
                                 └── public RSS + /editions/{id}
```

Manual path: `news-manual-fetch` → same fetch + edition build as the scheduler (`app/scheduler.py` → `app/fetch/runner.py`).

## Module map

| Path | Role |
| --- | --- |
| `app/main.py` | Routes, templates, lifespan (starts scheduler) |
| `app/db.py` | SQLite schema, queries, DB path, cost helpers |
| `app/newsletter.py` | Stored tweets + settings → edition items (no network) |
| `app/rss.py` | RSS XML from editions only |
| `app/billing.py` | Stripe Checkout, webhook, period-close refunds |
| `app/auth.py` | X OAuth, session, auth middleware / public prefixes |
| `app/user_actions.py` | Owner like/unlike on X (checkmark) |
| `app/scheduler.py` | Cron Mon (+ Thu if twice-weekly) 06:00 UTC; `run_job()` |
| `app/fetch/client.py` | X API v2 client (bearer) |
| `app/fetch/runner.py` | Period bounds, fetch window, store tweets, build editions; `fetch_new_account` on add when Stripe off |
| `app/fetch/estimate.py` | Pre-add cost estimate (no `api_calls` writes) |
| `app/cli.py` | `news-dev`, `news-manual-fetch`, `news-db-status` |
| `app/env.py` | Load `.env` |
| `app/templates/` | `base`, `home`, `landing`, `settings`, `edition`, `login`, `_tweet_macros` |
| `app/static/` | `carousel.js`, `home.js`, `landing.css`, `landing.js`, favicons |
| `tests/` | pytest; web TestClient with `with_scheduler=False`; fetch faked |

## Where state lives

| What | Where |
| --- | --- |
| DB file | `DATABASE_PATH`, else `~/.local/share/newsletter-tool/newsletter.db` (outside git; shared across worktrees) |
| Accounts, tweets, editions | `accounts`, `tweets`, `editions` |
| API spend rows | `api_calls` |
| Global cadence / append-unread | `app_settings` (singleton id=1) |
| Owner OAuth tokens | `oauth_session` (singleton id=1) |
| In-flight OAuth PKCE | `oauth_pending` (keyed by `state`; optional Checkout session id) |
| Users + billing | `users`, `billing_accounts`, `billing_payments`, `billing_refunds` |
| Like / dislike / read | `liked_tweets`, `disliked_tweets`, `read_tweets`, `read_newsletters` |
| Cached API payloads | `tweets.raw_json` (rebuild editions without refetch) |
| Session cookie | signed by `SESSION_SECRET` (signed-in user; may sync into `oauth_session` on `GET /`). Pre-callback OAuth handshake lives in `oauth_pending`, not the cookie. |
