import json
import os
import sqlite3
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
  if "digests" not in tables: return
  if "editions" not in tables:
    conn.execute("ALTER TABLE digests RENAME TO editions")
  else:
    conn.execute("INSERT OR IGNORE INTO editions SELECT * FROM digests")
    conn.execute("DROP TABLE digests")
  conn.commit()

# --- accounts ---

def add_account(conn, handle):
  handle = handle.lstrip("@").strip()
  cur = conn.execute("INSERT INTO accounts (handle) VALUES (?)", (handle,)); conn.commit()
  return cur.lastrowid

def remove_account(conn, account_id):
  conn.execute("UPDATE accounts SET active = 0 WHERE id = ?", (account_id,)); conn.commit()

def list_accounts(conn, active_only=True):
  q = "SELECT * FROM accounts" + (" WHERE active = 1" if active_only else "") + " ORDER BY handle"
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

# --- tweets ---

def save_tweets(conn, account_id, tweets):
  for t in tweets:
    conn.execute(
      "INSERT OR IGNORE INTO tweets (account_id, tweet_id, kind, text, created_at, raw_json) VALUES (?, ?, ?, ?, ?, ?)",
      (account_id, t["id"], t.get("kind", "post"), t["text"], t["created_at"], json.dumps(t)))
  conn.commit()

def tweets_for_week(conn, account_id, week_start, week_end):
  rows = conn.execute(
    "SELECT * FROM tweets WHERE account_id = ? AND created_at >= ? AND created_at < ? ORDER BY created_at",
    (account_id, week_start, week_end)).fetchall()
  return [dict(r) for r in rows]

# --- api calls / cost ---

def record_api_call(conn, account_id, endpoint, units, cost_usd):
  conn.execute("INSERT INTO api_calls (account_id, endpoint, units, cost_usd) VALUES (?, ?, ?, ?)",
    (account_id, endpoint, units, cost_usd)); conn.commit()

def cost_for_account(conn, account_id, since=None):
  q = "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM api_calls WHERE account_id = ?"; params = [account_id]
  if since: q += " AND called_at >= ?"; params.append(since)
  return conn.execute(q, params).fetchone()["c"]

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

def save_oauth_session(conn, x_user_id, access_token, refresh_token=None):
  conn.execute(
    """INSERT INTO oauth_session (id, x_user_id, access_token, refresh_token, updated_at) VALUES (1, ?, ?, ?, datetime('now'))
       ON CONFLICT(id) DO UPDATE SET
         x_user_id = excluded.x_user_id, access_token = excluded.access_token,
         refresh_token = COALESCE(excluded.refresh_token, oauth_session.refresh_token),
         updated_at = datetime('now')""",
    (x_user_id, access_token, refresh_token))
  conn.commit()

def get_oauth_session(conn):
  row = conn.execute("SELECT * FROM oauth_session WHERE id = 1").fetchone()
  return dict(row) if row else None

# --- liked tweets (owner actions) ---

def is_tweet_liked(conn, tweet_id):
  return conn.execute("SELECT 1 FROM liked_tweets WHERE tweet_id = ?", (tweet_id,)).fetchone() is not None

def mark_tweet_liked(conn, tweet_id):
  conn.execute("INSERT OR IGNORE INTO liked_tweets (tweet_id) VALUES (?)", (tweet_id,)); conn.commit()

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
