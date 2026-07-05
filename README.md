# newsletter-tool

Personal tool that turns selected X accounts into clean weekly digests, viewable on the web and via RSS.

## Run

```bash
pip install -e ".[dev]"
cp .env.example .env   # then set X_BEARER_TOKEN in .env
news-dev
```

## Test

```bash
pytest
```

See `docs/ARCHITECTURE.md` for design details.
