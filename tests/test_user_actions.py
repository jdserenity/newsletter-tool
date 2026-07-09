import httpx
import pytest

from app import auth, db
from app.fetch.client import XClient
from app.user_actions import (
  UserActionsClient, drain_like_queue, enqueue_newsletter_likes, follow_tracked_account,
  like_delay_seconds, resolve_target_x_user_id, resume_like_drain_if_needed, retry_pending_follows,
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

def test_like_delay_seconds_is_base_plus_or_minus_jitter(monkeypatch):
  monkeypatch.setattr("app.user_actions.random.choice", lambda xs: 1)
  monkeypatch.setattr("app.user_actions.random.randint", lambda a, b: 12)
  assert like_delay_seconds() == 72
  monkeypatch.setattr("app.user_actions.random.choice", lambda xs: -1)
  assert like_delay_seconds() == 48

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
  assert follow_tracked_account(conn, UserActionsClient(http=http), None, "99", db.get_account(conn, account_id=aid)) is False
  assert http.posts == []

def test_follow_tracked_account_skips_already_followed(conn):
  aid = db.add_account(conn, "alice"); db.set_account_identity(conn, aid, "111", "Alice")
  db.mark_account_followed(conn, aid)
  http = FakeHttp()
  assert follow_tracked_account(conn, UserActionsClient(http=http), "tok", "99", db.get_account(conn, account_id=aid)) is True
  assert http.posts == []

def test_follow_tracked_account_posts_follow(conn):
  aid = db.add_account(conn, "alice"); db.set_account_identity(conn, aid, "111", "Alice")
  http = FakeHttp(); client = UserActionsClient(http=http)
  follow_tracked_account(conn, client, "tok", "99", db.get_account(conn, account_id=aid))
  assert http.posts[0][0] == "/users/99/following"
  assert db.get_account(conn, account_id=aid)["followed_at"] is not None

def test_follow_tracked_account_does_not_clear_existing_followed_at(conn):
  aid = db.add_account(conn, "alice"); db.set_account_identity(conn, aid, "111", "Alice")
  db.mark_account_followed(conn, aid)
  first = db.get_account(conn, account_id=aid)["followed_at"]
  follow_tracked_account(conn, UserActionsClient(http=FakeHttp()), "tok", "99", db.get_account(conn, account_id=aid))
  assert db.get_account(conn, account_id=aid)["followed_at"] == first

def test_retry_pending_follows_follows_unfollowed_accounts(conn):
  a1 = db.add_account(conn, "alice"); db.set_account_identity(conn, a1, "111", "Alice")
  a2 = db.add_account(conn, "bob"); db.set_account_identity(conn, a2, "222", "Bob")
  db.mark_account_followed(conn, a1)
  http = FakeHttp(); client = UserActionsClient(http=http)
  followed = retry_pending_follows(conn, "tok", "99", actions_client=client, read_client=XClient(bearer_token="t", http=http))
  assert followed == 1
  assert db.get_account(conn, account_id=a2)["followed_at"] is not None
  assert len(http.posts) == 1

def test_enqueue_newsletter_likes_skips_liked_and_queued(conn):
  db.mark_tweet_liked(conn, "1"); db.enqueue_like(conn, "2")
  items = [{"tweet_id": "1"}, {"tweet_id": "2"}, {"tweet_id": "3"}]
  assert enqueue_newsletter_likes(conn, items) == 1
  assert db.like_queue_size(conn) == 2
  assert db.peek_like_queue(conn) == "2"

def test_enqueue_newsletter_likes_noop_without_items(conn):
  assert enqueue_newsletter_likes(conn, []) == 0

def test_drain_like_queue_likes_first_immediately_then_waits(conn, monkeypatch):
  db.save_oauth_session(conn, "99", "at", "rt")
  db.enqueue_like(conn, "42"); db.enqueue_like(conn, "43")
  monkeypatch.setattr("app.auth.refresh_access_token", lambda *a, **k: {"access_token": "at", "refresh_token": "rt"})
  monkeypatch.setattr("app.user_actions.like_delay_seconds", lambda: 53)
  sleeps = []
  http = FakeHttp()
  liked = drain_like_queue(conn, actions_client=UserActionsClient(http=http), sleep=lambda s: sleeps.append(s))
  assert liked == 2
  assert [p[2]["tweet_id"] for p in http.posts] == ["42", "43"]
  assert sleeps == [53]

def test_drain_like_queue_stops_without_oauth(conn):
  db.enqueue_like(conn, "42")
  assert drain_like_queue(conn, auth_config=auth.AuthConfig.from_env(enabled=False)) == 0
  assert db.like_queue_size(conn) == 1

def test_drain_like_queue_skips_already_liked_still_in_queue(conn, monkeypatch):
  db.save_oauth_session(conn, "99", "at", "rt")
  db.mark_tweet_liked(conn, "42"); db.enqueue_like(conn, "42"); db.enqueue_like(conn, "43")
  monkeypatch.setattr("app.auth.refresh_access_token", lambda *a, **k: {"access_token": "at", "refresh_token": "rt"})
  http = FakeHttp()
  liked = drain_like_queue(conn, actions_client=UserActionsClient(http=http), sleep=lambda s: None)
  assert liked == 1
  assert [p[2]["tweet_id"] for p in http.posts] == ["43"]
  assert db.like_queue_size(conn) == 0

def test_resume_like_drain_if_needed_starts_when_queue_nonempty(tmp_path, monkeypatch):
  path = str(tmp_path / "resume.db")
  c = db.connect(path); db.enqueue_like(c, "99"); c.close()
  started = []
  monkeypatch.setattr("app.user_actions.start_like_drain", lambda p: started.append(p))
  resume_like_drain_if_needed(path)
  assert started == [path]

def test_persist_session_oauth_writes_db(conn):
  class Req:
    session = {
      auth.SESSION_USER_ID: "99", auth.SESSION_ACCESS: "at", auth.SESSION_REFRESH: "rt",
    }
  auth.persist_session_oauth(conn, Req())
  row = db.get_oauth_session(conn)
  assert row["x_user_id"] == "99"
  assert row["access_token"] == "at"
  assert row["refresh_token"] == "rt"

def test_persist_session_oauth_skips_incomplete_session(conn):
  class Req:
    session = {auth.SESSION_ACCESS: "at"}
  auth.persist_session_oauth(conn, Req())
  assert db.get_oauth_session(conn) is None

def test_owner_access_token_refreshes_from_persisted_session(conn, monkeypatch):
  class Req:
    session = {
      auth.SESSION_USER_ID: "99", auth.SESSION_ACCESS: "old-at", auth.SESSION_REFRESH: "rt",
    }
  monkeypatch.setattr(auth, "refresh_access_token", lambda *a, **k: {
    "access_token": "new-at", "refresh_token": "rt", "expires_in": 7200})
  cfg = auth.AuthConfig.from_env(enabled=True)
  cfg.client_id = "cid"; cfg.client_secret = "sec"
  token, uid = auth.owner_access_token(conn, Req(), cfg)
  assert token == "new-at"; assert uid == "99"

def test_resume_like_drain_if_needed_noop_when_queue_empty(tmp_path, monkeypatch):
  path = str(tmp_path / "empty.db")
  db.connect(path).close()
  started = []
  monkeypatch.setattr("app.user_actions.start_like_drain", lambda p: started.append(p))
  resume_like_drain_if_needed(path)
  assert started == []

def test_get_valid_access_token_refreshes_and_persists(conn, monkeypatch):
  # No expires_at → treat as unknown and refresh once.
  db.save_oauth_session(conn, "99", "old-at", "rt")
  monkeypatch.setattr(auth, "refresh_access_token", lambda http, cid, sec, rt: {
    "access_token": "new-at", "refresh_token": "new-rt", "expires_in": 7200})
  cfg = auth.AuthConfig.from_env(enabled=True)
  cfg.client_id = "cid"; cfg.client_secret = "sec"
  token, uid = auth.get_valid_access_token(conn, cfg)
  assert token == "new-at"; assert uid == "99"
  row = db.get_oauth_session(conn)
  assert row["access_token"] == "new-at"; assert row["refresh_token"] == "new-rt"
  assert row["expires_at"]  # stored so the next call can skip the network

def test_get_valid_access_token_reuses_unexpired_token(conn, monkeypatch):
  from datetime import datetime, timedelta, timezone
  exp = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
  db.save_oauth_session(conn, "99", "cached-at", "rt", expires_at=exp)
  def boom(*a, **k): raise AssertionError("should not refresh while token is still valid")
  monkeypatch.setattr(auth, "refresh_access_token", boom)
  cfg = auth.AuthConfig.from_env(enabled=True)
  cfg.client_id = "cid"; cfg.client_secret = "sec"
  token, uid = auth.get_valid_access_token(conn, cfg)
  assert token == "cached-at"; assert uid == "99"

def test_get_valid_access_token_refreshes_when_expired(conn, monkeypatch):
  from datetime import datetime, timedelta, timezone
  exp = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
  db.save_oauth_session(conn, "99", "old-at", "rt", expires_at=exp)
  monkeypatch.setattr(auth, "refresh_access_token", lambda *a, **k: {
    "access_token": "new-at", "refresh_token": "new-rt", "expires_in": 7200})
  cfg = auth.AuthConfig.from_env(enabled=True)
  cfg.client_id = "cid"; cfg.client_secret = "sec"
  token, uid = auth.get_valid_access_token(conn, cfg)
  assert token == "new-at"; assert uid == "99"

def test_persist_session_oauth_does_not_clobber_existing_db_tokens(conn):
  from datetime import datetime, timedelta, timezone
  exp = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
  db.save_oauth_session(conn, "99", "db-at", "db-rt", expires_at=exp)
  class Req:
    session = {
      auth.SESSION_USER_ID: "99", auth.SESSION_ACCESS: "session-at", auth.SESSION_REFRESH: "session-rt",
    }
  assert auth.persist_session_oauth(conn, Req()) is False
  row = db.get_oauth_session(conn)
  assert row["access_token"] == "db-at"
  assert row["refresh_token"] == "db-rt"
  assert row["expires_at"] == exp

def test_run_owner_maintenance_retries_pending_follows(tmp_path, monkeypatch):
  from datetime import datetime, timedelta, timezone
  from app.user_actions import run_owner_maintenance
  path = str(tmp_path / "maint.db")
  c = db.connect(path)
  aid = db.add_account(c, "pending"); db.set_account_identity(c, aid, "111", "Pending")
  exp = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
  db.save_oauth_session(c, "99", "at", "rt", expires_at=exp); c.close()
  retried = []
  monkeypatch.setattr("app.user_actions.retry_pending_follows",
    lambda conn, token, owner_id, **k: retried.append((token, owner_id)) or 1)
  cfg = auth.AuthConfig.from_env(enabled=True)
  cfg.client_id = "cid"; cfg.client_secret = "sec"
  run_owner_maintenance(path, cfg)
  assert retried == [("at", "99")]
