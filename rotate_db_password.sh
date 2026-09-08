#!/usr/bin/env bash
# Rotate the Railway Postgres password for the "jubilant-mindfulness" project.
#
# Why this order: POSTGRES_PASSWORD is only honoured by the Postgres image at
# initdb time, so setting the variable does NOT change the live password. The
# real change is ALTER USER; the variables are then brought back in sync.
#
# Expect ~1-2 min where Macro-Tracker and workout-tracker cannot reach the DB,
# between the ALTER and their redeploys finishing. The data is untouched.
#
# Usage:  bash rotate_db_password.sh           # also moves Macro-Tracker internal
#         bash rotate_db_password.sh --public  # keep it on the public proxy
set -euo pipefail

# The Railway CLI resolves the project from the working directory, so anchor
# to the linked project regardless of where this script is invoked from.
PROJECT_DIR="/Users/jessegoranson/Documents/AI Data/Macro Tracker App"
cd "$PROJECT_DIR" || { echo "✗ project dir not found: $PROJECT_DIR"; exit 1; }
DBENV="${DBENV:-$HOME/MacroTrackerBackups/.dbenv}"
: "${DBENV:?internal error: DBENV unset}"
USE_INTERNAL=1                      # internal host by default
[ "${1:-}" = "--public" ] && USE_INTERNAL=0
DRY=0
for a in "$@"; do [ "$a" = "--dry-run" ] && DRY=1; done
run() { if [ "$DRY" = "1" ]; then echo "      [dry-run] $*" | cut -c1-110; else "$@"; fi; }

command -v railway >/dev/null || { echo "✗ railway CLI not found"; exit 1; }
command -v psql    >/dev/null || { echo "✗ psql not found"; exit 1; }

# ── Current password, read from Railway (never hardcoded here) ───────────────
OLD=$(railway variables --service Postgres --kv | sed -n 's/^PGPASSWORD=//p')
[ -n "$OLD" ] || { echo "✗ could not read current PGPASSWORD"; exit 1; }

PUB_HOST=mainline.proxy.rlwy.net; PUB_PORT=55642
INT_HOST=postgres.railway.internal; INT_PORT=5432

# ── Generate the new password locally: 32 URL-safe chars, no shell/URL metachars
# NOTE: do NOT use `tr </dev/urandom | head -c 32` here — head closes the
# pipe, tr takes SIGPIPE (141), and pipefail+errexit kill the script silently.
NEW=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32)))")
[ ${#NEW} -eq 32 ] || { echo "password generation failed"; exit 1; }
echo "→ Generated a new 32-character password (not printed)."

# ── Pre-flight: confirm we can reach the DB with the old password ────────────
echo "→ Verifying current credentials…"
PGPASSWORD="$OLD" psql -h $PUB_HOST -p $PUB_PORT -U postgres -d railway \
  -tAc 'select 1' >/dev/null || { echo "✗ cannot connect with current password"; exit 1; }
echo "  ✓ connected"

# ── 1. The actual rotation ───────────────────────────────────────────────────
echo "→ ALTER USER postgres…"
# psql does NOT interpolate :'var' inside a -c string (only for input read from
# stdin or a file), which is why the previous form was sent to the server
# literally. Inline the value instead. That is safe here *because* NEW is
# asserted to be exactly 32 chars of [A-Za-z0-9] — no quote or backslash can
# appear in it.
case "$NEW" in
  *[!A-Za-z0-9]*) echo "✗ generated password has unexpected characters"; exit 1 ;;
esac
run env PGPASSWORD="$OLD" psql -h $PUB_HOST -p $PUB_PORT -U postgres -d railway \
  -v ON_ERROR_STOP=1 -c "ALTER ROLE postgres WITH PASSWORD '$NEW';"
echo "  ✓ live password changed"

# ── 2. Re-sync every consumer ────────────────────────────────────────────────
echo "→ Updating Postgres service variables…"
run railway variables --service Postgres \
  --set "PGPASSWORD=$NEW" \
  --set "POSTGRES_PASSWORD=$NEW" \
  --set "DATABASE_URL=postgresql://postgres:$NEW@$INT_HOST:$INT_PORT/railway" \
  --set "DATABASE_PUBLIC_URL=postgresql://postgres:$NEW@$PUB_HOST:$PUB_PORT/railway" >/dev/null

if [ "$USE_INTERNAL" = "1" ]; then
  MT_URL="postgresql://postgres:$NEW@$INT_HOST:$INT_PORT/railway"
  echo "→ Updating Macro-Tracker (moving to internal host)…"
else
  MT_URL="postgresql://postgres:$NEW@$PUB_HOST:$PUB_PORT/railway"
  echo "→ Updating Macro-Tracker…"
fi
run railway variables --service Macro-Tracker --set "DATABASE_URL=$MT_URL" >/dev/null

echo "→ Updating workout-tracker…"
run railway variables --service workout-tracker \
  --set "DATABASE_URL=postgresql://postgres:$NEW@$INT_HOST:$INT_PORT/railway" >/dev/null

# ── 3. Local backup credentials ──────────────────────────────────────────────
if [ "$DRY" = "1" ]; then
  echo "→ Updating $DBENV…"
  echo "      [dry-run] would rewrite $DBENV (left untouched)"
elif [ -f "$DBENV" ]; then
  echo "-> Updating $DBENV"
  cp "$DBENV" "$DBENV.bak.$(date +%Y%m%d%H%M%S)"
  # Replace the old password wherever it appears (PGPASSWORD= and inside a URL)
  python3 - "$DBENV" "$OLD" "$NEW" <<'PY'
import sys
path, old, new = sys.argv[1:4]
with open(path) as f: s = f.read()
open(path, "w").write(s.replace(old, new))
PY
  chmod 600 "$DBENV"
  echo "  ✓ updated (old copy kept as .bak.*, delete once backups are verified)"
else
  echo "  ! $DBENV not found — update your backup credentials manually"
fi

# ── 4. Verify ────────────────────────────────────────────────────────────────
if [ "$DRY" = "1" ]; then
  echo
  echo "✓ Dry run complete — nothing was changed. Re-run without --dry-run to apply."
  exit 0
fi

echo "→ Verifying new password…"
PGPASSWORD="$NEW" psql -h $PUB_HOST -p $PUB_PORT -U postgres -d railway \
  -tAc "select 'rows in mt_ingredients: '||count(*) from mt_ingredients;"

echo "→ Confirming the OLD password no longer works…"
if PGPASSWORD="$OLD" psql -h $PUB_HOST -p $PUB_PORT -U postgres -d railway \
     -tAc 'select 1' >/dev/null 2>&1; then
  echo "  ✗ WARNING: old password still accepted — investigate before trusting this"
  exit 1
else
  echo "  ✓ old password rejected"
fi

echo
echo "✓ Rotation complete."
echo "  Next: wait ~1 min for the two services to redeploy, then load the app"
echo "  and run:  bash ~/MacroTrackerBackups/backup.sh"
