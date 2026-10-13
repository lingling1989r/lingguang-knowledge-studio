#!/bin/zsh
set -e
TASK_SITE_ROOT="$(cd -- "$(dirname "$0")" && pwd)"
cd "$TASK_SITE_ROOT"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
export STUDIO_PORT="${STUDIO_PORT:-8765}"
exec python3 -m uvicorn app.server:app --host 127.0.0.1 --port "$STUDIO_PORT" --log-level info
