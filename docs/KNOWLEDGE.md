# Knowledge

Hard-won lessons and context that should survive across agent sessions.

## X API pricing (2026-07)
Pay-per-use is the default for new developers. Legacy Basic/Pro subscriptions are being migrated away. Budget using ~$0.005/post read and ~$0.010/user lookup. X dedupes identical resource reads within 24h (only charged once).

## Database path
Accounts, tweets, and API cost rows live in one SQLite file. The path comes from `DATABASE_PATH` in `.env` (loaded on app import). If unset, the default is `~/.local/share/newsletter-tool/newsletter.db` — outside any git checkout so all worktrees see the same data.

If you previously used `data/newsletter.db` inside a repo folder, move it once:
```bash
mkdir -p ~/.local/share/newsletter-tool
mv /path/to/old/data/newsletter.db ~/.local/share/newsletter-tool/
```

## Fetch vs newsletter filtering
Replies and retweets can be excluded at the API via the `exclude` parameter — those tweets are never fetched and never billed. Quote tweets cannot be excluded server-side; they are always fetched and filtered in the newsletter builder when `include_quotes` is off.

## Terminology
The product is **Newsletter Tool**. Never use the word "digest" in code, templates, or docs. Weekly snapshots live in the `editions` table. The old `digests` table is renamed automatically on connect.

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
Prints DB path, current newsletter week, per-account tweet/edition counts, API cost, like-queue size, and OAuth status. If tweets were stored but no newsletter row exists for that week (the homepage reads `editions`, not raw `tweets`), the command warns and suggests `news-db-status --rebuild` to build newsletters from stored tweets without calling the X API.
