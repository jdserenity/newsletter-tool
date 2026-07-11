# Project knowledge

Hard-won lessons and traps. Product/system facts live only in `scaffold/ARCH-LLM.md` / `scaffold/ARCH-HUMAN.md` — do not restate them here.

## iOS home-screen icon ignores the tab favicon
Safari “Add to Home Screen” does **not** use `<link rel="icon">`. Without `<link rel="apple-touch-icon" href="…">` (PNG, typically 180×180) it falls back to a screenshot of the page. Ship the same art as the favicon there, plus optional `site.webmanifest` icons for Android/desktop install. Prefer opaque PNG (no transparency) so iOS does not invent a black background.

## DB path: old in-repo location
Default is outside the checkout (`~/.local/share/newsletter-tool/newsletter.db`) so worktrees share data. If you still have `data/newsletter.db` inside a repo folder, move it once:

```bash
mkdir -p ~/.local/share/newsletter-tool
mv /path/to/old/data/newsletter.db ~/.local/share/newsletter-tool/
```

`news-manual-fetch` prints the DB path at startup — if the web UI and CLI disagree, compare that path to `news-db-status` (classic cause: dev server started before `.env` was saved).

## Carousel jumps left after toggles / mark-read
Not a scroll-math bug. Full form `POST` + `RedirectResponse("/")` reloads `/` at `scrollLeft = 0`. Keep toolbar toggles and mark-read on in-place `fetch` + `Accept: application/json` (`app/static/home.js`). Do not “fix” this by saving/restoring scroll on a full reload.

## Truncated tweet text
Without `note_tweet` in `tweet.fields`, X returns ~280-char `text`. Enabling it does not rebill as a separate unit, but **old rows stay truncated until refetched** (`news-manual-fetch` or weekly job). Same for tweets stored before media/quote expansion: `save_tweets` upserts, but only on refetch.

## Handle sort looks wrong with capitals
SQLite default `ORDER BY handle` is binary: uppercase before lowercase (`RuxandraTeslo` first). Lists must use `COLLATE NOCASE`.

## RSS readers report “feed not found”
Any one of these breaks readers (they often mislabel the failure):

1. **Auth:** feeds polled without cookies must stay public (`/feeds/`, also `/editions/`, `/static/`). Auth middleware redirecting to HTML login = unparseable “feed.”
2. **`<pubDate>`:** raw SQLite `built_at` is not RSS — use RFC 822 (`email.utils.format_datetime`).
3. **Invalid XML:** HTML in item descriptions must be CDATA (and split if `]]>` appears in tweet text). Raw `<br>`/`<img>` makes the document not well-formed.

## Settings / edition pages won’t scroll
Homepage sets `html, body { overflow: hidden }` for the carousel. Overriding **only** `body.page-settings` / `body.page-edition` leaves `html` locked. Unlock both (`html:has(body.page-…)` + body class).

## X OAuth console traps
- `X_OAUTH_CALLBACK_URL` must match a console Callback URL **exactly** (scheme, host, port, path). Local default: `http://127.0.0.1:8000/auth/callback`.
- Client ID/Secret on the Keys page is not enough. Complete **OAuth 2.0 → Edit settings**: enable OAuth 2.0, Web App, Callback URI + Website URL, save. OAuth 1.0 “Read and write” on Keys is a different system.
- Immediate fail on X’s authorize page (before login form) usually means OAuth 2.0 settings never saved or callback mismatch.
- `SESSION_SECRET` signs the cookie; `openssl rand -hex 32` if you need one.
- Web tests use `auth_enabled=False`; real auth coverage is `tests/test_auth.py`.

## Follow / like: tokens, limits, queue
- Drain uses **`oauth_session` in SQLite**, not the browser cookie alone. CLI can enqueue likes with `OAuth no` in `news-db-status` until you sign in once via the web app (homepage bootstraps tokens if missing and resumes the queue).
- Unfollowed tracked accounts (`followed_at` null) retry in a **background** thread on homepage load (`schedule_owner_maintenance`) and on app startup when OAuth is present — never block `GET /` on X HTTP. Access tokens are reused until near `expires_at`; do not refresh on every page load.

## Do not put X network on homepage render
`GET /` used to call `get_valid_access_token` (always hit X token endpoint) and `retry_pending_follows` inline, so Settings → Home felt multi-second even when nothing changed. Keep homepage render local (SQLite + templates). Network owner work belongs in background maintenance or explicit write paths (add account).
- POST follow directly (no “already following?” list crawl) — cheaper and enough for re-follow.
- Published per-user rate limits (X docs, 2026; confirm in Developer Console for pay-per-use):

  | Action | Endpoint | Pro | Basic |
  | --- | --- | --- | --- |
  | Follow | `POST /2/users/:id/following` | 50 / 15 min | 5 / 15 min |
  | Like | `POST /2/users/:id/likes` | 1000 / 24 h | 200 / 24 h |

  429 responses expose `x-rate-limit-remaining` / `x-rate-limit-reset`. X guidelines want likes user-initiated; this app only likes items for accounts the owner chose to track — still pace conservatively (first like immediate, then ~60s ±1–20s).

## CLI entry points missing after pull
If `news-manual-fetch` / `news-db-status` / `news-dev` are not found: re-run `./scripts/setup.sh` or `pip install -e .`.

## X API 503 used to abort the whole newsletter run
A single `503 Service Unavailable` from `api.x.com` used to raise immediately in `XClient`, so scheduled jobs (and `news-manual-fetch`) could finish with zero new editions. Bearer GETs now retry transient statuses and transport errors; a per-account failure no longer blocks the other accounts’ editions.

## `news-db-status` week column
Per-account newsletter stats use each account’s **latest edition** week (same as the homepage card), not only the current fetch-target week shown in the status header.
