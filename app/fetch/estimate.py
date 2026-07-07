"""Pre-add fetch cost estimate via X counts/all over the last three complete weeks."""
from datetime import datetime, timedelta, timezone

from app.fetch.client import XClient, COST_PER_COUNTS_ALL, COST_PER_POST_READ, COST_PER_USER_READ

ESTIMATE_WEEKS = 3

def normalize_handle(handle):
  return handle.lstrip("@").strip().lower()

def counts_query(handle, include_replies=False, include_retweets=False):
  """Search query mirroring timeline exclude settings (quotes are always fetched)."""
  q = f"from:{normalize_handle(handle)}"
  if not include_retweets: q += " -is:retweet"
  if not include_replies: q += " -is:reply"
  return q

def prior_week_windows(now=None, weeks=ESTIMATE_WEEKS):
  """Last `weeks` complete Mon-Mon windows in UTC, oldest first."""
  now = now or datetime.now(timezone.utc)
  this_monday = now.date() - timedelta(days=now.date().weekday())
  fmt = lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  return [(fmt(this_monday - timedelta(days=7 * (i + 1))), fmt(this_monday - timedelta(days=7 * i)))
    for i in range(weeks - 1, -1, -1)]

def estimate_fetch_cost(client, handle, include_replies=False, include_retweets=False, now=None):
  """Returns dict with 3-week average tweet volume and projected weekly fetch cost."""
  query = counts_query(handle, include_replies=include_replies, include_retweets=include_retweets)
  weeks = []; query_cost = 0.0
  for start, end in prior_week_windows(now=now):
    count, c = client.count_tweets_all(query, start, end)
    query_cost += c
    weeks.append({"week_start": start, "week_end": end, "tweet_count": count})
  total = sum(w["tweet_count"] for w in weeks)
  avg = total / len(weeks) if weeks else 0.0
  return {
    "handle": normalize_handle(handle),
    "query": query,
    "weeks": weeks,
    "avg_tweets_per_week": round(avg, 1),
    "estimated_weekly_fetch_usd": round(avg * COST_PER_POST_READ + COST_PER_USER_READ, 3),
    "estimate_query_cost_usd": round(query_cost, 3),
  }
