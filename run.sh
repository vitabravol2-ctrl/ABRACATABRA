#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-app}"
shift || true
cd "$APP_DIR"

if [[ -f package.json ]]; then
  npm install
  npm start -- "$@"
elif [[ -f requirements.txt ]]; then
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  python3 main.py "$@"
elif [[ -f Cargo.toml ]]; then
  cargo run -- "$@"
elif [[ -f go.mod ]]; then
  go run . "$@"
else
  echo "Unsupported project type. Add your run command to run.sh."
  exit 1
fi
