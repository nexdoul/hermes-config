#!/bin/bash
# retitle-backfill payload — backfill Chinese titles into organized 115 dirs.
#
# Idempotent and self-terminating, which is what makes a completion marker
# trustworthy: a file that already carries its title is skipped, so re-running
# never renames anything twice; and when no file is left to title, the run
# exits 0 and the wrapper records state=done.
#
# Slice: one batch per invocation, bounded by --limit, so a container restart
# cannot lose more than the batch in flight.  The next relaunch continues from
# the durable state.
#
# Exit codes: 0 nothing left to do (or a batch completed) -> done
#             2 the run had failures -> retry, then exhausted
set -u

PROJECT=/home/hatch/code/javdb
DAILY="$PROJECT/115DailyOrg"
PY=/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/venv/bin/python

export JAVDB_ENV_ROOT="$PROJECT/env"
export JAVDB_115_CLI="$PROJECT/env/bin/115driver"
export JAVDB_115_BATCH_CLI="$PROJECT/env/bin/115driver-batch"
export PYTHONPATH="$PROJECT/115DailyOrg/_shared:$PROJECT/115DailyOrg/_internal:$PROJECT/115re:$PROJECT/115re/_internal:$PROJECT/115pan:$PROJECT/115pan/_internal"

STATE_DIR="$PROJECT/runtime/dailyorg"
LOG="$PROJECT/logs/task-retitle-backfill.log"
BATCH_LOG_DIR="$PROJECT/logs/task-retitle-batches"
mkdir -p "$STATE_DIR" "$(dirname "$LOG")" "$BATCH_LOG_DIR"

# Directories to sweep, from the organized-dirs registry.  Read-only, so a
# misconfigured entry says so instead of half-scanning an account.
mapfile -t DIRS < <(python3 - "$STATE_DIR" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]) / "state" / "organized-dirs.json"
try:
    doc = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)
for d in doc.get("dirs") or []:
    path = str(d.get("path") or "").strip()
    if path:
        print(path)
PY
)

if [ "${#DIRS[@]}" -eq 0 ]; then
    echo "[$(date -Is)] no registered directories, nothing to do" >>"$LOG"
    exit 0
fi

# One batch per invocation.  The regression tests for the paging fix and the
# rename safety both ran with batches of this size.
BATCH_LIMIT="${RETITLE_BATCH_LIMIT:-20}"

total_done=0
total_seen=0
rc_all=0

for dir in "${DIRS[@]}"; do
    [ -n "$dir" ] || continue
    tag=$(printf '%s' "$dir" | tr -c 'A-Za-z0-9._-' '_')
    out="$BATCH_LOG_DIR/${tag}-$(date +%Y%m%d-%H%M%S).log"
    echo "[$(date -Is)] retitle batch dir=$dir limit=$BATCH_LIMIT" >>"$LOG"

    # `--apply` is required, not optional: dailyorg.py decides from the flag
    # alone (``cfg.apply = bool(args.apply) and command in (...)``), so an
    # environment variable here would be silently ignored and the run would
    # "succeed" as a dry-run while writing a done marker for work it never
    # did.  A green exit code must mean the renames happened.
    "$PY" "$DAILY/dailyorg.py" \
        --state-dir "$STATE_DIR" \
        --run-name "retitle-$(date +%Y%m%d-%H%M%S)" \
        retitle --apply --registry-dir "$dir" --limit "$BATCH_LIMIT" >>"$out" 2>&1
    rc=$?
    tail -3 "$out" | sed 's/^/    /' >>"$LOG"

    # A run that silently degraded to a dry-run is the most dangerous outcome
    # here: exit 0, "no mutations were performed", nothing renamed, and the
    # wrapper would mark the task done.  Refuse that combination explicitly so
    # it shows up as a failure and stays retryable.
    if [ "$rc" -eq 0 ] && grep -q "no mutations were performed" "$out"; then
        echo "[$(date -Is)] batch ran as DRY-RUN (expected apply), refusing" >>"$LOG"
        rc_all=2
        continue
    fi

    if [ "$rc" -ne 0 ]; then
        rc_all=2
        echo "[$(date -Is)] batch failed rc=$rc dir=$dir" >>"$LOG"
        # Keep going: one directory that cannot be read must not strand the
        # rest, and the durable state means the next run resumes cleanly.
        continue
    fi
    total_done=$((total_done + 1))
done

echo "[$(date -Is)] retitle sweep done: ${total_done}/${#DIRS[@]} dirs ok" >>"$LOG"
exit "$rc_all"
