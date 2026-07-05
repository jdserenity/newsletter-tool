"""Weekly fetch: pulls each active account's tweets for the week, honoring per-account
settings at the API level, records costs in the DB, and stores raw tweets."""
from datetime import datetime, timedelta, timezone

from app import db
from app.fetch.client import XClient, classify_tweet

def week_bounds(now=None):
  """Most recent complete Mon-Mon week as (start_iso, end_iso)."""
  now = now or datetime.now(timezone.utc)
  today = now.date()
  this_monday = today - timedelta(days=today.weekday())
  start = this_monday - timedelta(days=7); end = this_monday
  fmt = lambda d: datetime(d.year, d.month, d.day, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
  return fmt(start), fmt(end)

def fetch_account_week(conn, client, account, week_start, week_end):
  """Fetch one account's tweets for the week. Returns cost incurred (USD)."""
  cost = 0.0
  if not account["x_user_id"]:
    user, c = client.get_user_by_handle(account["handle"])
    db.record_api_call(conn, account["id"], "users/by/username", 1, c); cost += c
    db.set_account_identity(conn, account["id"], user["id"], user.get("name", account["handle"]))
    account = db.get_account(conn, account_id=account["id"])
  tweets, c = client.get_user_tweets(
    account["x_user_id"], week_start, week_end,
    include_replies=bool(account["include_replies"]), include_retweets=bool(account["include_retweets"]))
  db.record_api_call(conn, account["id"], "users/:id/tweets", len(tweets), c); cost += c
  for t in tweets: t["kind"] = classify_tweet(t)
  db.save_tweets(conn, account["id"], tweets)
  return cost

def build_account_edition(conn, account, week_start, week_end, cost=0.0):
  """Build and store one account's newsletter from tweets already in the DB."""
  from app.newsletter import build_newsletter
  account = db.get_account(conn, account_id=account["id"])
  tweets = db.tweets_for_week(conn, account["id"], week_start, week_end)
  items = build_newsletter(tweets, account)
  db.save_edition(conn, account["id"], week_start, week_end, items, cost)
  return items

def _verify_editions(conn, week_start):
  """Every active account must have a newsletter row for this week after a fetch run."""
  missing = [a["handle"] for a in db.list_accounts(conn)
    if db.edition_for_week(conn, a["id"], week_start) is None]
  if missing:
    raise RuntimeError("Newsletter build failed for: " + ", ".join(f"@{h}" for h in missing))

def repair_missing_editions(conn, now=None):
  """Build newsletters from stored tweets when the week has tweets but no edition row (no API calls)."""
  week_start, week_end = week_bounds(now)
  repaired = []
  for account in db.list_accounts(conn):
    if db.edition_for_week(conn, account["id"], week_start) is not None: continue
    if not db.tweets_for_week(conn, account["id"], week_start, week_end): continue
    build_account_edition(conn, account, week_start, week_end, cost=0.0)
    repaired.append(account["handle"])
  return repaired

def run_weekly_fetch(conn, client=None, now=None, db_path=None):
  """Fetch + build newsletters for all active accounts. Returns list of (handle, cost)."""
  from app.user_actions import enqueue_newsletter_likes, start_like_drain
  client = client or XClient()
  week_start, week_end = week_bounds(now)
  costs = {}
  for account in db.list_accounts(conn):
    costs[account["id"]] = fetch_account_week(conn, client, account, week_start, week_end)
  results = []; enqueued = 0
  for account in db.list_accounts(conn):
    items = build_account_edition(conn, account, week_start, week_end, costs.get(account["id"], 0.0))
    enqueued += enqueue_newsletter_likes(conn, items)
    results.append((account["handle"], costs.get(account["id"], 0.0)))
  _verify_editions(conn, week_start)
  if db_path and enqueued > 0: start_like_drain(db_path)
  return results
