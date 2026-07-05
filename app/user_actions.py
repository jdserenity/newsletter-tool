"""User-context X API actions (follow, like) using the owner's OAuth access token."""
import random
from datetime import datetime, timedelta, timezone

import httpx

from app import auth, db
from app.fetch.client import XClient

BASE_URL = "https://api.x.com/2"
LIKE_BASE_SECONDS = 60
LIKE_JITTER_SECONDS = (1, 20)

class UserActionsClient:
  def __init__(self, http=None):
    self.http = http or httpx.Client(base_url=BASE_URL, timeout=30)

  def follow_user(self, access_token, source_user_id, target_user_id):
    r = self.http.post(f"/users/{source_user_id}/following",
      headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
      json={"target_user_id": target_user_id})
    r.raise_for_status()
    return r.json()

  def like_tweet(self, access_token, user_id, tweet_id):
    r = self.http.post(f"/users/{user_id}/likes",
      headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
      json={"tweet_id": tweet_id})
    r.raise_for_status()
    return r.json()

def _iso(dt):
  return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _parse_iso(iso):
  return datetime.fromisoformat(iso.replace("Z", "+00:00"))

def like_delay_seconds():
  """Wait ~1 minute plus 1–20s jitter before the next like."""
  return LIKE_BASE_SECONDS + random.randint(*LIKE_JITTER_SECONDS)

def next_like_deadline(from_time=None):
  from_time = from_time or datetime.now(timezone.utc)
  return from_time + timedelta(seconds=like_delay_seconds())

def resolve_target_x_user_id(conn, read_client, account):
  """Resolve tracked account's X user id, using bearer read client if not cached."""
  if account["x_user_id"]: return account["x_user_id"]
  user, _ = read_client.get_user_by_handle(account["handle"])
  db.set_account_identity(conn, account["id"], user["id"], user.get("name", account["handle"]))
  return user["id"]

def follow_tracked_account(conn, actions_client, access_token, owner_user_id, account, read_client=None):
  """Follow a tracked account from the owner's X account. Best-effort; errors are swallowed."""
  if not access_token or not owner_user_id: return
  read_client = read_client or XClient()
  try:
    target_id = resolve_target_x_user_id(conn, read_client, account)
    actions_client.follow_user(access_token, owner_user_id, target_id)
  except Exception: pass

def enqueue_digest_likes(conn, items):
  """Queue digest tweets for background liking. Skips already-liked and already-queued."""
  if not items: return 0
  enqueued = 0
  for item in items:
    tweet_id = item["tweet_id"]
    if db.is_tweet_liked(conn, tweet_id) or db.is_tweet_queued(conn, tweet_id): continue
    db.enqueue_like(conn, tweet_id); enqueued += 1
  return enqueued

def process_like_queue(conn, auth_config=None, actions_client=None, now=None):
  """Like at most one queued tweet if pacing allows. Returns True if a like was attempted."""
  now = now or datetime.now(timezone.utc)
  next_at = db.get_next_like_at(conn)
  if next_at and now < _parse_iso(next_at): return False
  tweet_id = db.peek_like_queue(conn)
  if not tweet_id: return False
  auth_config = auth_config or auth.AuthConfig.from_env()
  access_token, owner_id = auth.get_valid_access_token(conn, auth_config) if auth_config.enabled else (None, None)
  if not access_token or not owner_id: return False
  actions_client = actions_client or UserActionsClient()
  try:
    actions_client.like_tweet(access_token, owner_id, tweet_id)
    db.mark_tweet_liked(conn, tweet_id)
    db.dequeue_like(conn, tweet_id)
  except Exception: pass
  db.set_next_like_at(conn, _iso(next_like_deadline(now)))
  return True
