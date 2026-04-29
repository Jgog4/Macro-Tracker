#!/bin/bash
# deploy.sh — commit everything and push to Railway in one command.
# Usage:  ./deploy.sh
#         ./deploy.sh "optional commit message"

set -e
cd "$(dirname "$0")"

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
