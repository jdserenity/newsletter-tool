"""User-context X API actions (follow, like) using the owner's OAuth access token."""
import random
import threading
import time

import httpx

from app import auth, db
from app.fetch.client import XClient

BASE_URL = "https://api.x.com/2"
LIKE_BASE_SECONDS = 60
LIKE_JITTER_SECONDS = 20

_drain_lock = threading.Lock()
_drain_running = False

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

def like_delay_seconds():
  """Wait ~1 minute ± 1–20s before the next like."""
  return LIKE_BASE_SECONDS + random.choice((-1, 1)) * random.randint(1, LIKE_JITTER_SECONDS)

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
    db.mark_account_followed(conn, account["id"])
  except Exception: pass

def enqueue_newsletter_likes(conn, items):
  """Queue newsletter tweets for background liking. Skips already-liked and already-queued."""
  if not items: return 0
  enqueued = 0
  for item in items:
    tweet_id = item["tweet_id"]
    if db.is_tweet_liked(conn, tweet_id) or db.is_tweet_queued(conn, tweet_id): continue
    db.enqueue_like(conn, tweet_id); enqueued += 1
  return enqueued

def drain_like_queue(conn, auth_config=None, actions_client=None, sleep=time.sleep):
  """Like every queued tweet: first immediately, then ~1 min ± jitter between each."""
  auth_config = auth_config or auth.AuthConfig.from_env()
  actions_client = actions_client or UserActionsClient()
  liked = 0; first = True
  while True:
    tweet_id = db.peek_like_queue(conn)
    if not tweet_id: break
    if db.is_tweet_liked(conn, tweet_id):
      db.dequeue_like(conn, tweet_id); continue
    if not first: sleep(like_delay_seconds())
    first = False
    access_token, owner_id = auth.get_valid_access_token(conn, auth_config) if auth_config.enabled else (None, None)
    if not access_token or not owner_id: break
    try:
      actions_client.like_tweet(access_token, owner_id, tweet_id)
      db.mark_tweet_liked(conn, tweet_id)
      db.dequeue_like(conn, tweet_id); liked += 1
    except Exception: pass
  return liked

def _drain_worker(db_path):
  global _drain_running
  try:
    conn = db.connect(db_path)
    try: drain_like_queue(conn)
    finally: conn.close()
  finally:
    with _drain_lock:
      _drain_running = False

def start_like_drain(db_path):
  """Run the like queue in a background thread until empty. No-op if already running."""
  global _drain_running
  with _drain_lock:
    if _drain_running: return
    _drain_running = True
  threading.Thread(target=_drain_worker, args=(db_path,), daemon=True).start()

def resume_like_drain_if_needed(db_path):
  """Resume draining after restart if tweets are still queued."""
  conn = db.connect(db_path)
  try:
    if db.like_queue_size(conn) > 0: start_like_drain(db_path)
  finally:
    conn.close()
