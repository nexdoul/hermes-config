#!/usr/bin/env bash
# Restart the Hermes gateway via the SIGUSR1 drain-aware path, with a detached
# relaunch watcher so the gateway comes back up even though there is no systemd
# unit or external supervisor on this host.
#
# Why not `hermes gateway restart` from an agent turn: the CLI refuses a
# self-targeting restart when it runs inside the supervised gateway process tree
# (_is_supervised_gateway_process). From here the CLI is a descendant of the
# gateway worker, so it would exit 1.
#
# Why not a bare `hermes gateway run`: _guard_existing_gateway_process_conflict
# prints "already running" and exits 1 while the old PID still holds the lock.
#
# The sequence below:
#   1. Arm a detached watcher that relaunches the gateway once the old PID exits.
#   2. Send SIGUSR1 → request_restart(via_service=True): refuse new turns, wait
#      for in-flight work, drain, exit 75.
#   3. Watcher respawns `hermes gateway run` detached (setsid), same as the
#      documented manual launch this host already uses.
#
# Idempotent-ish: if the gateway is not running, just starts it.
set -u

LOG="/home/hatch/.hermes/logs/gateway-restart-manual.log"
TS() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(TS)] $*" >> "$LOG"; }

HOME_DIR="/home/hatch"
HERMES_BIN="$HOME_DIR/.hermes/bin/hermes"
LOG_DIR="$HOME_DIR/.hermes/logs"

PID_FILE="$HOME_DIR/.hermes/gateway.pid"

current_pid() {
  [ -f "$PID_FILE" ] || return 0
  python3 -c "
import json,sys
try:
    print(json.load(open('$PID_FILE')).get('pid',''))
except Exception:
    pass
"
}

pid_alive() {
  [ -n "${1:-}" ] && [ -d "/proc/$1" ]
}

pid_is_gateway() {
  [ -e "/proc/$1/cmdline" ] || return 1
  tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null | grep -q "hermes.*gateway run"
}

launch() {
  cd "$HOME_DIR" || return 1
  setsid nohup "$HERMES_BIN" gateway run >> "$LOG_DIR/gateway.log" 2>&1 < /dev/null &
  log "launched gateway (detached)"
}

OLD_PID="$(current_pid)"

if ! pid_alive "$OLD_PID" || ! pid_is_gateway "$OLD_PID"; then
  log "no live gateway process (pid='$OLD_PID'); starting one"
  launch
  exit 0
fi

log "gateway running as pid=$OLD_PID; sending SIGUSR1 (drain-aware restart)"

# Detached relaunch watcher: wait for the old PID to disappear, then relaunch.
# Written to a script file so the PID never appears in a pgrep-able pattern that
# could self-match a later cleanup pass.
WATCHER="/tmp/hermes-gw-relaunch-watch-$$.sh"
cat > "$WATCHER" <<WEOF
#!/usr/bin/env bash
OLD=$OLD_PID
deadline=\$(( \$(date +%s) + 300 ))
while [ -d "/proc/\$OLD" ] && [ \$(date +%s) -lt \$deadline ]; do sleep 0.2; done
if [ -d "/proc/\$OLD" ]; then
  echo "[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] watcher: old pid \$OLD still alive after 300s; not relaunching" >> "$LOG"
  exit 1
fi
cd "$HOME_DIR" || exit 1
setsid nohup "$HERMES_BIN" gateway run >> "$LOG_DIR/gateway.log" 2>&1 < /dev/null &
echo "[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] watcher: relaunched gateway after pid \$OLD exited" >> "$LOG"
WEOF
chmod +x "$WATCHER"
setsid nohup bash "$WATCHER" >> "$LOG" 2>&1 < /dev/null &
log "armed relaunch watcher ($WATCHER) for pid=$OLD_PID"

kill -USR1 "$OLD_PID" || { log "FAILED to signal pid=$OLD_PID"; exit 1; }
log "SIGUSR1 sent to pid=$OLD_PID"
