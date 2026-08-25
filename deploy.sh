#!/bin/bash
# deploy.sh — commit everything and push to Railway in one command.
# Usage:  ./deploy.sh
#         ./deploy.sh "optional commit message"

set -e
cd "$(dirname "$0")"

# ── Pre-flight: catch import errors BEFORE they become a failed deploy ───────
# Railway runs `uvicorn app.main:app`; if that import fails the container dies
# and the deploy is rejected. Reproduce that exact check locally first.
PY313="$(command -v python3.13 || command -v python3.12 || true)"
if [ -n "$PY313" ]; then
  echo "→ Checking backend imports…"
  if ! (cd backend && DATABASE_URL="postgresql+asyncpg://u:p@localhost/db" \
        "$PY313" -c "import sys; sys.path.insert(0,'.'); import app.main" 2>/tmp/mt_import_err); then
    echo "✗ BACKEND IMPORT FAILED — not deploying:"
    tail -5 /tmp/mt_import_err
    exit 1
  fi
  echo "  ✓ backend imports OK"
else
  echo "  ! python3.12+ not found — skipping import check"
fi

# ── Pre-flight: frontend must build ──────────────────────────────────────────
if [ -d frontend/node_modules ]; then
  echo "→ Building frontend…"
  if ! (cd frontend && npm run build >/tmp/mt_build.log 2>&1); then
    echo "✗ FRONTEND BUILD FAILED — not deploying:"
    tail -12 /tmp/mt_build.log
    exit 1
  fi
  echo "  ✓ frontend builds OK"
fi

# Clear any stale git locks left by the AI sandbox
rm -f .git/HEAD.lock .git/index.lock .git/MERGE_HEAD.lock .git/CHERRY_PICK_HEAD.lock

# Stage all tracked + untracked changes
git add -A

# Nothing to do?
if git diff --cached --quiet; then
  echo "✓ Nothing to commit — already up to date."
  git push
  exit 0
fi

# Commit message: use arg if provided, else auto-generate with timestamp
MSG="${1:-"Update $(date '+%Y-%m-%d %H:%M')"}"
git commit -m "$MSG"

# Push
git push

echo "✓ Deployed."
