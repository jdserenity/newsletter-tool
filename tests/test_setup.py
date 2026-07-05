import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def test_setup_script_installs_editable_package():
  r = subprocess.run(["bash", str(ROOT / "scripts" / "setup.sh")], cwd=ROOT, capture_output=True, text=True)
  assert r.returncode == 0, r.stderr + r.stdout
