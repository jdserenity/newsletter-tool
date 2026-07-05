import os

from app.env import load_env

def test_load_env_reads_dotenv_file(tmp_path, monkeypatch):
  env_file = tmp_path / ".env"
  env_file.write_text("X_BEARER_TOKEN=from-dotenv\n")
  monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
  load_env(dotenv_path=env_file)
  assert os.environ["X_BEARER_TOKEN"] == "from-dotenv"

def test_load_env_does_not_override_existing_env(tmp_path, monkeypatch):
  env_file = tmp_path / ".env"
  env_file.write_text("X_BEARER_TOKEN=from-dotenv\n")
  monkeypatch.setenv("X_BEARER_TOKEN", "already-set")
  load_env(dotenv_path=env_file)
  assert os.environ["X_BEARER_TOKEN"] == "already-set"
