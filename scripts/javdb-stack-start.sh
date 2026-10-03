#!/usr/bin/env bash
# javdb 项目自愈 launcher (供 hermes cron 每 5 分钟调用)
#
# 职责: 保证"重启后 JavDB -> 115 这条链还活着"
#   1. /etc/systemd/system 下的两个 unit 在不在 (重启清空 /etc 手动改动 -> [H], 必须重建)
#      源文件在项目内 env/etc/ (位于 /home/hatch 永久区, 不被清)
#   2. mihomo (javdb 源站路由) + 115driver-cnvps-tunnel (115 的 CN 出口隧道)
#   3. 端口就绪: 7890(mihomo mixed) / 41150(SOCKS5)
#   4. 冒烟测试: 115driver whoami 真账号 (走本地编译的 x86_64 二进制 + 隧道)
#
# 健康标记: logs/.stack_healthy (mtime 即上次健康时刻)
# 失败细节: logs/javdb-selfheal.log
#
# 注意: 文件名必须带 .sh —— 无扩展名会被 hermes cron 当 Python 执行。
set -u

PROJECT=/home/hatch/code/javdb
ENV=$PROJECT/env
LOGDIR=$PROJECT/logs
LOG=$LOGDIR/javdb-selfheal.log
LAST_OK=$LOGDIR/.stack_healthy
UNIT_SRC=$ENV/etc
UNIT_DST=/etc/systemd/system
UNITS="mihomo-local.service 115driver-cnvps-tunnel.service krvps-tunnel.service"
mkdir -p "$LOGDIR"

log() { echo "$(date -Iseconds) $*" >> "$LOG"; }

# 并发保护 + 锁持有者活性保底 (同 browse-stack-start.sh 的教训:
# daemon 继承 flock FD 会让自愈永久空转, 必须识别泄漏并抢锁)
LOCK=/tmp/javdb-stack-start.lock
exec 9>"$LOCK"
if ! flock -n 9; then
  # fuser 可能输出多个 PID（空格分隔）。tr -d ' ' 会把它们粘成一个巨大
  # 数字，/proc/<垃圾> 读不到 -> 误判泄漏 -> 抢锁时上游还在收尾。
  # 必须 for h in $holders 逐 PID 判定。
  holders=$(fuser "$LOCK" 2>/dev/null)
  if [ -n "$holders" ]; then
    leaked=0
    busy=0
    for h in $holders; do
      # PID 可能已退出：2>/dev/null 不足以压掉 bash 自身的重定向报错，
      # 用 { ...; } 2>/dev/null 把整组包裹起来。
      if { tr '\0' ' ' < "/proc/$h/cmdline"; } 2>/dev/null | grep -q 'javdb-stack-start'; then
        busy=1
      else
        leaked=1
      fi
    done
    if [ "$busy" = "1" ]; then
      log "another selfheal run in progress (holders=$holders), exiting"
      exit 0
    fi
    if [ "$leaked" = "1" ]; then
      log "stale lock holder pid=$holders, 非本脚本实例 -> 视为泄漏, 抢锁继续"
      flock -n 9 || { log "WARN 抢锁失败, 本轮让路 (上游可能正在收尾)"; exit 0; }
    else
      log "flock busy but no holder found, exiting"
      exit 0
    fi
  else
    log "flock busy but no holder found, exiting"
    exit 0
  fi
fi

need_reload=0

# --- 1. unit 文件重建 (/etc 是易失区) ---
for u in $UNITS; do
  if [ ! -f "$UNIT_SRC/$u" ]; then
    log "ERROR 项目内 unit 源文件缺失: $UNIT_SRC/$u"
    exit 1
  fi
  if [ ! -f "$UNIT_DST/$u" ] || ! cmp -s "$UNIT_SRC/$u" "$UNIT_DST/$u"; then
    install -m 0644 "$UNIT_SRC/$u" "$UNIT_DST/$u"
    log "unit 已重建/更新: $UNIT_DST/$u"
    need_reload=1
  fi
done

[ "$need_reload" = "1" ] && systemctl daemon-reload

# --- 2. 服务拉起 (幂等: 已 active 时不动) ---
for u in $UNITS; do
  svc=${u%.service}
  state=$(systemctl is-active "$svc" 2>/dev/null || true)
  if [ "$state" != "active" ]; then
    log "service $svc 非 active (state=$state) -> enable --now"
    if ! systemctl enable --now "$svc" >>"$LOG" 2>&1; then
      log "ERROR systemctl enable --now $svc 失败"
      exit 1
    fi
  fi
done

# --- 3. 端口就绪 (mihomo mixed 7890 + 隧道 41150) ---
# unit 刚 active 时端口可能还没 bind, 给最多 30s 收敛窗口
ports_ok=0
for i in $(seq 1 30); do
  if ss -tln 2>/dev/null | grep -q "127.0.0.1:7890" && \
     ss -tln 2>/dev/null | grep -q "127.0.0.1:41150"; then
    ports_ok=1
    break
  fi
  sleep 1
done
[ "$ports_ok" = "1" ] || log "WARN 端口未在 30s 内就绪 (7890/41150), 继续冒烟测试"

# --- 4. 冒烟测试: 115 真账号 (本地二进制 + cnvps 隧道 + 迁移的 cookie) ---
# 这是唯一能同时验证"二进制在/隧道在/cookie 在"的单点检查
if ! timeout 90 "$ENV/bin/115driver" whoami >/dev/null 2>&1; then
  log "ERROR 115 whoami 失败 (二进制/隧道/cookie 至少一项不可用)"
  exit 1
fi

# --- 5. 源站路由可解析 (javdb 采集入口的前置条件) ---
# 本机直连 javdb.com 是可用路径，但它本身有 30s 级的偶发抖动 (实测 3 次里
# 1 次失败，单次探测 15~26s 不等)。自愈每 5 分钟一次，一次抖动就把整次
# 巡检判成 exit 1 并发出报警 —— 而下次巡检通常就恢复。所以这里重试:
# 单次失败不是故障，连续失败才是。
#
# 但"javdb 侧把本机出口 IP 封了"与上面完全不同，是自愈脚本治不了的外部
# 故障：实测真实 IP 直连 / egress 代理 / cnvps 隧道三条路全部 403 或超时，
# 而 google、github 同期 200，说明是本机网络没问题、javdb 的 Cloudflare
# WAF 按 IP 封禁。这种情况重试 3 次只会让每轮巡检都刷一次同样的报警，
# 所以降级为 WARN：记录到日志供人判断，但不以 exit 1 打扰用户，也不
# touch 健康标记（.stack_healthy 的 mtime 必须继续如实反映"上一次真的全绿"）。
route_ok=""

# 已知外部封禁记忆：上一轮已确认 javdb WAF 封本机 IP 时，写一个 stamp。
# 30 分钟内的后续巡检不再重复 3x150s 的 route 重试 —— 封禁不可能在几分钟内
# 自己解封，重复重试只是把每轮巡检拖到 2 分钟以上并刷一样的 WARN。
# 到期后仍然会重新探测一次，所以解封后自动恢复，不需要人工清 stamp。
BLOCKED_STAMP=$LOGDIR/.javdb_waf_blocked
in_cooldown=0
if [ -f "$BLOCKED_STAMP" ]; then
  stamp_age=$(( $(date +%s) - $(stat -c %Y "$BLOCKED_STAMP" 2>/dev/null || echo 0) ))
  if [ "$stamp_age" -lt 1800 ]; then
    in_cooldown=1
  fi
fi

# 封禁冷却期内改用单次快速探测（一次裸 curl 就够判断解封没有），
# 而不是启动 Python 跑完整 route 选择。
if [ "$in_cooldown" = "1" ]; then
  code=$(timeout 40 curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' \
    -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
    https://javdb.com/ 2>/dev/null)
  if [ "$code" = "200" ]; then
    log "javdb WAF 封禁已解除（快速探测 200），清冷却标记并恢复完整巡检"
    rm -f "$BLOCKED_STAMP"
    in_cooldown=0
  else
    log "javdb stack DEGRADED (javdb WAF 封禁冷却中, 剩余 $(( (1800 - stamp_age) / 60 )) 分钟; units active, ports=$ports_ok, 115 whoami ok)"
    exit 0
  fi
fi

for attempt in 1 2 3; do
  route_ok=$(timeout 150 env \
    PYTHONPATH="$PROJECT/115pan:$PROJECT/115pan/_internal" \
    JAVDB_ENV_ROOT="$ENV" \
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT/115pan/_internal')
import source_transport as st
r = st.prepare_source_route('https://javdb.com/')
print('OK' if r.ok else 'FAIL:' + r.phase)
" 2>>"$LOG" | tail -1)
  [ "$route_ok" = "OK" ] && break
  log "WARN source route attempt $attempt/3 不可用: $route_ok"
  [ "$attempt" = "3" ] || sleep 20
done
case "$route_ok" in
  OK)
    # 恢复了：清掉可能存在的封禁记忆，让下次立刻回到完整巡检
    rm -f "$BLOCKED_STAMP"
    ;;
  *)
    # 区分"链路自身坏了"和"javdb 外部封禁本机 IP"：后者先用一次裸 HTTP
    # 请求确认 javdb 是否真的不可达（403/超时都算不可达，而不是我们配错）。
    if timeout 40 curl -sS --noproxy '*' -o /dev/null -w '%{http_code}' \
        -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
        https://javdb.com/ 2>/dev/null | grep -qE '^(403|000)$'; then
      log "WARN javdb.com 对本机出口 IP 返回 403/超时（Cloudflare WAF 按 IP 封禁）。units/115 隧道本身健康，此为外部故障，自愈无法修复；写 30 分钟冷却标记，期间只做快速解禁探测。"
      touch "$BLOCKED_STAMP"
      log "javdb stack DEGRADED (units active, ports=$ports_ok, 115 whoami ok, source route blocked by javdb WAF)"
      exit 0
    fi
    log "ERROR source route 不可用 (3 次尝试后): $route_ok"
    exit 1
    ;;
esac

touch "$LAST_OK"
log "javdb stack OK (units active, ports=$ports_ok, 115 whoami ok, source route ok)"
exit 0
