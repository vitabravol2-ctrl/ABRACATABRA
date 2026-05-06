#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${1:-}"
if [[ -z "$REPO_URL" ]]; then
  echo "Usage: ./download.sh <github_repo_url> [target_dir]"
  exit 1
fi
TARGET_DIR="${2:-app}"
git clone "$REPO_URL" "$TARGET_DIR"
