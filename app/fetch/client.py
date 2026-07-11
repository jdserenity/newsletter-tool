"""X API v2 client. Pay-per-use pricing (verified 2026-07): ~$0.005/post read, ~$0.010/user read.
Every call records units + estimated cost to the api_calls table via the caller."""
import os
import time
import httpx

BASE_URL = "https://api.x.com/2"
COST_PER_POST_READ = 0.005
COST_PER_USER_READ = 0.010
COST_PER_COUNTS_ALL = 0.010

# Transient X / network failures worth retrying before giving up on a newsletter run.
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_BASE = 2.0  # seconds; delays 2, 4, 8, 16, 32

# note_tweet carries full text for long posts; without it, X truncates `text` (~280 chars).
TWEET_FIELDS = "created_at,referenced_tweets,entities,public_metrics,attachments,author_id,note_tweet"
MEDIA_FIELDS = "url,preview_image_url,type,alt_text,width,height"
USER_FIELDS = "username"
EXPANSIONS = "attachments.media_keys,referenced_tweets.id,referenced_tweets.id.attachments.media_keys,referenced_tweets.id.author_id"

def count_post_reads(body):
  """Unique post IDs in data + includes.tweets — each counts toward billing."""
  ids = set()
  for t in body.get("data") or []: ids.add(t["id"])
  for t in (body.get("includes") or {}).get("tweets") or []: ids.add(t["id"])
  return len(ids)

def _media_keys(tweet):
  keys = list((tweet.get("attachments") or {}).get("media_keys") or [])
  if keys: return keys
  for u in (tweet.get("entities") or {}).get("urls") or []:
    mk = u.get("media_key")
    if mk and mk not in keys: keys.append(mk)
  return keys

def attach_media(tweets, includes):
  """Merge expanded media objects from includes.media onto each tweet as media_expanded."""
  by_key = {m["media_key"]: m for m in (includes or {}).get("media", [])}
  for t in tweets:
    t["media_expanded"] = [by_key[k] for k in _media_keys(t) if k in by_key]
  return tweets

def attach_quoted(tweets, includes):
  """Merge quoted tweet + its media and author from includes onto the quoting tweet."""
  by_id = {t["id"]: t for t in (includes or {}).get("tweets", [])}
  by_key = {m["media_key"]: m for m in (includes or {}).get("media", [])}
  by_user = {u["id"]: u for u in (includes or {}).get("users", [])}
  for t in tweets:
    ref = next((r for r in (t.get("referenced_tweets") or []) if r.get("type") == "quoted"), None)
    if not ref: continue
    qt = by_id.get(ref["id"])
    if not qt: continue
    keys = _media_keys(qt)
    author = by_user.get(qt.get("author_id")) or {}
    t["quoted_tweet"] = {
      **qt, "author_handle": author.get("username"),
      "media_expanded": [by_key[k] for k in keys if k in by_key]}
  return tweets

def enrich_tweets(page, includes):
  attach_media(page, includes); attach_quoted(page, includes)
  return page

def retry_delay_seconds(attempt, response=None, base=DEFAULT_BACKOFF_BASE):
  """Seconds to wait before the next try. attempt is 0-based (first retry = 0)."""
  if response is not None and response.status_code == 429:
    ra = response.headers.get("Retry-After")
    if ra:
      try: return max(float(ra), 0.0)
      except ValueError: pass
  return base * (2 ** attempt)

def get_with_retries(http, path, *, params=None, max_retries=DEFAULT_MAX_RETRIES,
                     sleep=time.sleep, backoff_base=DEFAULT_BACKOFF_BASE):
  """GET with retries on transient status codes and transport errors."""
  last_exc = None
  for attempt in range(max_retries + 1):
    try:
      r = http.get(path, params=params)
    except httpx.TransportError as e:
      last_exc = e
      if attempt >= max_retries: raise
      sleep(retry_delay_seconds(attempt, base=backoff_base)); continue
    if r.status_code in RETRYABLE_STATUS and attempt < max_retries:
      sleep(retry_delay_seconds(attempt, response=r, base=backoff_base)); continue
    r.raise_for_status()
    return r
  if last_exc: raise last_exc
  raise RuntimeError("get_with_retries exhausted without response")

class XClient:
  def __init__(self, bearer_token=None, http=None, sleep=time.sleep, max_retries=DEFAULT_MAX_RETRIES):
    self.token = bearer_token or os.environ.get("X_BEARER_TOKEN", "")
    self.http = http or httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {self.token}"}, timeout=30)
    self.sleep = sleep
    self.max_retries = max_retries

  def _get(self, path, params=None):
    return get_with_retries(self.http, path, params=params, max_retries=self.max_retries, sleep=self.sleep)

  def get_user_by_handle(self, handle):
    """Returns ({id, name, username}, cost_usd)."""
    r = self._get(f"/users/by/username/{handle}")
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
        "tweet.fields": TWEET_FIELDS, "expansions": EXPANSIONS,
        "media.fields": MEDIA_FIELDS, "user.fields": USER_FIELDS}
      if excludes: params["exclude"] = ",".join(excludes)
      if token: params["pagination_token"] = token
      r = self._get(f"/users/{x_user_id}/tweets", params=params)
      body = r.json(); page = body.get("data", [])
      enrich_tweets(page, body.get("includes"))
      reads = count_post_reads(body); units += reads; cost += reads * COST_PER_POST_READ
      tweets.extend(page); token = body.get("meta", {}).get("next_token")
      if not token: break
    return tweets, cost, units

  def count_tweets_all(self, query, start_time, end_time, granularity="day"):
    """Returns (tweet_count, cost_usd) for a query in a time window. One charge per request page."""
    params = {"query": query, "start_time": start_time, "end_time": end_time, "granularity": granularity}
    total = 0; cost = 0.0; token = None
    while True:
      p = dict(params)
      if token: p["pagination_token"] = token
      r = self._get("/tweets/counts/all", params=p)
      body = r.json()
      total += sum(b.get("tweet_count", 0) for b in body.get("data", []))
      cost += COST_PER_COUNTS_ALL
      token = body.get("meta", {}).get("next_token")
      if not token: break
    return total, cost

def classify_tweet(raw):
  """post | quote | reply | retweet, based on referenced_tweets."""
  for ref in raw.get("referenced_tweets") or []:
    if ref.get("type") == "retweeted": return "retweet"
    if ref.get("type") == "quoted": return "quote"
    if ref.get("type") == "replied_to": return "reply"
  return "post"
