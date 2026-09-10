#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -f config.json ]]; then
  echo "Missing config.json — copy config.example.json and add your Jira API token."
  exit 1
fi

if ! python3 -c "import requests" >/dev/null 2>&1; then
  python3 -m pip install -r requirements.txt
fi

MONTH="${1:-$(date +%Y-%m)}"
AUTHOR="${2:-}"

ARGS=(--month "$MONTH" --serve)
if [[ -n "$AUTHOR" ]]; then
  ARGS=(--month "$MONTH" --author "$AUTHOR" --serve)
fi

python3 generate_dashboard.py "${ARGS[@]}"
