"""X API v2 client. Pay-per-use pricing (verified 2026-07): ~$0.005/post read, ~$0.010/user read.
Every call records units + estimated cost to the api_calls table via the caller."""
import os
import httpx

BASE_URL = "https://api.x.com/2"
COST_PER_POST_READ = 0.005
COST_PER_USER_READ = 0.010

TWEET_FIELDS = "created_at,referenced_tweets,entities,public_metrics,attachments"
MEDIA_FIELDS = "url,preview_image_url,type,alt_text,width,height"
EXPANSIONS = "attachments.media_keys,referenced_tweets.id,referenced_tweets.id.attachments.media_keys"

def count_post_reads(body):
  """Unique post IDs in data + includes.tweets — each counts toward billing."""
  ids = set()
  for t in body.get("data") or []: ids.add(t["id"])
  for t in (body.get("includes") or {}).get("tweets") or []: ids.add(t["id"])
  return len(ids)

def attach_media(tweets, includes):
  """Merge expanded media objects from includes.media onto each tweet as media_expanded."""
  by_key = {m["media_key"]: m for m in (includes or {}).get("media", [])}
  for t in tweets:
    keys = (t.get("attachments") or {}).get("media_keys") or []
    t["media_expanded"] = [by_key[k] for k in keys if k in by_key]
  return tweets

def attach_quoted(tweets, includes):
  """Merge quoted tweet + its media from includes onto the quoting tweet as quoted_tweet."""
  by_id = {t["id"]: t for t in (includes or {}).get("tweets", [])}
  by_key = {m["media_key"]: m for m in (includes or {}).get("media", [])}
  for t in tweets:
    ref = next((r for r in (t.get("referenced_tweets") or []) if r.get("type") == "quoted"), None)
    if not ref: continue
    qt = by_id.get(ref["id"])
    if not qt: continue
    keys = (qt.get("attachments") or {}).get("media_keys") or []
    t["quoted_tweet"] = {**qt, "media_expanded": [by_key[k] for k in keys if k in by_key]}
  return tweets

def enrich_tweets(page, includes):
  attach_media(page, includes); attach_quoted(page, includes)
  return page

class XClient:
  def __init__(self, bearer_token=None, http=None):
    self.token = bearer_token or os.environ.get("X_BEARER_TOKEN", "")
    self.http = http or httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {self.token}"}, timeout=30)

  def get_user_by_handle(self, handle):
    """Returns ({id, name, username}, cost_usd)."""
    r = self.http.get(f"/users/by/username/{handle}"); r.raise_for_status()
    return r.json()["data"], COST_PER_USER_READ

  def get_user_tweets(self, x_user_id, start_time, end_time, include_replies, include_retweets):
    """Returns (list of raw tweet dicts, cost_usd, post_read_units).
    Excludes replies/retweets at the API level when settings say so."""
    excludes = []
    if not include_replies: excludes.append("replies")
    if not include_retweets: excludes.append("retweets")
    tweets = []; cost = 0.0; units = 0; token = None
    while True:
      params = {
        "start_time": start_time, "end_time": end_time, "max_results": 100,
        "tweet.fields": TWEET_FIELDS, "expansions": EXPANSIONS, "media.fields": MEDIA_FIELDS}
      if excludes: params["exclude"] = ",".join(excludes)
      if token: params["pagination_token"] = token
      r = self.http.get(f"/users/{x_user_id}/tweets", params=params); r.raise_for_status()
      body = r.json(); page = body.get("data", [])
      enrich_tweets(page, body.get("includes"))
      reads = count_post_reads(body); units += reads; cost += reads * COST_PER_POST_READ
      tweets.extend(page); token = body.get("meta", {}).get("next_token")
      if not token: break
    return tweets, cost, units

def classify_tweet(raw):
  """post | quote | reply | retweet, based on referenced_tweets."""
  for ref in raw.get("referenced_tweets") or []:
    if ref.get("type") == "retweeted": return "retweet"
    if ref.get("type") == "quoted": return "quote"
    if ref.get("type") == "replied_to": return "reply"
  return "post"
