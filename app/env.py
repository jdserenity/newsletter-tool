"""Load .env from the repo root into os.environ (does not override existing vars)."""
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

def load_env(dotenv_path=None):
  load_dotenv(dotenv_path or REPO_ROOT / ".env")
