# newsletter-tool

Personal tool that turns selected X accounts into clean weekly digests, viewable on the web and via RSS.

## Run

```bash
pip install -r requirements.txt
export X_BEARER_TOKEN=...   # X API v2 bearer token
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```

See `docs/ARCHITECTURE.md` for design details.
