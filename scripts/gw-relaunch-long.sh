#!/usr/bin/env bash
# Long-deadline relaunch watcher (companion to gateway-restart-manual.sh's 300s one).
#
# The gateway's restart drain can legally wait up to agent.restart_after_turn_timeout
# (1800s default) for in-flight turns before it exits. A watcher with a shorter
# deadline abandons the host with no gateway at all — which on this box means no
# Feishu/WhatsApp link and no selfheal entry point until the 5-minute cron notices.
#
# This one waits 2400s. If the primary watcher already relaunched the gateway by
# then, `hermes gateway run` here exits 1 harmlessly ("already running").
set -u

LOG="/home/hatch/.hermes/logs/gateway-restart-manual.log"
TS() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(TS)] $*" >> "$LOG"; }

OLD="${1:?usage: gw-relaunch-long.sh <old_pid>}"
HOME_DIR="/home/hatch"
HERMES_BIN="$HOME_DIR/.hermes/bin/hermes"

deadline=$(( $(date +%s) + 2400 ))
while [ -d "/proc/$OLD" ] && [ $(date +%s) -lt $deadline ]; do sleep 1; done

if [ -d "/proc/$OLD" ]; then
  log "long watcher: pid $OLD still alive after 2400s; leaving it alone (drain may be wedged — check gateway.log)"
  exit 1
fi

# If a gateway is already running (the short watcher won), this exits 1 harmlessly.
cd "$HOME_DIR" || exit 1
setsid nohup "$HERMES_BIN" gateway run >> "$HOME_DIR/.hermes/logs/gateway.log" 2>&1 < /dev/null &
log "long watcher: relaunch attempt done after pid $OLD exited"
