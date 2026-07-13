import hashlib
import base64
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.main import create_app

def test_pkce_challenge_is_s256_of_verifier():
  verifier, challenge = auth.make_pkce_pair()
  expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
  assert challenge == expected
  assert 43 <= len(verifier) <= 128

def test_authorize_url_includes_required_params():
  url = auth.build_authorize_url(
    client_id="cid", redirect_uri="http://localhost/auth/callback",
    state="st", code_challenge="ch", scopes=["users.read", "offline.access"])
  assert "x.com/i/oauth2/authorize" in url
  assert "client_id=cid" in url
  assert "code_challenge_method=S256" in url
  assert "scope=users.read+offline.access" in url or "scope=users.read%20offline.access" in url

def test_exchange_code_posts_to_token_endpoint():
  transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
    "token_type": "bearer", "access_token": "at", "refresh_token": "rt", "expires_in": 7200}))
  client = httpx.Client(transport=transport)
  tok = auth.exchange_code(client, client_id="cid", client_secret="sec",
    redirect_uri="http://localhost/cb", code="code123", code_verifier="verifier")
  assert tok["access_token"] == "at"
  assert tok["refresh_token"] == "rt"

def test_fetch_me_returns_user_fields():
  transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
    "data": {"id": "42", "username": "alice", "name": "Alice"}}))
  me = auth.fetch_me(httpx.Client(transport=transport), "at")
  assert me == {"id": "42", "username": "alice", "name": "Alice"}

@pytest.fixture
def auth_client(tmp_path, monkeypatch):
  monkeypatch.setenv("X_CLIENT_ID", "test-client-id")
  monkeypatch.setenv("X_CLIENT_SECRET", "test-client-secret")
  monkeypatch.setenv("X_OAUTH_CALLBACK_URL", "http://testserver/auth/callback")
  monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
  app = create_app(db_path=str(tmp_path / "auth.db"), with_scheduler=False, auth_enabled=True)
  with TestClient(app) as c:
    yield c

def test_unauthenticated_home_shows_landing(auth_client):
  r = auth_client.get("/", follow_redirects=False)
  assert r.status_code == 200
  assert "More Mentally Stable X Experience" in r.text
  assert "landing" in r.text
  assert 'href="https://x.com/diamaribuilds"' in r.text
  assert 'href="https://x.com/gdpwrultd"' in r.text
  assert "Created by" in r.text
  assert "J.D. Diamari" in r.text
  assert "Good Power Unlimited, So That Evil May Be a Solved Problem" in r.text
  assert "Enter now" in r.text
  assert "/billing/checkout" in r.text or "/auth/login/start" in r.text
  # Pricing: API costs + 1USD service fee.
  assert "API Costs + 1USD service fee" in r.text
  assert "Extremely reasonable" in r.text
  # Signed-out visitors must not see the app carousel chrome.
  assert 'class="carousel"' not in r.text
  assert "Signed in as" not in r.text

def test_authenticated_home_shows_app_not_landing(auth_client, monkeypatch):
  _login_auth_client(auth_client, monkeypatch)
  r = auth_client.get("/", follow_redirects=False)
  assert r.status_code == 200
  assert 'class="carousel"' in r.text or 'id="carousel"' in r.text or "Signed in as" in r.text
  assert "So That Evil May Be a Solved Problem" not in r.text
  assert 'class="landing"' not in r.text

def test_settings_still_requires_login(auth_client):
  r = auth_client.get("/settings", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/auth/login"

def test_rss_feed_is_public_without_login(auth_client):
  # RSS readers have no session cookie — feeds must not redirect to /auth/login.
  c = db.connect(auth_client.app.state.db_path)
  aid = db.add_account(c, "alice")
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
    [{"tweet_id": "1", "kind": "post", "text": "hello rss", "created_at": "2026-06-30T10:00:00Z",
      "url": "https://x.com/alice/status/1", "likes": 0, "reposts": 0}], 0.01)
  r = auth_client.get(f"/feeds/{aid}.xml", follow_redirects=False)
  assert r.status_code == 200
  assert "application/rss+xml" in r.headers["content-type"]
  assert "<rss" in r.text
  assert "hello rss" in r.text
  assert "/auth/login" not in r.headers.get("location", "")

def test_edition_page_is_public_without_login(auth_client):
  # Feed item links point at /editions/{id}; those deep links must open without a cookie.
  c = db.connect(auth_client.app.state.db_path)
  aid = db.add_account(c, "alice")
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
    [{"tweet_id": "1", "kind": "post", "text": "hello edition", "created_at": "2026-06-30T10:00:00Z",
      "url": "https://x.com/alice/status/1", "likes": 0, "reposts": 0}], 0.01)
  eid = db.list_editions(c)[0]["id"]
  r = auth_client.get(f"/editions/{eid}", follow_redirects=False)
  assert r.status_code == 200
  assert "hello edition" in r.text
  assert 'class="mark-check' not in r.text  # mark-read UI only when signed in

def test_login_page_is_public(auth_client):
  r = auth_client.get("/auth/login")
  assert r.status_code == 200
  assert "Sign in with X" in r.text

def test_login_start_redirects_to_x(auth_client):
  r = auth_client.get("/auth/login/start", follow_redirects=False)
  assert r.status_code == 303
  loc = r.headers["location"]
  assert "x.com/i/oauth2/authorize" in loc
  assert "client_id=test-client-id" in loc

def test_callback_exchanges_code_and_sets_session(auth_client, monkeypatch):
  def fake_exchange(http, client_id, client_secret, redirect_uri, code, code_verifier):
    return {"access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200}
  def fake_me(http, access_token):
    return {"id": "99", "username": "owner", "name": "Owner"}
  monkeypatch.setattr(auth, "exchange_code", fake_exchange)
  monkeypatch.setattr(auth, "fetch_me", fake_me)
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  qs = parse_qs(urlparse(login.headers["location"]).query)
  state = qs["state"][0]
  r = auth_client.get("/auth/callback?code=abc&state=bad", follow_redirects=False)
  assert r.status_code == 400
  r = auth_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/"
  c = db.connect(auth_client.app.state.db_path)
  row = db.get_oauth_session(c)
  assert row["x_user_id"] == "99"
  assert row["access_token"] == "user-at"
  assert row["refresh_token"] == "user-rt"
  r = auth_client.get("/")
  assert r.status_code == 200
  assert "owner" in r.text.lower() or "@owner" in r.text
  assert 'class="site-user"' in r.text
  assert "Signed in as" in r.text
  assert 'href="/settings"' in r.text
  assert ">Settings</a>" in r.text
  assert 'class="site-actions"' in r.text
  # On settings, the same control becomes Home so you can leave the page.
  r = auth_client.get("/settings")
  assert r.status_code == 200
  assert 'href="/"' in r.text
  assert ">Home</a>" in r.text
  assert ">Settings</a>" not in r.text

def test_add_account_does_not_auto_follow(auth_client, monkeypatch):
  monkeypatch.setattr(auth, "refresh_access_token", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {"access_token": "user-at", "refresh_token": "user-rt"})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "99", "username": "owner", "name": "Owner"})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
  auth_client.post("/accounts", data={"handle": "newvoice"}, follow_redirects=True)
  c = db.connect(auth_client.app.state.db_path)
  account = db.get_account(c, handle="newvoice")
  assert account is not None
  assert account.get("followed_at") is None

def test_home_persists_oauth_session(auth_client, monkeypatch):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "99", "username": "owner", "name": "Owner"})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
  auth_client.get("/")
  row = db.get_oauth_session(db.connect(auth_client.app.state.db_path))
  assert row["refresh_token"] == "user-rt"
  assert row["access_token"] == "user-at"

def _login_auth_client(auth_client, monkeypatch):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "99", "username": "owner", "name": "Owner"})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)

def test_like_tweet_calls_x_when_auth_enabled(auth_client, monkeypatch):
  x_calls = []
  def fake_like(access_token, owner_user_id, tweet_id, actions_client=None):
    x_calls.append((access_token, owner_user_id, tweet_id))
    return {"data": {"liked": True}}
  monkeypatch.setattr("app.main.like_tweet_on_x", fake_like)
  _login_auth_client(auth_client, monkeypatch)
  c = db.connect(auth_client.app.state.db_path)
  aid = db.add_account(c, "alice")
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
    [{"tweet_id": "1", "kind": "post", "text": "hello", "created_at": "2026-06-30T10:00:00Z",
      "url": "https://x.com/alice/status/1", "likes": 0, "reposts": 0}], 0.01)
  r = auth_client.post("/tweets/1/like", headers={"Accept": "application/json"})
  assert r.status_code == 200
  assert r.json()["liked_on_x"] is True
  assert x_calls == [("user-at", "99", "1")]
  assert db.is_tweet_liked(c, "1")

def test_like_tweet_x_failure_does_not_save_local(auth_client, monkeypatch):
  from app.user_actions import LikeActionError
  monkeypatch.setattr("app.main.like_tweet_on_x",
    lambda *a, **k: (_ for _ in ()).throw(LikeActionError("X like failed (403)")))
  _login_auth_client(auth_client, monkeypatch)
  c = db.connect(auth_client.app.state.db_path)
  aid = db.add_account(c, "alice")
  db.save_edition(c, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z",
    [{"tweet_id": "1", "kind": "post", "text": "hello", "created_at": "2026-06-30T10:00:00Z",
      "url": "https://x.com/alice/status/1", "likes": 0, "reposts": 0}], 0.01)
  r = auth_client.post("/tweets/1/like", headers={"Accept": "application/json"})
  assert r.status_code == 502
  assert "X like failed" in r.json()["detail"]
  assert not db.is_tweet_liked(c, "1")

def test_logout_clears_session(auth_client, monkeypatch):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {"access_token": "at", "refresh_token": "rt"})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "1", "username": "u", "name": "U"})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)
  assert auth_client.get("/").status_code == 200
  r = auth_client.post("/auth/logout", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/"
  # After logout, `/` is the public landing page again (not a redirect to login).
  home = auth_client.get("/", follow_redirects=False)
  assert home.status_code == 200
  assert "landing" in home.text
  assert "Signed in as" not in home.text
