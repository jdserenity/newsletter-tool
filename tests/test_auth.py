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

def test_unauthenticated_home_redirects_to_login(auth_client):
  r = auth_client.get("/", follow_redirects=False)
  assert r.status_code == 303
  assert r.headers["location"] == "/auth/login"

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
  assert 'class="site-actions"' in r.text

def test_add_account_follows_from_owner_session(auth_client, monkeypatch):
  follow_calls = []
  def fake_follow(conn, actions_client, access_token, owner_user_id, account, read_client=None):
    follow_calls.append((access_token, owner_user_id, account["handle"]))
  monkeypatch.setattr("app.main.follow_tracked_account", fake_follow)
  monkeypatch.setattr(auth, "refresh_access_token", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {"access_token": "user-at", "refresh_token": "user-rt"})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "99", "username": "owner", "name": "Owner"})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
  auth_client.post("/accounts", data={"handle": "newvoice"}, follow_redirects=True)
  assert follow_calls == [("user-at", "99", "newvoice")]

def test_home_persists_oauth_and_resumes_like_drain(auth_client, monkeypatch):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {"access_token": "user-at", "refresh_token": "user-rt"})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "99", "username": "owner", "name": "Owner"})
  monkeypatch.setattr(auth, "refresh_access_token", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
  c = db.connect(auth_client.app.state.db_path)
  db.enqueue_like(c, "42")
  started = []
  monkeypatch.setattr("app.main.resume_like_drain_if_needed", lambda p: started.append(p))
  auth_client.get("/")
  row = db.get_oauth_session(c)
  assert row["refresh_token"] == "user-rt"
  assert started == [auth_client.app.state.db_path]

def test_home_retries_pending_follows(auth_client, monkeypatch):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {"access_token": "user-at", "refresh_token": "user-rt"})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "99", "username": "owner", "name": "Owner"})
  monkeypatch.setattr(auth, "refresh_access_token", lambda *a, **k: {
    "access_token": "user-at", "refresh_token": "user-rt", "expires_in": 7200})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
  c = db.connect(auth_client.app.state.db_path)
  aid = db.add_account(c, "pending"); db.set_account_identity(c, aid, "111", "Pending")
  retried = []
  monkeypatch.setattr("app.main.retry_pending_follows", lambda conn, token, owner_id: retried.append(owner_id) or 1)
  monkeypatch.setattr("app.main.resume_like_drain_if_needed", lambda p: None)
  auth_client.get("/")
  assert retried == ["99"]

def test_logout_clears_session(auth_client, monkeypatch):
  monkeypatch.setattr(auth, "exchange_code", lambda *a, **k: {"access_token": "at", "refresh_token": "rt"})
  monkeypatch.setattr(auth, "fetch_me", lambda *a, **k: {"id": "1", "username": "u", "name": "U"})
  login = auth_client.get("/auth/login/start", follow_redirects=False)
  state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
  auth_client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)
  assert auth_client.get("/").status_code == 200
  r = auth_client.post("/auth/logout", follow_redirects=False)
  assert r.status_code == 303
  assert auth_client.get("/", follow_redirects=False).status_code == 303
