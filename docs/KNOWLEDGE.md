# Knowledge

Hard-won lessons and context that should survive across agent sessions.

## X API pricing (2026-07)
Pay-per-use is the default for new developers. Legacy Basic/Pro subscriptions are being migrated away. Budget using ~$0.005/post read and ~$0.010/user lookup. X dedupes identical resource reads within 24h (only charged once).

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
