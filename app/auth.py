"""X OAuth 2.0 (PKCE) user authentication for the web app."""
import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app import db

AUTH_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
USER_ME_URL = "https://api.x.com/2/users/me"
# Refresh a bit before X says the access token dies so we don't use one mid-request.
TOKEN_REFRESH_SKEW_SECONDS = 120

# Scopes for sign-in. like.write / follows.write were for removed auto actions.
DEFAULT_SCOPES = ("users.read", "tweet.read", "offline.access")

SESSION_ACCESS = "access_token"
SESSION_REFRESH = "refresh_token"
SESSION_USER_ID = "x_user_id"
SESSION_USERNAME = "username"
SESSION_NAME = "name"
SESSION_OAUTH_STATE = "oauth_state"
SESSION_CODE_VERIFIER = "code_verifier"

class AuthConfig:
  def __init__(self, enabled, client_id, client_secret, callback_url, session_secret, scopes=None, http=None):
    self.enabled = enabled
    self.client_id = client_id
    self.client_secret = client_secret
    self.callback_url = callback_url
    self.session_secret = session_secret
    self.scopes = scopes or DEFAULT_SCOPES
    self.http = http

  @classmethod
  def from_env(cls, enabled=True, http=None):
    scopes_env = os.environ.get("X_OAUTH_SCOPES", "").strip()
    scopes = tuple(s for s in scopes_env.split() if s) or DEFAULT_SCOPES
    return cls(
      enabled=enabled,
      client_id=os.environ.get("X_CLIENT_ID", ""),
      client_secret=os.environ.get("X_CLIENT_SECRET", ""),
      callback_url=os.environ.get("X_OAUTH_CALLBACK_URL", "http://127.0.0.1:8000/auth/callback"),
      session_secret=os.environ.get("SESSION_SECRET", ""),
      scopes=scopes,
      http=http,
    )

  def configured(self):
    return bool(self.client_id and self.client_secret and self.session_secret)

def make_pkce_pair():
  verifier = secrets.token_urlsafe(64)[:128]
  challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
  return verifier, challenge

def build_authorize_url(client_id, redirect_uri, state, code_challenge, scopes):
  q = urlencode({
    "response_type": "code",
    "client_id": client_id,
    "redirect_uri": redirect_uri,
    "scope": " ".join(scopes),
    "state": state,
    "code_challenge": code_challenge,
    "code_challenge_method": "S256",
  })
  return f"{AUTH_URL}?{q}"

def _token_request(http, data, client_id, client_secret):
  auth = (client_id, client_secret) if client_secret else None
  r = http.post(TOKEN_URL, data=data, auth=auth,
    headers={"Content-Type": "application/x-www-form-urlencoded"})
  r.raise_for_status()
  return r.json()

def exchange_code(http, client_id, client_secret, redirect_uri, code, code_verifier):
  return _token_request(http, {
    "code": code, "grant_type": "authorization_code",
    "client_id": client_id, "redirect_uri": redirect_uri, "code_verifier": code_verifier,
  }, client_id, client_secret)

def refresh_access_token(http, client_id, client_secret, refresh_token):
  return _token_request(http, {
    "refresh_token": refresh_token, "grant_type": "refresh_token", "client_id": client_id,
  }, client_id, client_secret)

def expires_at_from_token(token, now=None):
  """ISO UTC expiry from a token response's expires_in seconds, or None if missing."""
  expires_in = token.get("expires_in")
  if expires_in is None: return None
  now = now or datetime.now(timezone.utc)
  return (now + timedelta(seconds=int(expires_in))).strftime("%Y-%m-%dT%H:%M:%SZ")

def _parse_expires_at(value):
  if not value: return None
  s = value.strip()
  if s.endswith("Z"): s = s[:-1] + "+00:00"
  return datetime.fromisoformat(s).astimezone(timezone.utc)

def access_token_usable(row, now=None, skew_seconds=TOKEN_REFRESH_SKEW_SECONDS):
  """True when the stored access token is present and not near expiry."""
  if not row or not row.get("access_token"): return False
  try: exp = _parse_expires_at(row.get("expires_at"))
  except ValueError: return False
  if exp is None: return False  # unknown expiry → refresh when a refresh_token exists
  now = now or datetime.now(timezone.utc)
  return exp > now + timedelta(seconds=skew_seconds)

def fetch_me(http, access_token):
  r = http.get(USER_ME_URL, headers={"Authorization": f"Bearer {access_token}"},
    params={"user.fields": "name,username"})
  r.raise_for_status()
  return r.json()["data"]

def session_user(request):
  if not request.session.get(SESSION_ACCESS): return None
  return {
    "x_user_id": request.session.get(SESSION_USER_ID),
    "username": request.session.get(SESSION_USERNAME),
    "name": request.session.get(SESSION_NAME),
  }

def clear_session(request):
  for key in (SESSION_ACCESS, SESSION_REFRESH, SESSION_USER_ID, SESSION_USERNAME, SESSION_NAME,
              SESSION_OAUTH_STATE, SESSION_CODE_VERIFIER):
    request.session.pop(key, None)

def store_user_session(request, token, me):
  request.session[SESSION_ACCESS] = token["access_token"]
  if token.get("refresh_token"): request.session[SESSION_REFRESH] = token["refresh_token"]
  request.session[SESSION_USER_ID] = me["id"]
  request.session[SESSION_USERNAME] = me["username"]
  request.session[SESSION_NAME] = me.get("name", "")

def persist_session_oauth(conn, request):
  """Bootstrap browser session tokens into the DB for background jobs.

  Does not overwrite an existing DB row: the browser session is only a first-time
  source. Clobbering would wipe a refreshed access token / expires_at and force
  needless network refreshes on every page load.
  """
  uid = request.session.get(SESSION_USER_ID)
  access = request.session.get(SESSION_ACCESS)
  refresh = request.session.get(SESSION_REFRESH)
  if not (uid and access and refresh): return False
  existing = db.get_oauth_session(conn)
  if existing and existing.get("refresh_token"): return False
  db.save_oauth_session(conn, uid, access, refresh)
  return True

def owner_access_token(conn, request, config):
  """Usable access token for owner actions: DB (refresh only if needed), else browser session."""
  persist_session_oauth(conn, request)
  access, uid = get_valid_access_token(conn, config)
  if access and uid: return access, uid
  if request.session.get(SESSION_ACCESS) and request.session.get(SESSION_USER_ID):
    return request.session[SESSION_ACCESS], request.session[SESSION_USER_ID]
  return None, None

def get_valid_access_token(conn, config, now=None):
  """Return (access_token, x_user_id) from DB; refresh over the network only near/after expiry."""
  row = db.get_oauth_session(conn) if conn else None
  if not row or not row.get("refresh_token"): return None, None
  if access_token_usable(row, now=now):
    return row["access_token"], row["x_user_id"]
  http = http_client(config)
  try:
    token = refresh_access_token(http, config.client_id, config.client_secret, row["refresh_token"])
  except Exception:
    return None, None
  access = token["access_token"]
  refresh = token.get("refresh_token") or row["refresh_token"]
  db.save_oauth_session(conn, row["x_user_id"], access, refresh,
    expires_at=expires_at_from_token(token, now=now))
  return access, row["x_user_id"]

def http_client(config):
  return config.http or httpx.Client(timeout=30)

# Paths any client may hit without a browser login cookie.
# /feeds/ must stay public: RSS readers do not send session cookies, so requiring
# auth made them receive the HTML login page (or a redirect) and report "feed not found".
# /editions/ is public too: feed item links deep-link here; content is already in the feed.
PUBLIC_PREFIXES = ("/auth/", "/feeds/", "/editions/", "/static/")
class RequireAuthMiddleware:
  def __init__(self, app, config: AuthConfig):
    self.app = app
    self.config = config

  async def __call__(self, scope, receive, send):
    if scope["type"] != "http" or not self.config.enabled:
      return await self.app(scope, receive, send)
    path = scope.get("path", "")
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
      return await self.app(scope, receive, send)
    from starlette.requests import Request
    from starlette.responses import RedirectResponse
    request = Request(scope, receive)
    if request.session.get(SESSION_ACCESS):
      return await self.app(scope, receive, send)
    response = RedirectResponse("/auth/login", status_code=303)
    await response(scope, receive, send)
