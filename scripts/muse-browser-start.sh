#!/usr/bin/env bash
set -euo pipefail
BASE="${CAMOFOX_STATE_DIR:-${HOME}/.camofox}/muse-persistent"
APP="${CAMOFOX_APP_DIR:-${HOME}/camofox-browser}"
mkdir -p "$BASE"
exec 9>"$BASE/launcher.lock"
flock -w 30 9
LOG="$BASE/service.log"
if ! command -v Xvfb >/dev/null 2>&1; then echo 'Xvfb missing' >&2; exit 1; fi
if [ ! -x "${CAMOFOX_STATE_DIR:-${HOME}/.camofox}/muse-runtime/camoufox-bin" ]; then echo 'isolated browser runtime missing' >&2; exit 1; fi
if [ ! -r "${CAMOFOX_STATE_DIR:-${HOME}/.camofox}/Muse 自动网络审批助手.user.js" ]; then echo 'userscript missing' >&2; exit 1; fi
if ! pgrep -f '^Xvfb :91 ' >/dev/null; then
  nohup Xvfb :91 -screen 0 1440x900x24 -ac -nolisten tcp -noreset >>"$BASE/xvfb.log" 2>&1 </dev/null &
  disown || true
fi
# 200 requires a live Muse page and an observed userscript execution marker.
if curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:18678/health >/dev/null 2>&1; then
  touch "$BASE/.last_healthy"
  exit 0
fi
# An unhealthy instance may still be loading; do not race a second Firefox
# against the same profile. Restart only after repeated degraded checks.
if ss -lntp | grep -q '127.0.0.1:18678 '; then
  count=0
  [ -r "$BASE/.unhealthy_count" ] && read -r count < "$BASE/.unhealthy_count"
  count=$((count+1))
  printf '%s\n' "$count" > "$BASE/.unhealthy_count"
  if [ "$count" -lt 3 ]; then exit 1; fi
  pid=$(ss -lntp | sed -n 's/.*127\.0\.0\.1:18678 .*pid=\([0-9]*\).*/\1/p' | sed -n '1p')
  [ -z "$pid" ] || kill -TERM "$pid" 2>/dev/null || true
  for n in $(seq 1 20); do
    if ! ss -lntp | grep -q '127.0.0.1:18678 '; then break; fi
    sleep 1
  done
  if ss -lntp | grep -q '127.0.0.1:18678 '; then echo 'old instance did not stop' >&2; exit 1; fi
fi
rm -f "$BASE/.unhealthy_count"
cd "$APP"
export DISPLAY=:91 CAMOFOX_DISABLE_DEFAULT_ADDONS=1
# Prevent the daemon from inheriting the launcher's flock descriptor.
nohup node "$APP/muse-persistent.mjs" 9>&- >>"$LOG" 2>&1 </dev/null &
disown || true
for n in $(seq 1 35); do
  if curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:18678/health >/dev/null 2>&1; then
    touch "$BASE/.last_healthy"
    exit 0
  fi
  sleep 1
done
echo 'Muse browser failed health check after launch' >&2
exit 1
