import httpx
import pytest
from datetime import datetime, timezone

from app import auth, db
from app.fetch.client import XClient
from app.user_actions import (
  UserActionsClient, enqueue_digest_likes, follow_tracked_account, like_delay_seconds,
  next_like_deadline, process_like_queue, resolve_target_x_user_id,
)

class FakeResponse:
  def __init__(self, status_code=200, body=None):
    self.status_code = status_code; self.body = body or {}
  def raise_for_status(self):
    if self.status_code >= 400: raise httpx.HTTPStatusError("err", request=None, response=self)
  def json(self): return self.body

class FakeHttp:
  def __init__(self, responses=None):
    self.responses = responses or {}; self.posts = []
  def post(self, path, headers=None, json=None):
    self.posts.append((path, headers or {}, json or {}))
    key = (path, json.get("target_user_id") if json else json.get("tweet_id") if json else None)
    if path in self.responses: return self.responses[path]
    if json and json.get("tweet_id") and "likes" in path: return FakeResponse(200, {"data": {"liked": True}})
    if json and json.get("target_user_id") and "following" in path: return FakeResponse(200, {"data": {"following": True}})
    return FakeResponse(200, {"data": {}})

def test_follow_user_posts_target_id():
  http = FakeHttp(); client = UserActionsClient(http=http)
  client.follow_user("token", "99", "111")
  assert http.posts == [("/users/99/following", {"Authorization": "Bearer token", "Content-Type": "application/json"}, {"target_user_id": "111"})]

def test_like_tweet_posts_tweet_id():
  http = FakeHttp(); client = UserActionsClient(http=http)
  client.like_tweet("token", "99", "42")
  assert http.posts[0] == ("/users/99/likes", {"Authorization": "Bearer token", "Content-Type": "application/json"}, {"tweet_id": "42"})

def test_like_delay_seconds_is_base_plus_jitter(monkeypatch):
  monkeypatch.setattr("app.user_actions.random.randint", lambda a, b: 7)
  assert like_delay_seconds() == 67

def test_next_like_deadline_adds_delay(monkeypatch):
  monkeypatch.setattr("app.user_actions.like_delay_seconds", lambda: 80)
  start = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
  end = next_like_deadline(start)
  assert int((end - start).total_seconds()) == 80

def test_resolve_target_x_user_id_uses_cached_id(conn):
  aid = db.add_account(conn, "alice"); db.set_account_identity(conn, aid, "111", "Alice")
  account = db.get_account(conn, account_id=aid)
  assert resolve_target_x_user_id(conn, XClient(bearer_token="t", http=FakeHttp()), account) == "111"

def test_resolve_target_x_user_id_looks_up_handle(conn):
  class LookupHttp:
    def get(self, path, params=None):
      return FakeResponse(200, {"data": {"id": "222", "name": "Bob", "username": "bob"}})
  aid = db.add_account(conn, "bob")
  account = db.get_account(conn, account_id=aid)
  xid = resolve_target_x_user_id(conn, XClient(bearer_token="t", http=LookupHttp()), account)
  assert xid == "222"
  assert db.get_account(conn, account_id=aid)["x_user_id"] == "222"

def test_follow_tracked_account_skips_without_token(conn):
  aid = db.add_account(conn, "alice"); db.set_account_identity(conn, aid, "111", "Alice")
  http = FakeHttp()
  follow_tracked_account(conn, UserActionsClient(http=http), None, "99", db.get_account(conn, account_id=aid))
  assert http.posts == []

def test_follow_tracked_account_posts_follow(conn):
  aid = db.add_account(conn, "alice"); db.set_account_identity(conn, aid, "111", "Alice")
  http = FakeHttp(); client = UserActionsClient(http=http)
  follow_tracked_account(conn, client, "tok", "99", db.get_account(conn, account_id=aid))
  assert http.posts[0][0] == "/users/99/following"

def test_enqueue_digest_likes_skips_liked_and_queued(conn):
  db.mark_tweet_liked(conn, "1"); db.enqueue_like(conn, "2")
  items = [{"tweet_id": "1"}, {"tweet_id": "2"}, {"tweet_id": "3"}]
  assert enqueue_digest_likes(conn, items) == 1
  assert db.like_queue_size(conn) == 2
  assert db.peek_like_queue(conn) == "2"

def test_enqueue_digest_likes_noop_without_items(conn):
  assert enqueue_digest_likes(conn, []) == 0

def test_process_like_queue_waits_for_pacing(conn, monkeypatch):
  db.save_oauth_session(conn, "99", "at", "rt")
  db.enqueue_like(conn, "42")
  future = datetime(2026, 7, 5, 13, 0, tzinfo=timezone.utc)
  db.set_next_like_at(conn, "2026-07-05T13:00:00Z")
  now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
  monkeypatch.setattr("app.auth.refresh_access_token", lambda *a, **k: {"access_token": "at", "refresh_token": "rt"})
  http = FakeHttp()
  assert process_like_queue(conn, actions_client=UserActionsClient(http=http), now=now) is False
  assert http.posts == []
  assert db.like_queue_size(conn) == 1

def test_process_like_queue_likes_one_and_sets_pacing(conn, monkeypatch):
  db.save_oauth_session(conn, "99", "at", "rt")
  db.enqueue_like(conn, "42"); db.enqueue_like(conn, "43")
  monkeypatch.setattr("app.auth.refresh_access_token", lambda *a, **k: {"access_token": "at", "refresh_token": "rt"})
  monkeypatch.setattr("app.user_actions.like_delay_seconds", lambda: 73)
  now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
  http = FakeHttp()
  assert process_like_queue(conn, actions_client=UserActionsClient(http=http), now=now) is True
  assert http.posts[0][2]["tweet_id"] == "42"
  assert db.is_tweet_liked(conn, "42")
  assert db.like_queue_size(conn) == 1
  assert db.get_next_like_at(conn) == "2026-07-05T12:01:13Z"

def test_get_valid_access_token_refreshes_and_persists(conn, monkeypatch):
  db.save_oauth_session(conn, "99", "old-at", "rt")
  monkeypatch.setattr(auth, "refresh_access_token", lambda http, cid, sec, rt: {
    "access_token": "new-at", "refresh_token": "new-rt", "expires_in": 7200})
  cfg = auth.AuthConfig.from_env(enabled=True)
  cfg.client_id = "cid"; cfg.client_secret = "sec"
  token, uid = auth.get_valid_access_token(conn, cfg)
  assert token == "new-at"; assert uid == "99"
  row = db.get_oauth_session(conn)
  assert row["access_token"] == "new-at"; assert row["refresh_token"] == "new-rt"
