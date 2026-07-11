# newsletter-tool

Personal tool that turns selected X accounts into clean newsletters (once or twice a week), viewable on the web and via RSS.

## Run

```bash
./scripts/setup.sh
cp .env.example .env   # then set X_BEARER_TOKEN and OAuth vars in .env
source venv/bin/activate
news-dev
```

Manual fetch for the current schedule period (build newsletters + paced likes):

```bash
news-manual-fetch
```

Database overview (counts, editions, API cost):

```bash
news-db-status
```

## Test

```bash
pytest
```

See `scaffold/ARCH-HUMAN.md` for design details.
