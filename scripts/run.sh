#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f backend/data/sample_montpellier_lyon.kmz ]]; then
  echo "Missing backend/data/sample_montpellier_lyon.kmz"
  exit 1
fi

exec .venv/bin/uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
