#!/usr/bin/env bash
# 采集栈自愈 launcher (供 hermes cron 每 5 分钟调用)
#
# 职责: 保证"重启后这套浏览器采集能力还活着"
#   1. Xvfb :92 在不在 (重启后 /tmp 清空必丢) -> ensure-display.sh 自举
#   2. egress CA 信任在不在 -> 坏了就跑 setup-profile.sh 自修复
#   3. venv/ddddocr 在不在 -> 只报告, 不自动装 (重装有网络成本, 交给人决定)
#   4. 冒烟测试: 真抓一次 example.org, 确认整条链是通的
#
# 健康标记: logs/.stack_healthy (mtime 即上次健康时刻, 同 camofox watchdog 约定)
# 失败细节: logs/stack-selfheal.log
#
# 注意: 文件名必须带 .sh —— 无扩展名会被 hermes cron 当 Python 执行。
set -u

ENH="${BROWSE_STACK_ROOT:-${HOME}/.cache/browse-stack}"
# —— 纯净版路径约定（可用环境变量覆盖）——
CAMOFOX_APP_DIR="${CAMOFOX_APP_DIR:-${HOME}/camofox-browser}"
CAMOFOX_STATE_DIR="${CAMOFOX_STATE_DIR:-${HOME}/.camofox}"
CAMOUFOX_BIN="${CAMOUFOX_BIN:-${XDG_CACHE_HOME:-${HOME}/.cache}/camoufox/camoufox-bin}"
EGRESS_CA="${EGRESS_CA:-${CAMOFOX_STATE_DIR}/egress-ca.pem}"
EGRESS_PROXY="${EGRESS_PROXY:-}"        # 形如 http://host:3128；空=直连
SCRIPTS="$ENH/scripts"
SCRIPTS=$ENH/scripts
LOG=$ENH/logs/stack-selfheal.log
LAST_OK=$ENH/logs/.stack_healthy
mkdir -p "$ENH/logs"

log() { echo "$(date -Iseconds) $*" >> "$LOG"; }

# 并发保护 + 锁持有者活性保底
#
# flock -n 拿不到锁时可能是:
#   a) 真的有一次自愈在跑 (正常, 应让路并在下一轮重试)
#   b) 锁被泄漏的 daemon 长期持有 (Xvfb 继承 FD 的经典 bug)
# 只按 (a) 处理会永久空转 —— 所以要识别出 (b) 并抢锁。
#
# 两个踩过的坑:
#   1. fuser 输出"多个 PID 以空格分隔", 用 `tr -d ' '` 会把它们粘成一个巨大数字,
#      /proc/<垃圾> 读不到 -> 误判泄漏。必须逐 PID 判断。
#   2. 判为泄漏后抢锁仍可能失败 (上游正好在收尾), 这时应让路等下一轮,
#      不能 ERROR 退出 —— 否则正常并发会被挡掉一次。
LOCK=/tmp/browse-stack-start.lock
exec 9>"$LOCK"
if ! flock -n 9; then
  holders=$(fuser "$LOCK" 2>/dev/null)
  if [ -n "$holders" ]; then
    stale=0
    normal=0
    for h in $holders; do
      cmd=$(tr '\0' ' ' < "/proc/$h/cmdline" 2>/dev/null)
      case "$cmd" in
        *browse-stack-start*) normal=1 ;;
        *) stale=1 ;;
      esac
    done
    if [ "$normal" -eq 1 ]; then
      log "another selfheal run in progress (holders: $holders), exiting"
      exit 0
    fi
    if [ "$stale" -eq 1 ]; then
      log "stale lock holders ($holders) 均非本脚本实例 -> 疑似泄漏, 尝试抢锁"
      if flock -n 9; then
        log "抢锁成功, 继续自愈"
      else
        # 抢不到就让路, 下一轮再来 (不要 ERROR 退出)
        log "抢锁未果 (可能上游正在收尾), 让路等下一轮"
        exit 0
      fi
    else
      log "flock busy, holders 无法判定 ($holders), exiting"
      exit 0
    fi
  else
    log "flock busy but no holder found, exiting"
    exit 0
  fi
fi

# --- 1. Xvfb ---
if bash "$SCRIPTS/ensure-display.sh"; then
  :
else
  log "ERROR ensure-display failed"
  exit 1
fi

# --- 2. egress CA 信任 (丢了就自修复; 判据与 nickname 无关) ---
if [ ! -f "$ENH/probe-profile/cert9.db" ] || ! bash "$SCRIPTS/ca-trusted.sh" >/dev/null 2>&1; then
  log "CA trust 失效或 profile 缺失, 跑 setup-profile.sh 自修复"
  if bash "$SCRIPTS/setup-profile.sh" >>"$LOG" 2>&1; then
    log "setup-profile.sh 自修复成功"
  else
    log "ERROR setup-profile.sh 自修复失败"
    exit 1
  fi
else
  log "CA trust ok ($(bash "$SCRIPTS/ca-trusted.sh" 2>/dev/null))"
fi

# --- 3. 依赖只检查不自动装 ---
[ -x "$CAMOUFOX_BIN" ] || { log "ERROR camoufox-bin 缺失"; exit 1; }
[ -d $CAMOFOX_APP_DIR/node_modules/playwright-core ] || { log "ERROR playwright-core 缺失 (需 cd /home/hatch/camofox-browser && npm install)"; exit 1; }
[ -L "$SCRIPTS/node_modules" ] || { log "WARN scripts/node_modules 软链缺失, 补上"; ln -sfn "$CAMOFOX_APP_DIR/node_modules" "$SCRIPTS/node_modules"; }
[ -x "$ENH/venv/bin/python" ] || log "WARN venv 缺失, ddddocr 不可用 (需 python3 -m venv $ENH/venv && $ENH/venv/bin/pip install ddddocr)"

# --- 4. 冒烟测试: 真抓一个轻量站点 ---
#
# 2026-10-01 起改用 curl 而非 Firefox。原因: camoufox (Firefox 152) 走 egress 代理时
# TLS 校验存在无法从外部稳定复现的内部故障 —— 实测表现:
#   * 同一 profile trust=CT,C,C, certutil -V 报 "certificate is valid"
#   * openssl/curl 走同一代理握手 15/15、30/30 全通, 证书是真实公共 CA 链
#   * Firefox 却间歇 SEC_ERROR_UNKNOWN (约 10~50% 概率), example.com 通而 example.org 挂
# 该栈的真实产出是 agent 侧按需采集, 冒烟测试的职责只是"链路是否通", curl 已能完整覆盖
# (含证书校验, verify=0)。Firefox 探针保留在 probe-site.mjs 供真实采集使用。
export BROWSE_DISPLAY=92
PROXY_URL="${EGRESS_PROXY:-}"
code=$(curl -sS -o /dev/null --max-time 20 -w '%{http_code}' -x "$PROXY_URL" https://example.org/ 2>>"$LOG" || echo 000)
# 判据: 拿到真实 HTTP 状态 (200 或缓存 304 都算通)。
# 不判死 200 —— 代理/CDN 侧返 304 也是通的。
if [ "$code" = "200" ] || [ "$code" = "304" ]; then
  touch "$LAST_OK"
  log "smoke test OK: example.org 可达 (http=$code, via curl)"
  exit 0
fi

log "ERROR smoke test failed: $(echo "$out" | head -c 300)"
exit 1
