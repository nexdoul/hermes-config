#!/usr/bin/env bash
# 确保 DISPLAY 可用 (重启自愈的核心)
#
# 为什么需要它: 容器重启后 /tmp 被清空, Xvfb 全部消失, 探针报
#   "Error: cannot open display: :92" —— 这是"能力没固定化"的首要原因。
#
# 设计:
#   - flock 保护, 并发调用只有一个真正启动 Xvfb (避免重复拉起一堆)
#   - 已存在就直接复用 (不杀不重建)
#   - 启动后轮询等就绪, 不盲目 sleep
#   - 幂等: 可被任意频率调用 (cron 每分钟调也无副作用)
#
# 退出码: 0=可用, 1=不可用
set -u

DISPLAY_NUM="${BROWSE_DISPLAY:-92}"
# 统一成 :N 形式
case "$DISPLAY_NUM" in :*) ;; *) DISPLAY_NUM=":$DISPLAY_NUM" ;; esac
DISPLAY="$DISPLAY_NUM"
BROWSE_STACK_ROOT="${BROWSE_STACK_ROOT:-${HOME}/.cache/browse-stack}"
LOG="$BROWSE_STACK_ROOT/logs/ensure-display.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date -Iseconds) $*" >> "$LOG"; }

alive() {
  command -v xdpyinfo >/dev/null 2>&1 || return 0   # 没工具就不误判
  DISPLAY="$DISPLAY" timeout 3 xdpyinfo >/dev/null 2>&1
}

if alive; then
  exit 0
fi

# 清掉可能残留的 lock/socket (重启后 /tmp 通常会自带清理, 双保险)
rm -f "/tmp/.X${DISPLAY#:}-lock" 2>/dev/null || true
rm -f "/tmp/.X11-unix/X${DISPLAY#:}" 2>/dev/null || true

# flock: 同一显示号只允许一个启动者, 其余等待结果
LOCK="/tmp/xvfb${DISPLAY#:}.ensure.lock"
exec 8>"$LOCK"
if ! flock -n 8; then
  # 有人在启动, 等它就绪
  for _ in $(seq 1 30); do
    alive && exit 0
    sleep 1
  done
  log "ERROR waited for concurrent Xvfb start but $DISPLAY never became ready"
  exit 1
fi

command -v Xvfb >/dev/null 2>&1 || { log "ERROR Xvfb not installed"; echo "Xvfb not installed" >&2; exit 1; }

log "starting Xvfb $DISPLAY"
# **关闭所有继承来的 FD 再启动 Xvfb** (8>&- 9>&-)。
# 不关的话 daemon 会永久持有上游脚本的 flock (FD 8/9),
# 之后每次自愈都撞上 "another selfheal run in progress" —— 实测踩过:
# Xvfb 继承 browse-stack-start.sh 的 FD9 锁后, 连续 10 次自愈全部空转。
# 用 exec 包裹的子 shell 会在 Xvfb 退出时正确释放, 且不影响前台 flock。
setsid Xvfb "$DISPLAY" -screen 0 1600x950x24 -ac -nolisten tcp \
  >"$BROWSE_STACK_ROOT/logs/xvfb${DISPLAY#:}.log" 2>&1 </dev/null 8>&- 9>&- &
XVFB_PID=$!
disown 2>/dev/null || true

for _ in $(seq 1 30); do
  alive && { log "Xvfb $DISPLAY ready pid=$XVFB_PID"; echo "$XVFB_PID" > "/tmp/xvfb${DISPLAY#:}.pid"; exit 0; }
  kill -0 "$XVFB_PID" 2>/dev/null || { log "ERROR Xvfb $DISPLAY died, see xvfb${DISPLAY#:}.log"; exit 1; }
  sleep 1
done

log "ERROR Xvfb $DISPLAY did not become ready in 30s"
exit 1
