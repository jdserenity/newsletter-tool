from app.cli import db_status, dev, fetch

def test_dev_starts_uvicorn_with_reload(monkeypatch):
  uvicorn_calls = []
  def fake_run(*args, **kwargs):
    uvicorn_calls.append((args, kwargs))
  import uvicorn
  monkeypatch.setattr(uvicorn, "run", fake_run)
  dev()
  assert uvicorn_calls == [(("app.main:create_app",), {"factory": True, "reload": True})]

def test_fetch_runs_weekly_fetch(monkeypatch, capsys):
  calls = {"fetch": 0}
  class FakeConn:
    def close(self): pass
  monkeypatch.setattr("app.env.load_env", lambda: None)
  monkeypatch.setattr("app.db.resolve_db_path", lambda: "/tmp/news.db")
  monkeypatch.setattr("app.db.connect", lambda path=None: FakeConn())
  monkeypatch.setattr("app.fetch.runner.run_weekly_fetch", lambda conn: (calls.__setitem__("fetch", calls["fetch"] + 1) or [("alice", 0.015)]))
  fetch()
  out = capsys.readouterr().out
  assert calls == {"fetch": 1}
  assert "alice: $0.015" in out
  assert "Draining" not in out

def test_fetch_reports_empty_accounts(monkeypatch, capsys):
  class FakeConn:
    def close(self): pass
  monkeypatch.setattr("app.env.load_env", lambda: None)
  monkeypatch.setattr("app.db.resolve_db_path", lambda: "/tmp/news.db")
  monkeypatch.setattr("app.db.connect", lambda path=None: FakeConn())
  monkeypatch.setattr("app.fetch.runner.run_weekly_fetch", lambda conn: [])
  fetch()
  assert "No active accounts." in capsys.readouterr().out

def test_db_status_prints_overview(monkeypatch, capsys):
  class FakeConn:
    def close(self): pass
  overview = {
    "week_start": "2026-06-22T00:00:00Z", "week_end": "2026-06-29T00:00:00Z",
    "tweet_count": 5, "edition_count": 2, "api_cost_usd": 0.065,
    "oauth_signed_in": True, "accounts": [
      {"handle": "karpathy", "display_name": "Andrej Karpathy", "active": True,
       "tweet_count": 5, "tweets_in_week": 1, "edition_week_start": "2026-06-22T00:00:00Z",
       "edition_week_end": "2026-06-29T00:00:00Z", "edition_items": 1, "liked_count": 3,
       "disliked_count": 1, "total_cost_usd": 0.015},
    ],
  }
  monkeypatch.setattr("app.cli._open_db", lambda: ("/tmp/news.db", FakeConn()))
  monkeypatch.setattr("app.db.database_overview", lambda conn: overview)
  db_status()
  out = capsys.readouterr().out
  assert "Database: /tmp/news.db" in out
  assert "@karpathy" in out
  assert "1 tweets · 1 in newsletter (2026-06-22)" in out
  assert "3 liked · 1 disliked" in out
