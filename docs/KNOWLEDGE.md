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

## Fetch vs digest filtering
Replies and retweets can be excluded at the API via the `exclude` parameter — those tweets are never fetched and never billed. Quote tweets cannot be excluded server-side; they are always fetched and filtered in the digest builder when `include_quotes` is off.

## Week boundaries
`week_bounds()` in `app/fetch/runner.py` uses the most recent complete Monday-to-Monday window in UTC.

## Tests
Run from repo root: `pytest` (or `venv/bin/python -m pytest`). Web tests use `TestClient` with scheduler disabled. Fetch tests use a fake HTTP client — no real API calls in CI.

## Manual weekly fetch
```bash
python -c "from app.scheduler import run_job; print(run_job())"
```

## X OAuth sign-in (web app)
- Callback URL in `.env` (`X_OAUTH_CALLBACK_URL`) must match a Callback URL in the X Developer Console **exactly** (including `http` vs `https` and port).
- `SESSION_SECRET` signs the browser cookie; generate with `openssl rand -hex 32` if you need a value.
- Local dev default callback: `http://127.0.0.1:8000/auth/callback` — register that URL in the console for the app.
- Web tests disable auth (`auth_enabled=False`); auth behavior is covered in `tests/test_auth.py`.
- OAuth authorize fails on X’s page (generic “Something went wrong”) when: callback URL mismatch, OAuth 2.0 user auth not enabled, wrong Client ID/Secret (OAuth 2.0 pair — not API Key), or requested scopes exceed app permissions (e.g. `like.write` needs Read and write in the console). Default app scopes are `users.read offline.access` only.
