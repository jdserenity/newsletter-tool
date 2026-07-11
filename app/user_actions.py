"""Owner-initiated X write actions (like on checkmark click)."""
import httpx

BASE_URL = "https://api.x.com/2"

class LikeActionError(Exception):
  """X like/unlike API call failed."""

class UserActionsClient:
  def __init__(self, http=None):
    self.http = http or httpx.Client(base_url=BASE_URL, timeout=30)

  def like_tweet(self, access_token, user_id, tweet_id):
    r = self.http.post(f"/users/{user_id}/likes",
      headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
      json={"tweet_id": tweet_id})
    if r.status_code >= 400:
      raise LikeActionError(f"X like failed ({r.status_code}): {r.text}")
    return r.json()

  def unlike_tweet(self, access_token, user_id, tweet_id):
    r = self.http.delete(f"/users/{user_id}/likes/{tweet_id}",
      headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code >= 400:
      raise LikeActionError(f"X unlike failed ({r.status_code}): {r.text}")
    return r.json() if r.content else {}

def like_tweet_on_x(access_token, owner_user_id, tweet_id, actions_client=None):
  """POST like to X. Raises LikeActionError on failure."""
  client = actions_client or UserActionsClient()
  return client.like_tweet(access_token, owner_user_id, tweet_id)

def unlike_tweet_on_x(access_token, owner_user_id, tweet_id, actions_client=None):
  """DELETE like on X. Raises LikeActionError on failure."""
  client = actions_client or UserActionsClient()
  return client.unlike_tweet(access_token, owner_user_id, tweet_id)
