# newsletter-tool

Personal tool that turns selected X accounts into clean weekly newsletters, viewable on the web and via RSS.

## Run

```bash
./scripts/setup.sh
cp .env.example .env   # then set X_BEARER_TOKEN and OAuth vars in .env
source venv/bin/activate
news-dev
```

Manual weekly fetch (build newsletters + paced likes):

```bash
news-manual-fetch
```

Database overview (counts, editions, API cost):

```bash
news-db-status
news-db-status --rebuild   # rebuild newsletters from stored tweets (no API calls)
```

## Test

```bash
pytest
```

See `docs/ARCHITECTURE.md` for design details.
