import httpx
import pytest

from app import auth, db
from app.fetch.client import XClient
from app.user_actions import UserActionsClient, follow_tracked_account, like_digest_items, resolve_target_x_user_id

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

def test_like_digest_items_skips_already_liked(conn):
  db.save_oauth_session(conn, "99", "at", "rt")
  db.mark_tweet_liked(conn, "1")
  http = FakeHttp()
  items = [{"tweet_id": "1"}, {"tweet_id": "2"}]
  liked = like_digest_items(conn, UserActionsClient(http=http), "at", "99", items)
  assert liked == 1
  assert len(http.posts) == 1
  assert http.posts[0][2]["tweet_id"] == "2"
  assert db.is_tweet_liked(conn, "2")

def test_like_digest_items_noop_without_items(conn):
  db.save_oauth_session(conn, "99", "at", "rt")
  http = FakeHttp()
  assert like_digest_items(conn, UserActionsClient(http=http), "at", "99", []) == 0

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
