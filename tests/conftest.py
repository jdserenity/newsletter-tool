import json
import pytest

from app import db

@pytest.fixture
def conn():
  c = db.connect(":memory:")
  yield c
  c.close()

def make_tweet(tweet_id, kind="post", text=None, created_at="2026-06-30T12:00:00Z", metrics=None):
  raw = {"id": tweet_id, "text": text or f"tweet {tweet_id}", "created_at": created_at,
         "public_metrics": metrics or {"like_count": 3, "retweet_count": 1}}
  # mirrors the shape of a row from the tweets table
  return {"tweet_id": tweet_id, "kind": kind, "text": raw["text"], "created_at": created_at, "raw_json": json.dumps(raw)}
