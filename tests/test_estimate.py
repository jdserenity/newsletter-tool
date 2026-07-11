from datetime import datetime, timezone

import pytest

from app.fetch.client import XClient, COST_PER_COUNTS_ALL, COST_PER_POST_READ, COST_PER_USER_READ
from app.fetch.estimate import counts_query, estimate_fetch_cost, prior_week_windows

class FakeResponse:
  def __init__(self, body, status_code=200):
    self.body = body; self.status_code = status_code; self.headers = {}
  def raise_for_status(self): pass
  def json(self): return self.body

class FakeCountsHttp:
  def __init__(self, counts_per_call):
    self.counts_per_call = list(counts_per_call); self.requests = []
  def get(self, path, params=None):
    self.requests.append((path, params or {}))
    count = self.counts_per_call.pop(0) if self.counts_per_call else 0
    return FakeResponse({"data": [{"tweet_count": count}], "meta": {}})

def test_counts_query_excludes_replies_and_retweets_by_default():
  assert counts_query("@Alice") == "from:alice -is:retweet -is:reply"

def test_counts_query_honors_settings():
  assert counts_query("bob", include_replies=True, include_retweets=True) == "from:bob"

def test_prior_week_windows_three_complete_weeks():
  now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)  # Monday
  windows = prior_week_windows(now=now, weeks=3)
  assert len(windows) == 3
  assert windows[-1] == ("2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  assert windows[0] == ("2026-06-15T00:00:00Z", "2026-06-22T00:00:00Z")

def test_estimate_fetch_cost_averages_three_weeks():
  client = XClient(bearer_token="t", http=FakeCountsHttp([10, 20, 30]))
  now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
  out = estimate_fetch_cost(client, "@alice", now=now)
  assert out["handle"] == "alice"
  assert out["avg_tweets_per_week"] == 20.0
  assert out["estimate_query_cost_usd"] == round(3 * COST_PER_COUNTS_ALL, 3)
  expected_fetch = 20 * COST_PER_POST_READ + COST_PER_USER_READ
  assert out["estimated_weekly_fetch_usd"] == round(expected_fetch, 3)
  assert len(out["weeks"]) == 3
  assert [w["tweet_count"] for w in out["weeks"]] == [10, 20, 30]

def test_estimate_uses_counts_all_endpoint():
  http = FakeCountsHttp([1, 2, 3]); client = XClient(bearer_token="t", http=http)
  estimate_fetch_cost(client, "alice", now=datetime(2026, 7, 6, tzinfo=timezone.utc))
  assert all(path == "/tweets/counts/all" for path, _ in http.requests)
