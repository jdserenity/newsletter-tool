"""OAuth session helpers used by the app (token refresh / persist).

Auto-follow and auto-like coverage lived here historically; those features were removed.
"""
import httpx
import pytest

from app import auth, db

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
