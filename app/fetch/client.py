"""X API v2 client. Pay-per-use pricing (verified 2026-07): ~$0.005/post read, ~$0.010/user read.
Every call records units + estimated cost to the api_calls table via the caller."""
import os
import httpx

BASE_URL = "https://api.x.com/2"
COST_PER_POST_READ = 0.005
COST_PER_USER_READ = 0.010

TWEET_FIELDS = "created_at,referenced_tweets,entities,public_metrics,attachments"
MEDIA_FIELDS = "url,preview_image_url,type,alt_text,width,height"

def attach_media(tweets, includes):
  """Merge expanded media objects from includes.media onto each tweet as media_expanded."""
  by_key = {m["media_key"]: m for m in (includes or {}).get("media", [])}
  for t in tweets:
    keys = (t.get("attachments") or {}).get("media_keys") or []
    t["media_expanded"] = [by_key[k] for k in keys if k in by_key]
  return tweets

class XClient:
  def __init__(self, bearer_token=None, http=None):
    self.token = bearer_token or os.environ.get("X_BEARER_TOKEN", "")
    self.http = http or httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {self.token}"}, timeout=30)

  def get_user_by_handle(self, handle):
    """Returns ({id, name, username}, cost_usd)."""
    r = self.http.get(f"/users/by/username/{handle}"); r.raise_for_status()
    return r.json()["data"], COST_PER_USER_READ

  def get_user_tweets(self, x_user_id, start_time, end_time, include_replies, include_retweets):
    """Returns (list of raw tweet dicts, cost_usd). Excludes replies/retweets at the API
    level when settings say so — excluded tweets are never fetched, so never paid for."""
    excludes = []
    if not include_replies: excludes.append("replies")
    if not include_retweets: excludes.append("retweets")
    tweets = []; cost = 0.0; token = None
    while True:
      params = {
        "start_time": start_time, "end_time": end_time, "max_results": 100,
        "tweet.fields": TWEET_FIELDS, "expansions": "attachments.media_keys",
        "media.fields": MEDIA_FIELDS}
      if excludes: params["exclude"] = ",".join(excludes)
      if token: params["pagination_token"] = token
      r = self.http.get(f"/users/{x_user_id}/tweets", params=params); r.raise_for_status()
      body = r.json(); page = body.get("data", [])
      attach_media(page, body.get("includes"))
      tweets.extend(page); cost += len(page) * COST_PER_POST_READ
      token = body.get("meta", {}).get("next_token")
      if not token: break
    return tweets, cost

def classify_tweet(raw):
  """post | quote | reply | retweet, based on referenced_tweets."""
  for ref in raw.get("referenced_tweets") or []:
    if ref.get("type") == "retweeted": return "retweet"
    if ref.get("type") == "quoted": return "quote"
    if ref.get("type") == "replied_to": return "reply"
  return "post"
