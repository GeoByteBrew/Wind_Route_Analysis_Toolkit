#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f backend/data/roads.geojson ]]; then
  .venv/bin/python scripts/generate_sample_data.py
fi

exec .venv/bin/uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
