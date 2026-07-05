#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
venv/bin/python -m pip install -e ".[dev]"
echo "Ready. Run: source venv/bin/activate && news-dev"
