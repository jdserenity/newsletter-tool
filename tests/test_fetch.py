from datetime import datetime, timedelta, timezone
import copy

from app import db
from app.fetch.client import (
  XClient, classify_tweet, COST_PER_POST_READ, COST_PER_USER_READ,
  attach_media, attach_quoted, count_post_reads)
from app.fetch.runner import fetch_account_week, repair_missing_editions, run_weekly_fetch, week_bounds

class FakeResponse:
  def __init__(self, body): self.body = body
  def raise_for_status(self): pass
  def json(self): return self.body

class FakeHttp:
  """Stands in for httpx.Client; records requests and serves canned responses."""
  def __init__(self, tweets, includes=None):
    self.tweets = tweets; self.includes = includes or {}; self.requests = []
  def get(self, path, params=None):
    self.requests.append((path, params or {}))
    if path.startswith("/users/by/username/"):
      return FakeResponse({"data": {"id": "111", "name": "Alice", "username": "alice"}})
    return FakeResponse({"data": copy.deepcopy(self.tweets), "includes": copy.deepcopy(self.includes), "meta": {}})

TWEETS = [
  {"id": "1", "text": "plain post", "created_at": "2026-06-30T10:00:00Z"},
  {"id": "2", "text": "a quote", "created_at": "2026-07-01T10:00:00Z",
   "referenced_tweets": [{"type": "quoted", "id": "999"}]}]

QUOTED_INCLUDES = {"tweets": [{"id": "999", "author_id": "42", "text": "original with pic https://t.co/qpic",
  "attachments": {"media_keys": ["3_999"]}}],
  "media": [{"media_key": "3_999", "type": "photo", "url": "https://pbs.twimg.com/media/q.jpg"}],
  "users": [{"id": "42", "username": "bob"}]}

def test_classify_tweet():
  assert classify_tweet(TWEETS[0]) == "post"
  assert classify_tweet(TWEETS[1]) == "quote"
  assert classify_tweet({"referenced_tweets": [{"type": "retweeted"}]}) == "retweet"
  assert classify_tweet({"referenced_tweets": [{"type": "replied_to"}]}) == "reply"

def test_count_post_reads_includes_expanded_tweets():
  body = {"data": TWEETS, "includes": QUOTED_INCLUDES}
  assert count_post_reads(body) == 3  # ids 1, 2, 999

def test_settings_gate_api_params():
  http = FakeHttp(TWEETS); client = XClient(bearer_token="t", http=http)
  client.get_user_tweets("111", "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
                         include_replies=False, include_retweets=False)
  _, params = http.requests[-1]
  assert params["exclude"] == "replies,retweets"
  assert "referenced_tweets.id" in params["expansions"]
  assert "referenced_tweets.id.attachments.media_keys" in params["expansions"]
  assert "referenced_tweets.id.author_id" in params["expansions"]
  assert params["user.fields"] == "username"
  assert "attachments" in params["tweet.fields"]
  assert "note_tweet" in params["tweet.fields"]
  assert "url" in params["media.fields"]
  client.get_user_tweets("111", "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
                         include_replies=True, include_retweets=True)
  _, params = http.requests[-1]
  assert "exclude" not in params

def test_attach_media_merges_includes():
  tweets = [{"id": "1", "attachments": {"media_keys": ["3_1"]}}]
  includes = {"media": [{"media_key": "3_1", "type": "photo", "url": "https://pbs.twimg.com/media/x.jpg"}]}
  attach_media(tweets, includes)
  assert tweets[0]["media_expanded"][0]["url"] == "https://pbs.twimg.com/media/x.jpg"

def test_attach_quoted_merges_includes():
  tweets = [TWEETS[1].copy()]
  attach_quoted(tweets, QUOTED_INCLUDES)
  assert tweets[0]["quoted_tweet"]["id"] == "999"
  assert tweets[0]["quoted_tweet"]["author_handle"] == "bob"
  assert tweets[0]["quoted_tweet"]["media_expanded"][0]["url"] == "https://pbs.twimg.com/media/q.jpg"

def test_enrich_tweets_attaches_quote_on_fetch():
  http = FakeHttp(TWEETS, QUOTED_INCLUDES); client = XClient(bearer_token="t", http=http)
  tweets, cost, units = client.get_user_tweets("111", "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
                                               include_replies=False, include_retweets=False)
  quote = next(t for t in tweets if t["id"] == "2")
  assert quote["quoted_tweet"]["id"] == "999"
  assert units == 3
  assert abs(cost - 3 * COST_PER_POST_READ) < 1e-9

def test_fetch_records_cost_and_stores_tweets(conn):
  aid = db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS, QUOTED_INCLUDES))
  account = db.get_account(conn, account_id=aid)
  cost = fetch_account_week(conn, client, account, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  expected = COST_PER_USER_READ + 3 * COST_PER_POST_READ  # user + 2 timeline + 1 quoted
  assert abs(cost - expected) < 1e-9
  assert abs(db.cost_for_account(conn, aid) - expected) < 1e-9
  stored = db.tweets_for_week(conn, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  assert len(stored) == 2
  assert {t["kind"] for t in stored} == {"post", "quote"}
  assert db.get_account(conn, account_id=aid)["x_user_id"] == "111"

def test_run_weekly_fetch_builds_newsletters(conn):
  db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS, QUOTED_INCLUDES))
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  results = run_weekly_fetch(conn, client=client, now=now)
  assert len(results) == 1
  editions = db.list_editions(conn)
  assert len(editions) == 1; assert editions[0]["item_count"] == 2

def test_run_weekly_fetch_enqueues_likes_and_starts_drain(conn, monkeypatch):
  started = []
  monkeypatch.setattr("app.user_actions.start_like_drain", lambda path: started.append(path))
  db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS))
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  run_weekly_fetch(conn, client=client, now=now, db_path=":memory:")
  assert db.like_queue_size(conn) == 2
  assert started == [":memory:"]

def test_run_weekly_fetch_builds_newsletter_for_every_account(conn):
  db.add_account(conn, "alice")
  db.add_account(conn, "bob")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS))
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  results = run_weekly_fetch(conn, client=client, now=now)
  assert len(results) == 2
  ws, _ = week_bounds(now)
  for handle in ("alice", "bob"):
    account = db.get_account(conn, handle=handle)
    assert db.edition_for_week(conn, account["id"], ws) is not None

def test_repair_missing_editions_builds_from_stored_tweets(conn):
  aid = db.add_account(conn, "alice")
  db.save_tweets(conn, aid, [{"id": "1", "text": "hi", "created_at": "2026-06-23T12:00:00Z", "kind": "post"}])
  now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
  assert repair_missing_editions(conn, now=now) == ["alice"]
  assert db.edition_for_week(conn, aid, "2026-06-22T00:00:00Z")["item_count"] == 1

def test_repair_missing_editions_skips_when_no_tweets(conn):
  db.add_account(conn, "alice")
  now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
  assert repair_missing_editions(conn, now=now) == []

def test_run_weekly_fetch_raises_if_edition_missing(conn, monkeypatch):
  db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS))
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  monkeypatch.setattr("app.db.save_edition", lambda *a, **k: None)
  import pytest
  with pytest.raises(RuntimeError, match="Newsletter build failed"):
    run_weekly_fetch(conn, client=client, now=now)

def test_week_bounds_is_last_complete_monday_week():
  now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
  start, end = week_bounds(now)
  assert start == "2026-06-22T00:00:00Z"; assert end == "2026-06-29T00:00:00Z"

def test_second_fetch_within_24h_dedupes_post_read_cost(conn):
  aid = db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS))
  account = db.get_account(conn, account_id=aid)
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  week = ("2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  cost1 = fetch_account_week(conn, client, account, *week, now=now)
  account = db.get_account(conn, account_id=aid)
  cost2 = fetch_account_week(conn, client, account, *week, now=now + timedelta(hours=2))
  expected = COST_PER_USER_READ + 2 * COST_PER_POST_READ
  assert abs(cost1 - expected) < 1e-9
  assert abs(cost2) < 1e-9
  assert abs(db.cost_for_account(conn, aid) - expected) < 1e-9

def test_fetch_charges_only_new_tweets_within_24h_window(conn):
  aid = db.add_account(conn, "alice")
  http = FakeHttp(TWEETS)
  client = XClient(bearer_token="t", http=http)
  account = db.get_account(conn, account_id=aid)
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  week = ("2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  fetch_account_week(conn, client, account, *week, now=now)
  account = db.get_account(conn, account_id=aid)
  http.tweets = TWEETS + [{"id": "3", "text": "new", "created_at": "2026-07-02T10:00:00Z"}]
  cost = fetch_account_week(conn, client, account, *week, now=now + timedelta(hours=23))
  assert abs(cost - COST_PER_POST_READ) < 1e-9

def test_fetch_rebills_tweets_after_24h_window(conn):
  aid = db.add_account(conn, "alice")
  client = XClient(bearer_token="t", http=FakeHttp(TWEETS))
  account = db.get_account(conn, account_id=aid)
  now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
  week = ("2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  fetch_account_week(conn, client, account, *week, now=now)
  account = db.get_account(conn, account_id=aid)
  cost = fetch_account_week(conn, client, account, *week, now=now + timedelta(hours=25))
  assert abs(cost - 2 * COST_PER_POST_READ) < 1e-9
