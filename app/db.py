import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "newsletter-tool" / "newsletter.db"

def resolve_db_path(override=None):
  if override is not None: return Path(override).expanduser()
  env = os.environ.get("DATABASE_PATH")
  if env: return Path(env).expanduser()
  return DEFAULT_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  handle TEXT NOT NULL UNIQUE,
  x_user_id TEXT,
  display_name TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  include_quotes INTEGER NOT NULL DEFAULT 1,
  include_replies INTEGER NOT NULL DEFAULT 0,
  include_retweets INTEGER NOT NULL DEFAULT 0,
  followed_at TEXT,
  added_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tweets (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  tweet_id TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'post',  -- post | quote | reply | retweet
  text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS editions (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  week_start TEXT NOT NULL,
  week_end TEXT NOT NULL,
  item_count INTEGER NOT NULL,
  cost_usd REAL NOT NULL DEFAULT 0,
  content_json TEXT NOT NULL,
  built_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(account_id, week_start)
);
CREATE TABLE IF NOT EXISTS api_calls (
  id INTEGER PRIMARY KEY,
  account_id INTEGER REFERENCES accounts(id),
  endpoint TEXT NOT NULL,
  units INTEGER NOT NULL,
  cost_usd REAL NOT NULL,
  called_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS oauth_session (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  x_user_id TEXT NOT NULL,
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  expires_at TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS liked_tweets (
  tweet_id TEXT NOT NULL PRIMARY KEY,
  liked_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS like_queue (
  id INTEGER PRIMARY KEY,
  tweet_id TEXT NOT NULL UNIQUE,
  queued_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS read_tweets (
  tweet_id TEXT NOT NULL PRIMARY KEY,
  read_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS read_newsletters (
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  week_start TEXT NOT NULL,
  read_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (account_id, week_start)
);
CREATE TABLE IF NOT EXISTS app_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  cadence TEXT NOT NULL DEFAULT 'twice_weekly',
  append_unread INTEGER NOT NULL DEFAULT 1
);
"""

def connect(db_path=None):
  path = resolve_db_path(db_path)
  if str(path) != ":memory:": path.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(str(path)); conn.row_factory = sqlite3.Row
  conn.executescript(SCHEMA)
  _migrate_schema(conn)
  return conn

def _migrate_schema(conn):
  tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
  if "digests" in tables:
    if "editions" not in tables:
      conn.execute("ALTER TABLE digests RENAME TO editions")
    else:
      conn.execute("INSERT OR IGNORE INTO editions SELECT * FROM digests")
      conn.execute("DROP TABLE digests")
    conn.commit()
  cols = {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
  if "followed_at" not in cols:
    conn.execute("ALTER TABLE accounts ADD COLUMN followed_at TEXT"); conn.commit()
  oauth_cols = {r[1] for r in conn.execute("PRAGMA table_info(oauth_session)").fetchall()}
  if oauth_cols and "expires_at" not in oauth_cols:
    conn.execute("ALTER TABLE oauth_session ADD COLUMN expires_at TEXT"); conn.commit()
  _ensure_app_settings(conn)
  _repair_inflated_api_call_costs(conn)

def _ensure_app_settings(conn):
  conn.execute(
    """CREATE TABLE IF NOT EXISTS app_settings (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      cadence TEXT NOT NULL DEFAULT 'twice_weekly',
      append_unread INTEGER NOT NULL DEFAULT 1)""")
  conn.execute(
    "INSERT OR IGNORE INTO app_settings (id, cadence, append_unread) VALUES (1, 'twice_weekly', 1)")
  conn.commit()

CADENCES = {"weekly", "twice_weekly"}

def get_app_settings(conn):
  _ensure_app_settings(conn)
  row = conn.execute("SELECT cadence, append_unread FROM app_settings WHERE id = 1").fetchone()
  return {"cadence": row["cadence"], "append_unread": int(row["append_unread"])}

def update_app_settings(conn, cadence=None, append_unread=None):
  _ensure_app_settings(conn)
  cur = get_app_settings(conn)
  if cadence is not None:
    if cadence not in CADENCES: raise ValueError(f"cadence must be one of {sorted(CADENCES)}")
    cur["cadence"] = cadence
  if append_unread is not None: cur["append_unread"] = int(bool(append_unread))
  conn.execute("UPDATE app_settings SET cadence = ?, append_unread = ? WHERE id = 1",
    (cur["cadence"], cur["append_unread"])); conn.commit()
  return cur

def _utc_cutoff(now, hours=24):
  return (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

def _repair_inflated_api_call_costs(conn):
  """One-time repair: zero api_calls rows X would have deduped within 24h."""
  if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_calls'").fetchone(): return
  conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
  if conn.execute("SELECT 1 FROM schema_migrations WHERE name = 'api_cost_dedup'").fetchone(): return
  rows = conn.execute(
    "SELECT id, account_id, endpoint, called_at FROM api_calls WHERE cost_usd > 0 ORDER BY called_at, id").fetchall()
  last_charged = {}; changed = False
  for r in rows:
    key = (r["account_id"], r["endpoint"])
    prev = last_charged.get(key)
    if prev:
      prev_at = datetime.strptime(prev, "%Y-%m-%d %H:%M:%S")
      cur_at = datetime.strptime(r["called_at"], "%Y-%m-%d %H:%M:%S")
      if cur_at - prev_at < timedelta(hours=24):
        conn.execute("UPDATE api_calls SET cost_usd = 0, units = 0 WHERE id = ?", (r["id"],)); changed = True
        continue
    last_charged[key] = r["called_at"]
  conn.execute("INSERT INTO schema_migrations (name) VALUES ('api_cost_dedup')"); conn.commit()

# --- accounts ---

def add_account(conn, handle):
  handle = handle.lstrip("@").strip()
  cur = conn.execute("INSERT INTO accounts (handle) VALUES (?)", (handle,)); conn.commit()
  return cur.lastrowid

def remove_account(conn, account_id):
  conn.execute("UPDATE accounts SET active = 0 WHERE id = ?", (account_id,)); conn.commit()

def list_accounts(conn, active_only=True):
  # COLLATE NOCASE: SQLite default sort is ASCII so "Ruxandra" would sort before "alice".
  q = "SELECT * FROM accounts" + (" WHERE active = 1" if active_only else "") + " ORDER BY handle COLLATE NOCASE"
  return [dict(r) for r in conn.execute(q).fetchall()]

def get_account(conn, account_id=None, handle=None):
  if account_id is not None: row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
  else: row = conn.execute("SELECT * FROM accounts WHERE handle = ?", (handle,)).fetchone()
  return dict(row) if row else None

def update_settings(conn, account_id, **settings):
  allowed = {"include_quotes", "include_replies", "include_retweets"}
  fields = {k: int(v) for k, v in settings.items() if k in allowed}
  if not fields: return
  sets = ", ".join(f"{k} = ?" for k in fields)
  conn.execute(f"UPDATE accounts SET {sets} WHERE id = ?", (*fields.values(), account_id)); conn.commit()

def set_account_identity(conn, account_id, x_user_id, display_name):
  conn.execute("UPDATE accounts SET x_user_id = ?, display_name = ? WHERE id = ?", (x_user_id, display_name, account_id)); conn.commit()

def mark_account_followed(conn, account_id):
  conn.execute("UPDATE accounts SET followed_at = datetime('now') WHERE id = ? AND followed_at IS NULL", (account_id,)); conn.commit()

def accounts_pending_follow(conn):
  return [dict(r) for r in conn.execute(
    "SELECT * FROM accounts WHERE active = 1 AND followed_at IS NULL ORDER BY handle COLLATE NOCASE").fetchall()]

def pending_follow_count(conn):
  return conn.execute(
    "SELECT COUNT(*) AS c FROM accounts WHERE active = 1 AND followed_at IS NULL").fetchone()["c"]

# --- tweets ---

def save_tweets(conn, account_id, tweets, fetched_at=None):
  if fetched_at is None: ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
  elif hasattr(fetched_at, "strftime"): ts = fetched_at.strftime("%Y-%m-%d %H:%M:%S")
  else: ts = fetched_at
  for t in tweets:
    conn.execute(
      """INSERT INTO tweets (account_id, tweet_id, kind, text, created_at, raw_json, fetched_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(tweet_id) DO UPDATE SET
           account_id = excluded.account_id, kind = excluded.kind, text = excluded.text,
           created_at = excluded.created_at, raw_json = excluded.raw_json,
           fetched_at = excluded.fetched_at""",
      (account_id, t["id"], t.get("kind", "post"), t["text"], t["created_at"], json.dumps(t), ts))
  conn.commit()

def tweets_for_week(conn, account_id, week_start, week_end):
  rows = conn.execute(
    "SELECT * FROM tweets WHERE account_id = ? AND created_at >= ? AND created_at < ? ORDER BY created_at",
    (account_id, week_start, week_end)).fetchall()
  return [dict(r) for r in rows]

# --- api calls / cost ---

def billable_post_count(conn, tweet_ids, now=None):
  """Post reads X bills once per tweet within 24h; skip tweet IDs we already fetched recently."""
  if not tweet_ids: return 0
  now = now or datetime.now(timezone.utc)
  cutoff = _utc_cutoff(now)
  placeholders = ",".join("?" * len(tweet_ids))
  rows = conn.execute(
    f"SELECT tweet_id FROM tweets WHERE tweet_id IN ({placeholders}) AND fetched_at >= ?",
    (*tweet_ids, cutoff)).fetchall()
  recent = {r["tweet_id"] for r in rows}
  remaining = [tid for tid in tweet_ids if tid not in recent]
  if remaining:
    want = set(remaining)
    for r in conn.execute("SELECT raw_json FROM tweets WHERE fetched_at >= ?", (cutoff,)).fetchall():
      try:
        qt = json.loads(r["raw_json"]).get("quoted_tweet")
        if qt and qt.get("id") in want: recent.add(qt["id"])
      except (json.JSONDecodeError, TypeError): pass
  return len([tid for tid in tweet_ids if tid not in recent])

def post_read_cost(conn, tweet_ids, now=None):
  from app.fetch.client import COST_PER_POST_READ
  return billable_post_count(conn, tweet_ids, now=now) * COST_PER_POST_READ

def billable_user_lookup(conn, account_id, now=None):
  """User lookup is billed once per account within 24h."""
  now = now or datetime.now(timezone.utc)
  cutoff = _utc_cutoff(now)
  row = conn.execute(
    "SELECT 1 FROM api_calls WHERE account_id = ? AND endpoint = 'users/by/username' AND cost_usd > 0 AND called_at >= ?",
    (account_id, cutoff)).fetchone()
  return row is None

def record_api_call(conn, account_id, endpoint, units, cost_usd):
  conn.execute("INSERT INTO api_calls (account_id, endpoint, units, cost_usd) VALUES (?, ?, ?, ?)",
    (account_id, endpoint, units, cost_usd)); conn.commit()

def cost_for_account(conn, account_id, since=None):
  q = "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM api_calls WHERE account_id = ?"; params = [account_id]
  if since: q += " AND called_at >= ?"; params.append(since)
  return conn.execute(q, params).fetchone()["c"]

def total_api_cost(conn, since=None):
  """Sum of recorded api_calls.cost_usd, optionally since a timestamp (UTC SQLite datetime)."""
  q = "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM api_calls"; params = []
  if since: q += " WHERE called_at >= ?"; params.append(since)
  return conn.execute(q, params).fetchone()["c"]

def month_start_utc(now=None):
  now = now or datetime.now(timezone.utc)
  return now.strftime("%Y-%m-01 00:00:00")

# --- editions (weekly newsletter snapshots) ---

def save_edition(conn, account_id, week_start, week_end, items, cost_usd):
  conn.execute(
    """INSERT INTO editions (account_id, week_start, week_end, item_count, cost_usd, content_json)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(account_id, week_start) DO UPDATE SET
         week_end = excluded.week_end, item_count = excluded.item_count,
         cost_usd = excluded.cost_usd, content_json = excluded.content_json,
         built_at = datetime('now')""",
    (account_id, week_start, week_end, len(items), cost_usd, json.dumps(items)))
  conn.commit()

def list_editions(conn, account_id=None):
  q = """SELECT e.*, a.handle, a.display_name FROM editions e JOIN accounts a ON a.id = e.account_id"""
  params = []
  if account_id is not None: q += " WHERE e.account_id = ?"; params.append(account_id)
  q += " ORDER BY e.week_start DESC"
  return [dict(r) for r in conn.execute(q, params).fetchall()]

def get_edition(conn, edition_id):
  row = conn.execute(
    "SELECT e.*, a.handle, a.display_name FROM editions e JOIN accounts a ON a.id = e.account_id WHERE e.id = ?",
    (edition_id,)).fetchone()
  return dict(row) if row else None

def latest_edition(conn, account_id):
  rows = list_editions(conn, account_id)
  return rows[0] if rows else None

# --- oauth session (single owner) ---

def save_oauth_session(conn, x_user_id, access_token, refresh_token=None, expires_at=None):
  conn.execute(
    """INSERT INTO oauth_session (id, x_user_id, access_token, refresh_token, expires_at, updated_at)
       VALUES (1, ?, ?, ?, ?, datetime('now'))
       ON CONFLICT(id) DO UPDATE SET
         x_user_id = excluded.x_user_id, access_token = excluded.access_token,
         refresh_token = COALESCE(excluded.refresh_token, oauth_session.refresh_token),
         expires_at = COALESCE(excluded.expires_at, oauth_session.expires_at),
         updated_at = datetime('now')""",
    (x_user_id, access_token, refresh_token, expires_at))
  conn.commit()

def get_oauth_session(conn):
  row = conn.execute("SELECT * FROM oauth_session WHERE id = 1").fetchone()
  return dict(row) if row else None

# --- liked tweets (owner actions) ---

def is_tweet_liked(conn, tweet_id):
  return conn.execute("SELECT 1 FROM liked_tweets WHERE tweet_id = ?", (tweet_id,)).fetchone() is not None

def mark_tweet_liked(conn, tweet_id):
  conn.execute("INSERT OR IGNORE INTO liked_tweets (tweet_id) VALUES (?)", (tweet_id,)); conn.commit()

# --- read tweets (owner marked as read in the UI) ---

def is_tweet_read(conn, tweet_id):
  return conn.execute("SELECT 1 FROM read_tweets WHERE tweet_id = ?", (tweet_id,)).fetchone() is not None

def mark_tweet_read(conn, tweet_id):
  conn.execute("INSERT OR IGNORE INTO read_tweets (tweet_id) VALUES (?)", (tweet_id,)); conn.commit()

def mark_tweet_unread(conn, tweet_id):
  conn.execute("DELETE FROM read_tweets WHERE tweet_id = ?", (tweet_id,)); conn.commit()

def read_tweet_ids(conn, tweet_ids=None):
  """Return the set of tweet IDs the owner has marked read. Optionally filter to tweet_ids."""
  if tweet_ids is not None:
    if not tweet_ids: return set()
    placeholders = ",".join("?" * len(tweet_ids))
    rows = conn.execute(
      f"SELECT tweet_id FROM read_tweets WHERE tweet_id IN ({placeholders})", tuple(tweet_ids)).fetchall()
  else:
    rows = conn.execute("SELECT tweet_id FROM read_tweets").fetchall()
  return {r["tweet_id"] for r in rows}

# --- read newsletters (hide account card for that week) ---

def is_newsletter_read(conn, account_id, week_start):
  return conn.execute(
    "SELECT 1 FROM read_newsletters WHERE account_id = ? AND week_start = ?",
    (account_id, week_start)).fetchone() is not None

def mark_newsletter_read(conn, account_id, week_start):
  conn.execute(
    "INSERT OR IGNORE INTO read_newsletters (account_id, week_start) VALUES (?, ?)",
    (account_id, week_start)); conn.commit()

# --- like queue (background pacing) ---

def enqueue_like(conn, tweet_id):
  conn.execute("INSERT OR IGNORE INTO like_queue (tweet_id) VALUES (?)", (tweet_id,)); conn.commit()

def is_tweet_queued(conn, tweet_id):
  return conn.execute("SELECT 1 FROM like_queue WHERE tweet_id = ?", (tweet_id,)).fetchone() is not None

def peek_like_queue(conn):
  row = conn.execute("SELECT tweet_id FROM like_queue ORDER BY id LIMIT 1").fetchone()
  return row["tweet_id"] if row else None

def dequeue_like(conn, tweet_id):
  conn.execute("DELETE FROM like_queue WHERE tweet_id = ?", (tweet_id,)); conn.commit()

def like_queue_size(conn):
  return conn.execute("SELECT COUNT(*) AS c FROM like_queue").fetchone()["c"]

def liked_tweet_count(conn, account_id):
  return conn.execute(
    """SELECT COUNT(*) AS c FROM tweets t
       INNER JOIN liked_tweets l ON l.tweet_id = t.tweet_id
       WHERE t.account_id = ?""", (account_id,)).fetchone()["c"]

def queued_like_count(conn, account_id):
  return conn.execute(
    """SELECT COUNT(*) AS c FROM tweets t
       INNER JOIN like_queue q ON q.tweet_id = t.tweet_id
       WHERE t.account_id = ?""", (account_id,)).fetchone()["c"]

# --- overview (CLI status) ---

def edition_for_week(conn, account_id, week_start):
  row = conn.execute(
    "SELECT * FROM editions WHERE account_id = ? AND week_start = ?", (account_id, week_start)).fetchone()
  return dict(row) if row else None

def previous_edition(conn, account_id, before_week_start):
  """Most recent edition for this account with week_start strictly before before_week_start."""
  row = conn.execute(
    """SELECT * FROM editions WHERE account_id = ? AND week_start < ?
       ORDER BY week_start DESC LIMIT 1""", (account_id, before_week_start)).fetchone()
  return dict(row) if row else None

def database_overview(conn, week_start=None, week_end=None):
  """Summary stats for CLI status. Per-account newsletter stats use the latest edition."""
  if week_start is None or week_end is None:
    from app.fetch.runner import period_bounds
    s = get_app_settings(conn)
    week_start, week_end = period_bounds(cadence=s["cadence"])
  accounts = []
  for a in list_accounts(conn, active_only=False):
    tweet_count = conn.execute("SELECT COUNT(*) AS c FROM tweets WHERE account_id = ?", (a["id"],)).fetchone()["c"]
    edition = latest_edition(conn, a["id"])
    if edition:
      ed_ws, ed_we = edition["week_start"], edition["week_end"]
      tweets_in_week = len(tweets_for_week(conn, a["id"], ed_ws, ed_we))
      edition_items = edition["item_count"]
    else:
      ed_ws = ed_we = None
      tweets_in_week = len(tweets_for_week(conn, a["id"], week_start, week_end))
      edition_items = None
    accounts.append({
      "id": a["id"], "handle": a["handle"], "display_name": a["display_name"], "active": bool(a["active"]),
      "tweet_count": tweet_count, "tweets_in_week": tweets_in_week,
      "edition_week_start": ed_ws, "edition_week_end": ed_we,
      "liked_count": liked_tweet_count(conn, a["id"]),
      "queued_like_count": queued_like_count(conn, a["id"]),
      "followed": bool(a.get("followed_at")),
      "edition_items": edition_items,
      "edition_cost_usd": edition["cost_usd"] if edition else None,
      "total_cost_usd": cost_for_account(conn, a["id"]),
    })
  totals = conn.execute(
    """SELECT
         (SELECT COUNT(*) FROM accounts WHERE active = 1) AS active_accounts,
         (SELECT COUNT(*) FROM accounts WHERE active = 0) AS inactive_accounts,
         (SELECT COUNT(*) FROM tweets) AS tweets,
         (SELECT COUNT(*) FROM editions) AS editions,
         (SELECT COALESCE(SUM(cost_usd), 0) FROM api_calls) AS api_cost_usd""").fetchone()
  return {
    "week_start": week_start, "week_end": week_end,
    "accounts": accounts,
    "active_accounts": totals["active_accounts"],
    "inactive_accounts": totals["inactive_accounts"],
    "tweet_count": totals["tweets"],
    "edition_count": totals["editions"],
    "api_cost_usd": totals["api_cost_usd"],
    "like_queue_size": like_queue_size(conn),
    "pending_follow_count": pending_follow_count(conn),
    "oauth_signed_in": get_oauth_session(conn) is not None,
  }
