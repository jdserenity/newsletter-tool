# Architecture (agent reference)

Dense system map for agents. Confirmed facts only. Lessons → `scaffold/PROJECT-KNOWLEDGE.md`. Do not use the word "digest" anywhere.

## Product
- **Name (UI):** More Mentally Stable X Experience
- Personal single-user tool: selected X accounts → clean weekly newsletters (web + RSS). Email out of scope. No multi-tenant.
- Hosted on owner VPS as subdomain of personal domain.
- Add/remove tracked X accounts. One weekly **edition** per account per week (`editions` table).
- Per-account settings (`include_quotes`, `include_replies`, `include_retweets`) gate **fetch** and also re-filter at newsletter build.
- Per-account API cost from `api_calls` rows (not log files). Settings page also shows active account count + sum of `api_calls.cost_usd` for current calendar month (UTC).
- **Estimate cost** (add card): 3× `GET /2/tweets/counts/all` (complete Mon–Mon weeks, oldest→newest) ≈ $0.01 each ≈ $0.03. Project weekly fetch as `avg_tweets × $0.005 + $0.01` user lookup; default new-account filters (replies/retweets excluded at API; quotes always counted). Rejects already-tracked handles. Does **not** write `api_calls`.
- Homepage: horizontal carousel of account cards (settings toggles, cost, latest newsletter inline). No separate account detail page. On load: `repair_missing_editions` builds missing editions from stored tweets when current week has tweets but no edition (no X API). GET `/` stays local (SQLite + templates); may persist OAuth tokens from the browser session into `oauth_session`.
- Account lists: `ORDER BY handle COLLATE NOCASE`.
- Favicon / home-screen icon: serif **Y** on cream (`/static/favicon.svg` + PNG). Same mark for iOS Add to Home Screen via `apple-touch-icon.png` (180) + `site.webmanifest` (`icon-192` / `icon-512`).

## Stack
- Python 3.11+ / FastAPI / Jinja2 / SQLite / APScheduler / httpx
- No JS framework, no frontend build. Static: `carousel.js`, `home.js`
- Single uvicorn process on VPS

## Module map
| Path | Role |
| --- | --- |
| `app/main.py` | Routes, template render, lifespan (scheduler) |
| `app/db.py` | SQLite schema, queries, path resolution, cost helpers |
| `app/newsletter.py` | Pure: tweets + settings → edition items; unread-first sort; media/quote shaping |
| `app/rss.py` | RSS XML from editions (no X API) |
| `app/auth.py` | OAuth2 PKCE, session, `RequireAuthMiddleware`, public prefixes |
| `app/user_actions.py` | Owner like/unlike on X (checkmark click) |
| `app/scheduler.py` | Weekly job Mon 06:00 UTC; `run_job()` for manual |
| `app/fetch/client.py` | X API v2 client (bearer) |
| `app/fetch/runner.py` | Weekly fetch window, store tweets, build editions |
| `app/fetch/estimate.py` | Pre-add cost estimate |
| `app/cli.py` | `news-dev`, `news-manual-fetch`, `news-db-status` |
| `app/env.py` | Load `.env` |
| `app/templates/` | `base`, `home`, `settings`, `edition`, `login`, `_tweet_macros` |
| `app/static/` | `carousel.js`, `home.js`, favicons |
| `tests/` | pytest; web uses TestClient + `with_scheduler=False`; fetch faked |

## SQLite
- Path: `DATABASE_PATH` env, else `~/.local/share/newsletter-tool/newsletter.db` (outside repo; shared across worktrees).
- Tables: `accounts`, `tweets`, `editions`, `api_calls`, `oauth_session` (singleton id=1), `liked_tweets`, `disliked_tweets`, `read_tweets`, `read_newsletters`
- `accounts` defaults: quotes on, replies/retweets off; optional legacy `followed_at` (unused)
- Legacy `digests` → `editions` rename on connect
- Tweet `raw_json` caches API payload for rebuild without refetch

## Routes
**Public** (`PUBLIC_PREFIXES`): `/auth/`, `/feeds/`, `/editions/`, `/static/`  
**Auth required** (when enabled): everything else → 303 `/auth/login`

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/` | Carousel; repair missing editions (local); may persist OAuth session tokens |
| GET | `/settings` | Account list + remove; month cost |
| POST | `/accounts` | Add handle |
| POST | `/accounts/estimate` | JSON cost estimate |
| POST | `/accounts/{id}/remove` | → redirect `/settings` |
| GET | `/accounts/{id}` | → `/` |
| POST | `/accounts/{id}/settings` | Form toggles; JSON if `Accept: application/json` |
| POST | `/tweets/{id}/like` | Like + mark read; clears dislike; JSON ok |
| POST | `/tweets/{id}/dislike` | Dislike + mark read; clears like; JSON ok |
| POST | `/tweets/{id}/read` | `read=true` likes; `read=false` clears feedback + unread; JSON ok |
| POST | `/accounts/{id}/read-newsletter` | `week_start`; hides card for that week |
| GET | `/editions/{id}` | Public deep link; like/dislike UI only if signed in |
| GET | `/feeds/{id}.xml` | Public RSS; CDATA HTML bodies; RFC 822 pubDate; Cache-Control 300 |
| GET/POST | `/auth/login`, `/auth/login/start`, `/auth/callback`, `/auth/logout` | OAuth PKCE |

## UI behavior
- **Out-links** (X profile/tweet/media, RSS): `target="_blank" rel="noopener noreferrer"`. In-app nav same tab.
- **Tweet like/dislike:** meta left, X + ✓ grouped on the right (X immediately left of ✓); same on desktop and mobile. Check → like on X + `liked_tweets` + mark read. X → `disliked_tweets` only. Re-click → unlike + clear + unread. Dim + sort to bottom by **when marked read** (`read_tweets.read_at`), not publish order.
- **Newsletter mark-read:** ✓ on every card (incl. empty / no edition). Bottom while any unread; **top** of body when all tweets read (empty stays bottom). `read_newsletters(account_id, week_start)` → card gone for that week.
- **In-place actions:** settings toggles + like/dislike via `fetch` + JSON (`home.js`). No full-page POST/redirect (would reset carousel scrollLeft).
- **Long text:** fetch requests `note_tweet`; UI clamps 8 lines + More/Less.
- **Header:** Settings left of Sign out; on `/settings` control is Home → `/`.
- **Carousel:** wheel on chrome/gaps → horizontal; wheel on body → vertical in card. ←/→ cards; ↑/↓ scroll centered card. Scrollbars hidden. ≤700px: card width ≈ viewport, horizontal scroll-snap, stacked toolbar/toggles, ~44px tap targets, safe-area insets.
- Homepage locks `html,body { overflow: hidden }`; settings/edition unlock via `html:has(body.page-…)` + body class.

## X API
- Pay-per-use (~2026-07): ~$0.005/post read, ~$0.010/user read; post reads cap 2M/mo. X dedupes same resource within 24h; app mirrors when recording tweet-read costs.
- **App bearer** `X_BEARER_TOKEN`: weekly fetch + estimates (not user session).
- **User OAuth** `X_CLIENT_ID`, `X_CLIENT_SECRET`, `X_OAUTH_CALLBACK_URL`, `SESSION_SECRET`. Scopes default: `users.read tweet.read like.write offline.access` (`X_OAUTH_SCOPES` override). Sign-in + checkmark likes use owner session token (`owner_access_token`).
- **Fetch:** settings exclude replies/retweets at API when off. Quotes always fetched; filtered in builder if `include_quotes` off. Fields include `note_tweet`, media keys, `referenced_tweets.id` (quoted posts extra post reads). Media on `raw_json`; photos inline; video/GIF thumb → X. Media `t.co` stripped at build. `api_calls.units` = timeline tweets + expanded referenced IDs per page.
- Week window: `week_bounds()` = most recent complete Mon–Mon UTC (`app/fetch/runner.py`).

## Run / deploy
```bash
./scripts/setup.sh
cp .env.example .env   # X_BEARER_TOKEN + OAuth vars
source venv/bin/activate
news-dev               # local server
news-manual-fetch      # fetch + build newsletters
news-db-status         # DB overview
pytest
```
VPS: one uvicorn; set env vars + `DATABASE_PATH`; register production OAuth callback in X Developer Console; reverse-proxy subdomain → app port.
