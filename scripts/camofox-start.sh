#!/usr/bin/env bash
# Camofox browser server self-healing launcher.
set -u
LOCK=/tmp/camofox-start.lock
APP="${CAMOFOX_APP_DIR:-${HOME}/camofox-browser}"
LOGDIR="${CAMOFOX_STATE_DIR:-${HOME}/.camofox}/logs"
LOG=$LOGDIR/server.log
LAST_OK=$LOGDIR/.last_healthy
PORT=9377
URL="http://127.0.0.1:$PORT"
ENVFILE="${CAMOFOX_STATE_DIR:-${HOME}/.camofox}/server.env"
mkdir -p "$LOGDIR"
exec 9>"$LOCK"
if ! flock -n 9; then echo "another start attempt in progress, exiting"; exit 0; fi
# Only the persistent home survives a reset: restore the GUI tools from cached .deb files.
if ! command -v x11vnc >/dev/null 2>&1 || ! command -v websockify >/dev/null 2>&1 || [ ! -f /usr/share/novnc/vnc.html ]; then
    shopt -s nullglob
    packages=("$APP"/.vnc-stack/debs/*.deb)
    shopt -u nullglob
    if [ "${#packages[@]}" -eq 0 ] || ! DEBIAN_FRONTEND=noninteractive dpkg -i --force-confold "${packages[@]}" >>"$LOG" 2>&1; then
        echo "$(date -Iseconds) ERROR: VNC package restore failed" >>"$LOG"
        exit 1
    fi
fi
# Load API credentials locally, without exposing the bearer token in output.
[ -r "$ENVFILE" ] || { echo "$(date -Iseconds) ERROR: server env missing" >> "$LOG"; exit 1; }
set -a
. "$ENVFILE"
set +a
# Prewarm only creates an off-screen 10x10 window; keep a visible tab open.
ensure_visible_tab() {
    python3 "${CAMOFOX_STATE_DIR:-${HOME}/.camofox}/bin/camofox-visible-tab.py" >> "$LOG" 2>&1
}
# The VNC watcher owns noVNC. If it is missing, a healthy API alone is not enough.
if curl -fsS --max-time 5 "$URL/health" >/dev/null 2>&1; then
    if curl -fsS --max-time 3 http://127.0.0.1:6080/vnc.html >/dev/null 2>&1; then
        ensure_visible_tab || exit 1
        touch "$LAST_OK"
        exit 0
    fi
    echo "$(date -Iseconds) ERROR: Camofox API alive but noVNC absent; investigate watcher" >> "$LOG"
    exit 1
fi
echo "$(date -Iseconds) camofox not responding on $PORT, starting..." >> "$LOG"
[ -f "$APP/node_modules/camoufox-js/package.json" ] || { echo "$(date -Iseconds) ERROR: node_modules missing" >> "$LOG"; exit 1; }
[ -x "${XDG_CACHE_HOME:-${HOME}/.cache}/camoufox/camoufox-bin" ] || { echo "$(date -Iseconds) ERROR: camoufox binary missing" >> "$LOG"; exit 1; }
[ -r "$ENVFILE" ] || { echo "$(date -Iseconds) ERROR: server env missing" >> "$LOG"; exit 1; }
cd "$APP" || exit 1
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"
export HOME="${HOME}"
set -a
. "$ENVFILE"
set +a
CAMOFOX_DISABLE_DEFAULT_ADDONS=1 nohup node server.js >> "$LOG" 2>&1 &
NEWPID=$!
disown "$NEWPID" 2>/dev/null || true
for i in $(seq 1 30); do
    if curl -fsS --max-time 3 "$URL/health" >/dev/null 2>&1 && curl -fsS --max-time 3 http://127.0.0.1:6080/vnc.html >/dev/null 2>&1; then
        ensure_visible_tab || exit 1
        echo "$(date -Iseconds) camofox started, pid=$NEWPID" >> "$LOG"
        touch "$LAST_OK"
        exit 0
    fi
    sleep 1
done
echo "$(date -Iseconds) ERROR: camofox failed to become healthy in 30s" >> "$LOG"
exit 1
