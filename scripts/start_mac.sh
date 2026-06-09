#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi

if ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import flask
import flask_socketio
import requests
PY
then
  .venv/bin/pip install --upgrade pip flask flask-socketio requests
fi

export APPDATA="${APPDATA:-$HOME/Library/Application Support}"
exec .venv/bin/python app.py --web "$@"
