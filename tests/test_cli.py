from app.cli import dev

def test_dev_starts_uvicorn_with_reload(monkeypatch):
  uvicorn_calls = []
  def fake_run(*args, **kwargs):
    uvicorn_calls.append((args, kwargs))
  import uvicorn
  monkeypatch.setattr(uvicorn, "run", fake_run)
  dev()
  assert uvicorn_calls == [(("app.main:app",), {"reload": True})]
