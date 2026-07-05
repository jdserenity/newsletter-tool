from app.cli import dev, fetch

def test_dev_starts_uvicorn_with_reload(monkeypatch):
  uvicorn_calls = []
  def fake_run(*args, **kwargs):
    uvicorn_calls.append((args, kwargs))
  import uvicorn
  monkeypatch.setattr(uvicorn, "run", fake_run)
  dev()
  assert uvicorn_calls == [(("app.main:create_app",), {"factory": True, "reload": True})]

def test_fetch_runs_weekly_fetch_and_drains_queue(monkeypatch, capsys):
  calls = {"fetch": 0, "drain": 0}
  class FakeConn:
    def close(self): pass
  monkeypatch.setattr("app.env.load_env", lambda: None)
  monkeypatch.setattr("app.db.resolve_db_path", lambda: "/tmp/news.db")
  monkeypatch.setattr("app.db.connect", lambda path=None: FakeConn())
  monkeypatch.setattr("app.db.like_queue_size", lambda conn: 2)
  monkeypatch.setattr("app.fetch.runner.run_weekly_fetch", lambda conn: (calls.__setitem__("fetch", calls["fetch"] + 1) or [("alice", 0.015)]))
  monkeypatch.setattr("app.user_actions.drain_like_queue", lambda *a, **k: (calls.__setitem__("drain", calls["drain"] + 1) or 2))
  fetch()
  out = capsys.readouterr().out
  assert calls == {"fetch": 1, "drain": 1}
  assert "alice: $0.015" in out
  assert "Draining 2 queued likes" in out
  assert "Liked 2 tweets." in out

def test_fetch_reports_empty_accounts(monkeypatch, capsys):
  class FakeConn:
    def close(self): pass
  monkeypatch.setattr("app.env.load_env", lambda: None)
  monkeypatch.setattr("app.db.resolve_db_path", lambda: "/tmp/news.db")
  monkeypatch.setattr("app.db.connect", lambda path=None: FakeConn())
  monkeypatch.setattr("app.db.like_queue_size", lambda conn: 0)
  monkeypatch.setattr("app.fetch.runner.run_weekly_fetch", lambda conn: [])
  fetch()
  assert "No active accounts." in capsys.readouterr().out
