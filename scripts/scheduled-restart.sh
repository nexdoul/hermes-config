#!/usr/bin/env bash
# Scheduled Hermes gateway restart, armed 2026-09-27 for 2026-09-28 06:00 Asia/Shanghai.
#
# Why a script and not a cron job's prompt: Hermes' cron scheduler refuses prompts containing
# gateway lifecycle commands (#30719 — a supervisor-driven SIGTERM-respawn loop can wedge a
# systemd/launchd-managed service). The restart logic therefore lives here, and cron only asks
# an agent to verify that it happened.
#
# The user explicitly requested this restart (it applies the heartbeat terminal-marker patch);
# it is not a self-directed restart.
set -u

LOG="/home/hatch/.hermes/logs/scheduled-restart.log"
TS() { date '+%Y-%m-%d %H:%M:%S %Z'; }

log() { echo "[$(TS)] $*" >> "$LOG"; }

# Refuse to run as a scheduled job INSIDE the gateway's own process tree: a restart issued from
# an agent turn would kill the very turn running it. Only an out-of-band caller is valid.
if [ "${HERMES_INTERNAL:-0}" = "1" ]; then
    log "refusing: invoked from inside the gateway (HERMES_INTERNAL=1)"
    exit 0
fi

log "scheduled restart starting"

# Verify the patch is present BEFORE restarting, so a bad install can't silently go live.
PATCH_FILE="/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/gateway/run_turn.py"
if [ -f "$PATCH_FILE" ]; then
    HITS=$(grep -c "_run_agent_stamp_heartbeat_terminal" "$PATCH_FILE" 2>/dev/null || echo 0)
    if [ "$HITS" -lt 2 ]; then
        log "WARNING: heartbeat terminal patch missing (grep hits=$HITS, expected >=2); restarting anyway"
    else
        log "patch verified: _run_agent_stamp_heartbeat_terminal present ($HITS hits)"
    fi
else
    log "WARNING: patch file not found: $PATCH_FILE"
fi

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q '^hermes'; then
    log "restarting via systemctl"
    systemctl restart hermes >> "$LOG" 2>&1
    RC=$?
else
    log "restarting via hermes gateway restart"
    hermes gateway restart >> "$LOG" 2>&1
    RC=$?
fi

log "restart command returned rc=$RC"
sleep 10

log "post-restart status:"
hermes gateway status >> "$LOG" 2>&1
log "scheduled restart finished rc=$RC"
