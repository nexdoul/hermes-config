#!/bin/bash
# Chain watchdog: re-launch the two long drivers if a container restart (or a
# crash) took them down.
#
# The drivers are setsid daemons, so a gateway restart does not reach them,
# but a *container* restart does.  Both drivers are idempotent at the top —
# the backfill skips finished items through filter_resumable, and 115re keeps
# its own per-movie state — so a re-launch can never duplicate work.
set -u
ROOT=/home/hatch/code/javdb
OUT="$ROOT/logs/chain-watchdog.log"
STAMP="$ROOT/logs/.chain-watchdog-stamp"
MARK_BACKFILL="$ROOT/logs/.minase-backfill-done"
MARK_ACTORS="$ROOT/logs/.actors-done"
DRV_BACKFILL="$ROOT/logs/minase-driver.sh"
DRV_ACTORS="$ROOT/logs/actors-driver.sh"

log() { echo "[watchdog $(date -u +%H:%M:%S)] $*" >> "$OUT"; }

# Rate-limit ourselves: 5 min between waking. The cron fires every 15m, so
# this only guards against manual/concurrent runs -- it must be SHORTER than
# the cron interval, otherwise the effective recovery latency doubles (a
# 15m stamp under a 15m cron means up to 30 min of dead task after a restart).
NOW=$(date +%s)
if [ -f "$STAMP" ]; then
    LAST=$(cat "$STAMP" 2>/dev/null || echo 0)
    if [ $((NOW - LAST)) -lt 300 ]; then
        exit 0
    fi
fi
echo "$NOW" > "$STAMP"

# 2026-09-30 hardening: liveness must cover STALLED work, not just a live PID.
# "Process exists" was the only check, so a driver hanging on a child looked
# healthy while the task sat dead and every log line said ok. Progress is read
# from the driver's own log mtime: one slice legitimately takes ~15 min, so
# 30 min of silence means two slices' worth of nothing happened.
STALL_S=$((30 * 60))
# mtime of the driver's own log = last time the work itself advanced
progress_newer_than() {
    local f="$ROOT/logs/minase-actress-apply.log"
    [ -f "$f" ] || return 1
    local now mt
    now=$(date +%s)
    mt=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    [ $((now - mt)) -lt "$1" ]
}
# PIDs of the driver, resolved by reading /proc cmdline -- never by name
# matching our own command line (that self-terminates: pkill -f sees the
# pattern sitting in the watchdog's own argv and kills the caller too).
driver_pids() {
    local pat="$1" p cmd
    for p in $(pgrep -f 'dailyorg.py' 2>/dev/null); do
        cmd=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null || true)
        case "$cmd" in *"$pat"*) echo "$p" ;; esac
    done
    for p in $(pgrep -f 'driver.sh' 2>/dev/null); do
        cmd=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null || true)
        case "$cmd" in
            *watchdog*|*pgrep*) continue ;;
        esac
        case "$cmd" in *"$pat"*) echo "$p" ;; esac
    done
}
# True when the driver process exists. Uses the same /proc scan.
alive() { [ -n "$(driver_pids "$1")" ]; }

if [ -f "$MARK_BACKFILL" ] && [ -f "$MARK_ACTORS" ]; then
    log "both markers present, nothing to do"
    exit 0
fi

if [ -f "$MARK_BACKFILL" ]; then
    log "backfill finished (marker present), nothing to do"
elif alive "minase-driver.sh"; then
    if progress_newer_than $STALL_S; then
        log "backfill driver alive and progressing, nothing to do"
    else
        log "STALL: driver alive but no progress in $((STALL_S/60))min, killing and relaunching (resume is idempotent)"
        for p in $(driver_pids "minase-driver.sh"); do
            log "  killing stalled pid $p"
            kill -TERM "$p" 2>/dev/null || true
        done
        sleep 2
        setsid bash "$DRV_BACKFILL" >> "$OUT" 2>&1 < /dev/null &
        log "relaunched stalled backfill driver"
    fi
else
    log "backfill driver not running and not finished, relaunching"
    setsid bash "$DRV_BACKFILL" >> "$OUT" 2>&1 < /dev/null &
fi

# Actor ingest is a separate chain stage: only run it once the backfill is
# done, otherwise both hammer 115 at once and double the WAF risk.
if [ ! -f "$MARK_BACKFILL" ]; then
    log "actor driver deferred until backfill finishes"
    exit 0
fi

if [ -f "$MARK_ACTORS" ]; then
    log "actor ingest finished (marker present), nothing to do"
    exit 0
fi

if alive "actors-driver.sh"; then
    if progress_newer_than $STALL_S; then
        log "actor driver alive and progressing, nothing to do"
    else
        log "STALL: actor driver alive but no progress in $((STALL_S/60))min, killing and relaunching"
        for p in $(driver_pids "actors-driver.sh"); do
            log "  killing stalled pid $p"
            kill -TERM "$p" 2>/dev/null || true
        done
        sleep 2
        setsid bash "$DRV_ACTORS" >> "$OUT" 2>&1 < /dev/null &
        log "relaunched stalled actor driver"
    fi
else
    log "actor driver not running, relaunching"
    setsid bash "$DRV_ACTORS" >> "$OUT" 2>&1 < /dev/null &
fi

exit 0
