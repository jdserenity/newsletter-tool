from app import db
from app.fetch.client import XClient, classify_tweet, COST_PER_POST_READ, COST_PER_USER_READ
from app.fetch.runner import fetch_account_week, run_weekly_fetch, week_bounds
from datetime import datetime, timezone

class FakeResponse:
  def __init__(self, body): self.body = body
  def raise_for_status(self): pass
  def json(self): return self.body

class FakeHttp:
  """Stands in for httpx.Client; records requests and serves canned responses."""
  def __init__(self, tweets):
    self.tweets = tweets; self.requests = []
  def get(self, path, params=None):
    self.requests.append((path, params or {}))
    if path.startswith("/users/by/username/"):
      return FakeResponse({"data": {"id": "111", "name": "Alice", "username": "alice"}})
    return FakeResponse({"data": self.tweets, "meta": {}})

TWEETS = [
  {"id": "1", "text": "plain post", "created_at": "2026-06-30T10:00:00Z"},
  {"id": "2", "text": "a quote", "created_at": "2026-07-01T10:00:00Z",
   "referenced_tweets": [{"type": "quoted", "id": "999"}]}]

def test_classify_tweet():
  assert classify_tweet(TWEETS[0]) == "post"
  assert classify_tweet(TWEETS[1]) == "quote"
  assert classify_tweet({"referenced_tweets": [{"type": "retweeted"}]}) == "retweet"
  assert classify_tweet({"referenced_tweets": [{"type": "replied_to"}]}) == "reply"

def test_settings_gate_api_params():
  http = FakeHttp(TWEETS); client = XClient(bearer_token="t", http=http)
  client.get_user_tweets("111", "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
                         include_replies=False, include_retweets=False)
  _, params = http.requests[-1]
  assert params["exclude"] == "replies,retweets"
  client.get_user_tweets("111", "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
                         include_replies=True, include_retweets=True)
  _, params = http.requests[-1]
  assert "exclude" not in params

def test_fetch_records_cost_and_stores_tweets(conn):
  aid = db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS))
  account = db.get_account(conn, account_id=aid)
  cost = fetch_account_week(conn, client, account, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  expected = COST_PER_USER_READ + 2 * COST_PER_POST_READ  # 1 user lookup + 2 post reads
  assert abs(cost - expected) < 1e-9
  assert abs(db.cost_for_account(conn, aid) - expected) < 1e-9
  stored = db.tweets_for_week(conn, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  assert len(stored) == 2
  assert {t["kind"] for t in stored} == {"post", "quote"}
  assert db.get_account(conn, account_id=aid)["x_user_id"] == "111"  # cached, not re-fetched next week

def test_run_weekly_fetch_builds_digests(conn):
  db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS))
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)  # week fetched: Jun 29 - Jul 6, covers TWEETS
  results = run_weekly_fetch(conn, client=client, now=now)
  assert len(results) == 1
  digests = db.list_digests(conn)
  assert len(digests) == 1; assert digests[0]["item_count"] == 2  # post + quote (quotes on on default)

def test_run_weekly_fetch_likes_digest_items_when_oauth_present(conn, monkeypatch):
  from app.user_actions import UserActionsClient
  db.add_account(conn, "alice")
  db.save_oauth_session(conn, "owner", "at", "rt")
  monkeypatch.setattr("app.auth.refresh_access_token", lambda *a, **k: {"access_token": "at", "refresh_token": "rt"})
  http = FakeHttp(TWEETS); client = XClient(bearer_token="t", http=http)
  class ActionsFakeHttp:
    def __init__(self): self.posts = []
    def post(self, path, headers=None, json=None):
      self.posts.append((path, headers or {}, json or {}))
      return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"data": {"liked": True}}})()
  actions_http = ActionsFakeHttp()
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  run_weekly_fetch(conn, client=client, now=now, actions_client=UserActionsClient(http=actions_http))
  liked_ids = {p[2]["tweet_id"] for p in actions_http.posts}
  assert liked_ids == {"1", "2"}
  assert db.is_tweet_liked(conn, "1") and db.is_tweet_liked(conn, "2")

def test_week_bounds_is_last_complete_monday_week():
  now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)  # a Sunday
  start, end = week_bounds(now)
  assert start == "2026-06-22T00:00:00Z"; assert end == "2026-06-29T00:00:00Z"
