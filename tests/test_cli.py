from app.cli import dev

def test_dev_loads_env_and_starts_uvicorn(monkeypatch):
  load_calls = []
  monkeypatch.setattr("app.env.load_env", lambda **kw: load_calls.append(kw))
  uvicorn_calls = []
  def fake_run(*args, **kwargs):
    uvicorn_calls.append((args, kwargs))
  import uvicorn
  monkeypatch.setattr(uvicorn, "run", fake_run)
  dev()
  assert load_calls == [{}]
  assert uvicorn_calls == [(("app.main:app",), {"reload": True})]
