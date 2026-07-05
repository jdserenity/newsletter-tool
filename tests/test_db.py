from pathlib import Path

from app import db
from tests.conftest import make_tweet

def test_resolve_db_path_default(monkeypatch):
  monkeypatch.delenv("DATABASE_PATH", raising=False)
  assert db.resolve_db_path() == db.DEFAULT_DB_PATH

def test_resolve_db_path_from_env(monkeypatch, tmp_path):
  monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "custom.db"))
  assert db.resolve_db_path() == tmp_path / "custom.db"

def test_resolve_db_path_override_beats_env(monkeypatch):
  monkeypatch.setenv("DATABASE_PATH", "/other/path.db")
  assert db.resolve_db_path("/override.db") == Path("/override.db")

def test_connect_uses_database_path_env(monkeypatch, tmp_path):
  db_file = tmp_path / "env.db"
  monkeypatch.setenv("DATABASE_PATH", str(db_file))
  c = db.connect()
  db.add_account(c, "alice")
  assert db_file.exists()
  assert db.get_account(c, handle="alice")["handle"] == "alice"

def test_add_and_list_accounts(conn):
  db.add_account(conn, "@alice")
  accounts = db.list_accounts(conn)
  assert len(accounts) == 1; assert accounts[0]["handle"] == "alice"  # @ stripped

def test_remove_account_deactivates(conn):
  aid = db.add_account(conn, "alice")
  db.remove_account(conn, aid)
  assert db.list_accounts(conn) == []
  assert db.get_account(conn, account_id=aid)["active"] == 0  # history preserved

def test_default_settings(conn):
  aid = db.add_account(conn, "alice")
  a = db.get_account(conn, account_id=aid)
  assert a["include_quotes"] == 1; assert a["include_replies"] == 0; assert a["include_retweets"] == 0

def test_update_settings(conn):
  aid = db.add_account(conn, "alice")
  db.update_settings(conn, aid, include_quotes=False, include_retweets=True)
  a = db.get_account(conn, account_id=aid)
  assert a["include_quotes"] == 0; assert a["include_retweets"] == 1

def test_save_tweets_dedupes(conn):
  aid = db.add_account(conn, "alice")
  t = {"id": "1", "text": "hi", "created_at": "2026-06-30T12:00:00Z"}
  db.save_tweets(conn, aid, [t]); db.save_tweets(conn, aid, [t])
  rows = db.tweets_for_week(conn, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z")
  assert len(rows) == 1

def test_cost_for_account(conn):
  aid = db.add_account(conn, "alice")
  db.record_api_call(conn, aid, "users/:id/tweets", 10, 0.05)
  db.record_api_call(conn, aid, "users/by/username", 1, 0.01)
  assert abs(db.cost_for_account(conn, aid) - 0.06) < 1e-9

def test_save_edition_upserts_per_week(conn):
  aid = db.add_account(conn, "alice")
  db.save_edition(conn, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", [{"a": 1}], 0.05)
  db.save_edition(conn, aid, "2026-06-29T00:00:00Z", "2026-07-06T00:00:00Z", [{"a": 1}, {"b": 2}], 0.07)
  editions = db.list_editions(conn, aid)
  assert len(editions) == 1; assert editions[0]["item_count"] == 2; assert editions[0]["cost_usd"] == 0.07

def test_edition_for_week(conn):
  aid = db.add_account(conn, "alice")
  db.save_edition(conn, aid, "2026-06-22T00:00:00Z", "2026-06-29T00:00:00Z", [{"a": 1}], 0.05)
  assert db.edition_for_week(conn, aid, "2026-06-22T00:00:00Z")["item_count"] == 1
  assert db.edition_for_week(conn, aid, "2026-06-29T00:00:00Z") is None

def test_database_overview_reports_missing_edition(conn):
  from app.fetch.runner import week_bounds
  ws, we = week_bounds()
  aid = db.add_account(conn, "alice")
  db.save_tweets(conn, aid, [{"id": "1", "text": "hi", "created_at": "2026-06-23T12:00:00Z", "kind": "post"}])
  o = db.database_overview(conn, ws, we)
  assert o["accounts"][0]["edition_items"] is None
  assert o["accounts"][0]["tweets_in_week"] == 1
  db.save_edition(conn, aid, ws, we, [{"tweet_id": "1"}], 0.01)
  o = db.database_overview(conn, ws, we)
  assert o["accounts"][0]["edition_items"] == 1

def test_migrate_digests_table_to_editions(tmp_path):
  import sqlite3
  path = tmp_path / "legacy.db"
  c = sqlite3.connect(str(path))
  c.executescript("""
    CREATE TABLE digests (
      id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, week_start TEXT NOT NULL,
      week_end TEXT NOT NULL, item_count INTEGER NOT NULL, cost_usd REAL NOT NULL DEFAULT 0,
      content_json TEXT NOT NULL, built_at TEXT NOT NULL DEFAULT (datetime('now')),
      UNIQUE(account_id, week_start)
    );
  """)
  c.commit(); c.close()
  conn = db.connect(str(path))
  tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
  assert "editions" in tables; assert "digests" not in tables
