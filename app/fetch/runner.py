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
  tweets, c, units = client.get_user_tweets(
    account["x_user_id"], week_start, week_end,
    include_replies=bool(account["include_replies"]), include_retweets=bool(account["include_retweets"]))
  db.record_api_call(conn, account["id"], "users/:id/tweets", units, c); cost += c
  for t in tweets: t["kind"] = classify_tweet(t)
  db.save_tweets(conn, account["id"], tweets)
  return cost

def run_weekly_fetch(conn, client=None, now=None, db_path=None):
  """Fetch + build newsletters for all active accounts. Returns list of (handle, cost)."""
  from app.newsletter import build_newsletter
  from app.user_actions import enqueue_newsletter_likes, start_like_drain
  client = client or XClient()
  week_start, week_end = week_bounds(now)
  results = []; enqueued = 0
  for account in db.list_accounts(conn):
    cost = fetch_account_week(conn, client, account, week_start, week_end)
    account = db.get_account(conn, account_id=account["id"])
    tweets = db.tweets_for_week(conn, account["id"], week_start, week_end)
    items = build_newsletter(tweets, account)
    db.save_edition(conn, account["id"], week_start, week_end, items, cost)
    enqueued += enqueue_newsletter_likes(conn, items)
    results.append((account["handle"], cost))
  if db_path and enqueued > 0: start_like_drain(db_path)
  return results
