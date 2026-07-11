"""Scheduled fetch: pulls each active account's tweets for the current period, honoring
per-account settings at the API level, records costs in the DB, and stores raw tweets."""
import json
from datetime import datetime, timedelta, timezone

from app import db
from app.fetch.client import XClient, classify_tweet, COST_PER_USER_READ

def _post_read_tweet_ids(tweets):
  """Timeline tweet IDs plus expanded quoted tweets — each can bill as a post read."""
  ids = []; seen = set()
  for t in tweets:
    for tid in (t["id"], (t.get("quoted_tweet") or {}).get("id")):
      if tid and tid not in seen: ids.append(tid); seen.add(tid)
  return ids

def _fmt_day(d):
  return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def week_bounds(now=None):
  """Most recent complete Mon-Mon week as (start_iso, end_iso)."""
  return period_bounds(now, cadence="weekly")

def period_bounds(now=None, cadence="twice_weekly"):
  """Most recent complete fetch period as (start_iso, end_iso).

  weekly: Mon→Mon. twice_weekly: Mon→Thu or Thu→Mon (whichever ended most recently).
  """
  now = now or datetime.now(timezone.utc)
  today = now.date()
  if cadence == "weekly":
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(days=7); end = this_monday
    return _fmt_day(start), _fmt_day(end)
  # twice_weekly: walk back to most recent Mon (0) or Thu (3), including today.
  end = today
  while end.weekday() not in (0, 3):
    end -= timedelta(days=1)
  if end.weekday() == 0:  # Monday end → started previous Thursday
    start = end - timedelta(days=4)
  else:  # Thursday end → started previous Monday
    start = end - timedelta(days=3)
  return _fmt_day(start), _fmt_day(end)

def fetch_account_week(conn, client, account, week_start, week_end, now=None, log=None):
  """Fetch one account's tweets for the period. Returns cost incurred (USD)."""
  now = now or datetime.now(timezone.utc)
  cost = 0.0
  handle = account["handle"]
  if log: log(f"Fetching @{handle} ({week_start[:10]} → {week_end[:10]})...")
  if not account["x_user_id"]:
    if log: log(f"  @{handle}: looking up user id...")
    user, _ = client.get_user_by_handle(account["handle"])
    uc = COST_PER_USER_READ if db.billable_user_lookup(conn, account["id"], now=now) else 0.0
    db.record_api_call(conn, account["id"], "users/by/username", 1 if uc else 0, uc); cost += uc
    db.set_account_identity(conn, account["id"], user["id"], user.get("name", account["handle"]))
    account = db.get_account(conn, account_id=account["id"])
    if log: log(f"  @{handle}: x_user_id={user['id']}")
  tweets, _, _ = client.get_user_tweets(
    account["x_user_id"], week_start, week_end,
    include_replies=bool(account["include_replies"]), include_retweets=bool(account["include_retweets"]))
  tweet_ids = _post_read_tweet_ids(tweets)
  c = db.post_read_cost(conn, tweet_ids, now=now)
  billable = db.billable_post_count(conn, tweet_ids, now=now)
  db.record_api_call(conn, account["id"], "users/:id/tweets", billable, c); cost += c
  for t in tweets: t["kind"] = classify_tweet(t)
  db.save_tweets(conn, account["id"], tweets, fetched_at=now)
  if log: log(f"  @{handle}: stored {len(tweets)} tweets, API ${cost:.3f}")
  return cost

def _merge_unread_from_previous(conn, account_id, week_start, items):
  """Prepend unread items from the previous edition (deduped, chrono-sorted)."""
  prev = db.previous_edition(conn, account_id, week_start)
  if not prev: return items
  prev_items = json.loads(prev["content_json"])
  tweet_ids = [i["tweet_id"] for i in prev_items if i.get("tweet_id")]
  read_ids = db.read_tweet_ids(conn, tweet_ids)
  seen = {i["tweet_id"] for i in items if i.get("tweet_id")}
  carry = [i for i in prev_items
           if i.get("tweet_id") and i["tweet_id"] not in read_ids and i["tweet_id"] not in seen]
  return sorted(carry + items, key=lambda i: i["created_at"])

def build_account_edition(conn, account, week_start, week_end, cost=0.0, append_unread=None):
  """Build and store one account's newsletter from tweets already in the DB."""
  from app.newsletter import build_newsletter
  account = db.get_account(conn, account_id=account["id"])
  if append_unread is None:
    append_unread = bool(db.get_app_settings(conn)["append_unread"])
  tweets = db.tweets_for_week(conn, account["id"], week_start, week_end)
  items = build_newsletter(tweets, account)
  if append_unread:
    items = _merge_unread_from_previous(conn, account["id"], week_start, items)
  db.save_edition(conn, account["id"], week_start, week_end, items, cost)
  return items

def _verify_editions(conn, week_start, account_ids=None):
  """Every requested active account must have a newsletter row for this period after a fetch run."""
  accounts = db.list_accounts(conn)
  if account_ids is not None:
    want = set(account_ids)
    accounts = [a for a in accounts if a["id"] in want]
  missing = [a["handle"] for a in accounts if db.edition_for_week(conn, a["id"], week_start) is None]
  if missing:
    raise RuntimeError("Newsletter build failed for: " + ", ".join(f"@{h}" for h in missing))

def repair_missing_editions(conn, now=None):
  """Build newsletters from stored tweets when the period has tweets but no edition row (no API calls)."""
  cadence = db.get_app_settings(conn)["cadence"]
  week_start, week_end = period_bounds(now, cadence)
  repaired = []
  for account in db.list_accounts(conn):
    if db.edition_for_week(conn, account["id"], week_start) is not None: continue
    if not db.tweets_for_week(conn, account["id"], week_start, week_end): continue
    build_account_edition(conn, account, week_start, week_end, cost=0.0)
    repaired.append(account["handle"])
  return repaired

def run_weekly_fetch(conn, client=None, now=None, db_path=None, log=None):
  """Fetch + build newsletters for all active accounts. Returns list of (handle, cost).

  Uses the stored cadence to pick the current period (weekly Mon–Mon or twice-weekly half-week).
  Retries transient X errors inside the client. If one account still fails, others still build;
  raises only when every account fails.
  """
  client = client or XClient(log=log)
  settings = db.get_app_settings(conn)
  week_start, week_end = period_bounds(now, settings["cadence"])
  accounts = db.list_accounts(conn)
  if log:
    log(f"Period {week_start[:10]} → {week_end[:10]} · {len(accounts)} account(s)")
    if settings["append_unread"]: log("Append unread: yes")
    else: log("Append unread: no (wipe unread from prior edition)")
  costs = {}; errors = {}
  for account in accounts:
    try:
      costs[account["id"]] = fetch_account_week(conn, client, account, week_start, week_end, now=now, log=log)
    except Exception as e:
      errors[account["handle"]] = e
      if log: log(f"  @{account['handle']}: FAILED — {e}")
  if errors and not costs:
    detail = "; ".join(f"@{h}: {err}" for h, err in errors.items())
    raise RuntimeError("Fetch failed for all accounts: " + detail)
  results = []
  for account in accounts:
    if account["id"] not in costs: continue
    if log: log(f"Building edition for @{account['handle']}...")
    items = build_account_edition(conn, account, week_start, week_end, costs[account["id"]],
      append_unread=bool(settings["append_unread"]))
    if log: log(f"  @{account['handle']}: {len(items)} items")
    results.append((account["handle"], costs[account["id"]]))
  _verify_editions(conn, week_start, account_ids=list(costs))
  if errors:
    for handle, err in errors.items():
      msg = f"warning: fetch failed for @{handle} after retries: {err}"
      if log: log(msg)
      else: print(msg, flush=True)
  return results
