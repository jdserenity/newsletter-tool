# Knowledge

Hard-won lessons and context that should survive across agent sessions.

## X API pricing (2026-07)
Pay-per-use is the default for new developers. Legacy Basic/Pro subscriptions are being migrated away. Budget using ~$0.005/post read and ~$0.010/user lookup. X dedupes identical resource reads within 24h (only charged once). The app mirrors that rule when recording costs: tweet reads bill only for tweet IDs not fetched in the last 24h; repeat weekly fetches within 24h add $0 for already-seen posts.

## Database path
Accounts, tweets, and API cost rows live in one SQLite file. The path comes from `DATABASE_PATH` in `.env` (loaded on app import). If unset, the default is `~/.local/share/newsletter-tool/newsletter.db` — outside any git checkout so all worktrees see the same data.

If you previously used `data/newsletter.db` inside a repo folder, move it once:
```bash
mkdir -p ~/.local/share/newsletter-tool
mv /path/to/old/data/newsletter.db ~/.local/share/newsletter-tool/
```

## Fetch vs newsletter filtering
Replies and retweets can be excluded at the API via the `exclude` parameter — those tweets are never fetched and never billed. Quote tweets cannot be excluded server-side; they are always fetched and filtered in the newsletter builder when `include_quotes` is off.

## Tweet media
Media URLs come from the X API `attachments.media_keys` expansion (no extra post-read charge). Quote tweets also expand `referenced_tweets.id` — each quoted post is an additional ~$0.005 post read. `api_calls.units` counts timeline tweets plus expanded referenced tweets per response page (matches X billing: different posts in one request each count separately). `save_tweets` upserts on refetch so enriched `raw_json` (media, quoted tweets) replaces stale rows. Tweets already in the DB before media/quote expansion need one refetch after that fix landed.

## Terminology
The product name in the UI is **Mentally Stable X Experience**. Never use the word "digest" in code, templates, or docs. Weekly snapshots live in the `editions` table. The old `digests` table is renamed automatically on connect.

## Carousel jumps left after toggles / mark-read
Root cause was not scroll math: forms used `method=post` + `RedirectResponse("/")`, so the browser loaded a fresh homepage at `scrollLeft = 0`. Fix is in-place `fetch` with `Accept: application/json` (see `app/static/home.js`), not “save/restore scroll position.”

## Truncated tweet text
X API v2 returns a short `text` field unless `tweet.fields` includes `note_tweet` (full body for long posts). After enabling that, re-run `news-manual-fetch` (or wait for the weekly job) so stored `raw_json` / editions pick up full text. Old rows without `note_tweet` stay truncated until refetched. Requesting `note_tweet` does not add a separate billable unit — it is part of the same post-read payload (~$0.005 per post already counted).

## Account sort and capital letters
SQLite's default `ORDER BY handle` is binary/ASCII: uppercase `R` sorts before lowercase `a`, so `RuxandraTeslo` appeared first. Use `ORDER BY handle COLLATE NOCASE`.

## RSS readers say the feed does not exist
Root cause: `RequireAuthMiddleware` required a browser session for every path except `/auth/*`. Feed readers request `/feeds/{id}.xml` with no cookie, got a 303 to the HTML login page, and failed to parse RSS. Fix: treat `/feeds/` (and `/static/`) as public. Second issue: raw SQLite `built_at` is not a valid RSS `<pubDate>` — use RFC 822 via `email.utils.format_datetime`.

`week_bounds()` in `app/fetch/runner.py` uses the most recent complete Monday-to-Monday window in UTC.

## Tests
Run from repo root: `pytest` (or `venv/bin/python -m pytest`). Web tests use `TestClient` with scheduler disabled. Fetch tests use a fake HTTP client — no real API calls in CI.

## X OAuth sign-in (web app)
- Callback URL in `.env` (`X_OAUTH_CALLBACK_URL`) must match a Callback URL in the X Developer Console **exactly** (including `http` vs `https` and port).
- `SESSION_SECRET` signs the browser cookie; generate with `openssl rand -hex 32` if you need a value.
- Local dev default callback: `http://127.0.0.1:8000/auth/callback` — register that URL in the console for the app.
- Web tests disable auth (`auth_enabled=False`); auth behavior is covered in `tests/test_auth.py`.
- **Keys and tokens ≠ user auth setup.** Client ID/Secret on the Keys page are necessary but not sufficient. Open **OAuth 2.0 Keys → Edit settings** and enable OAuth 2.0, choose **Web App**, set Callback URI and Website URL, then save. The “Read and write” line under OAuth 1.0 Access Token on the Keys page does not configure OAuth 2.0.
- Immediate failure on X’s page (before a login form) usually means the OAuth 2.0 Edit settings page was never completed or the callback URI there does not match `X_OAUTH_CALLBACK_URL`.

## Owner follow/like rate limits (official X API docs, 2026)
Published per-user limits vary by legacy plan tier (Pro / Basic / Free). Pay-per-use developers should confirm limits in the Developer Console; treat Pro numbers as the upper bound until verified.

| Action | Endpoint | Pro (per user) | Basic (per user) |
| --- | --- | --- | --- |
| Follow | `POST /2/users/:id/following` | 50 / 15 min | 5 / 15 min |
| Like | `POST /2/users/:id/likes` | 1000 / 24 hours | 200 / 24 hours |

Follow uses a 15-minute window; likes use a 24-hour window. Exceeding either returns HTTP 429; response headers include `x-rate-limit-remaining` and `x-rate-limit-reset`. X Developer Guidelines state likes must be user-initiated (no bulk/auto-like products); this app likes only newsletter items the owner already chose to track — still automate conservatively. Re-follow is handled by POSTing follow directly (cheaper than paginating the full following list). Likes drain in one background thread: first like immediately after enqueue, then 60s ± 1–20s sleep between each until the queue is empty.

## Manual weekly fetch
```bash
news-manual-fetch
```
Fetches the last complete week, builds newsletters, then drains the like queue in the foreground (paced). Re-run `./scripts/setup.sh` or `pip install -e .` once after pulling if `news-manual-fetch` is not found.

## Database overview
```bash
news-db-status
```
Prints DB path, current newsletter week, per-account tweet/edition counts, liked vs stored tweet counts (plus queued likes), follow status, API cost, like-queue size, and OAuth status.

`news-manual-fetch` prints the database path it uses at startup — compare that to the path in `news-db-status` if the web UI and CLI ever look out of sync (e.g. dev server started before `.env` was saved).

## Follow and like need OAuth in the database
Likes drain in a background thread (or via `news-manual-fetch`) using tokens stored in the `oauth_session` table, not the browser cookie alone. Running `news-manual-fetch` can enqueue likes without OAuth saved — `news-db-status` then shows queued likes with `OAuth no`, and nothing gets liked until you sign in via the web app once (homepage load copies session tokens into the DB and resumes the queue). Follow on add-account uses the same refreshed owner token path.

Unfollowed tracked accounts (`followed_at` null) are retried on homepage load and on app startup when OAuth is in the DB — same idea as resuming a stalled like queue.

`news-db-status` per-account newsletter stats use each account's **latest edition** week (same as the homepage), not only the current fetch-target week shown in the header.
