"""User-context X API actions (follow, like) using the owner's OAuth access token."""
import httpx

from app import db
from app.fetch.client import XClient

BASE_URL = "https://api.x.com/2"

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

def like_digest_items(conn, actions_client, access_token, owner_user_id, items):
  """Like digest tweets from the owner's account. Returns count newly liked. Skips already-liked."""
  if not access_token or not owner_user_id or not items: return 0
  liked = 0
  for item in items:
    tweet_id = item["tweet_id"]
    if db.is_tweet_liked(conn, tweet_id): continue
    try:
      actions_client.like_tweet(access_token, owner_user_id, tweet_id)
      db.mark_tweet_liked(conn, tweet_id); liked += 1
    except Exception: pass
  return liked
