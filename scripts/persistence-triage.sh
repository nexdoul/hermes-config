#!/usr/bin/env bash
#
# persistence-triage.sh — 重启后持久性三分诊断（skill hermes-runtime-local-patches 的 ①②③④ 步）
#
# 对每个需要持久的东西，判定它落在三个宿主的哪一个：
#   [P] permanent   已在永久区（$HOME 下）→ 不需要自愈，也不该接自愈
#   [M] movable     不在永久区，但搬过去就能永久 → 应该搬家而不是建自愈
#   [H] healable    搬不走（或在易失区才合理）→ 必须接自愈
#   第 4 步：已接自愈但 [M] 或 [P] 的 → 标记为冗余自愈（REDUNDANT），建议删
#
# 严格只读：本脚本不改任何东西，只输出判定 + 建议。真正的搬家/删除由人确认后做。
#
set -uo pipefail

HERMES_HOME="/home/hatch/.hermes"
HOME_ROOT="/home/hatch"
PATCH_ROOT="$HERMES_HOME/patches"
SETUP_DIR="$HOME_ROOT/workspace/setup"
ENHANCE_DIR="$HOME_ROOT/workspace/enhance"
RT_ROOT="$HERMES_HOME/npm/node_modules/hermes-agent"
RUNTIME="$RT_ROOT/runtime/hermes-agent"

C_RESET=$'\033[31m'; C_MOVE=$'\033[33m'; C_KEEP=$'\033[32m'; C_NC=$'\033[0m'
[ -t 1 ] || { C_RESET=""; C_MOVE=""; C_KEEP=""; C_NC=""; }

say()  { printf '%s\n' "$*"; }
hdr()  { printf '\n== %s ==\n' "$*"; }
row()  { printf '  %-6s %-42s %s\n' "$1" "$2" "$3"; }

# exists <path>：文件/目录/链接存在即 0
exists() { [ -e "$1" ] || [ -L "$1" ]; }

hdr "=== A. 已在永久区（[P] 不需自愈，别给它们加自愈）==="
p_count=0
chk_permanent() { # $1=显示名 $2=路径
  if exists "$2"; then row "[P]" "$1" "$2"; p_count=$((p_count+1))
  else row "[P?]" "$1" "$2  ← 缺失（应在永久区）"; fi
}
chk_permanent "Hermes 程序+数据 (HERMES_HOME)"        "$HERMES_HOME"
chk_permanent "Hermes 配置/密钥"                      "$HERMES_HOME/config.yaml"
chk_permanent "Hermes skills"                         "$HERMES_HOME/skills"
chk_permanent "Hermes plugins"                        "$HERMES_HOME/plugins"
chk_permanent "Hermes sessions/state"                 "$HERMES_HOME/sessions"
chk_permanent "runtime 补丁自愈清单 + 补丁包"          "$PATCH_ROOT"
chk_permanent "workspace 脚本/离线包/备份"             "$HOME_ROOT/workspace/setup"
chk_permanent "浏览器采集栈 (enhance 全栈)"            "$ENHANCE_DIR"
chk_permanent "增强版 venv (ddddocr+patchright)"       "$ENHANCE_DIR/venv"
chk_permanent "Firefox profile (CA 信任/cookies)"      "$ENHANCE_DIR/probe-profile"
chk_permanent "Camofox 二进制"                        "$HOME_ROOT/.cache/camoufox"
chk_permanent "Camofox profile (cookies/存储)"         "$HOME_ROOT/.camofox/profiles"
chk_permanent "Camofox 启动器 (两份)"                 "$HOME_ROOT/bin/camofox-start"
chk_permanent "VNC/desktop 持久 deb 包"               "$HOME_ROOT/camofox-browser/.vnc-stack/debs"
chk_permanent "hermes-start (自愈入口)"               "$HOME_ROOT/bin/hermes-start"
chk_permanent "SSH 公钥/配置"                         "$HOME_ROOT/.ssh/authorized_keys"
say "  —— 之上 $p_count 项：重启后天然还在。绝不删除、绝不因自愈重建。"

hdr "=== B. 不在永久区但搬过去就永久（[M] 应搬家而非自愈）==="
m_count=0
chk_movable() { # $1=显示名 $2=当前路径（易失） $3=建议永久路径
  if exists "$2"; then row "[M]" "$1" "现: $2"; row "    " "" "→ 建议搬到: $3"; m_count=$((m_count+1))
  else row "[M?]" "$1" "（当前不存在，搬家后此处为空）"; fi
}
chk_movable "hermes-gateway.pid"      "/tmp/hermes-gateway.pid"     "$HERMES_HOME/gateway.pid"
chk_movable "camofox-start.lock"      "/tmp/camofox-start.lock"     "$HERMES_HOME/locks/"
chk_movable "browse-stack-start.lock" "/tmp/browse-stack-start.lock" "$HERMES_HOME/locks/"
chk_movable "hermes-start.lock"       "/tmp/hermes-start.lock"      "$HERMES_HOME/locks/"
chk_movable "xvfb92.pid"              "/tmp/xvfb92.pid"             "$HERMES_HOME/locks/"
say "  —— $m_count 项：pid/lock 属于运行时状态。**pid 文件搬永久区有意义**（跨重启可排查），"
say "     lock 文件搬到永久区需配合 stale 探测（否则一次强杀会让自愈永远卡住）。"
say "     判定：锁类建议留 /tmp（重启自然失效正是想要的语义），pid 类建议搬永久区。"

hdr "=== C. 搬不走 / 必须在易失区重建（[H] 必须接自愈）==="
h_count=0
chk_healable() { # $1=显示名 $2=探针路径或命令描述 $3=自愈实体
  if [ -n "$2" ] && exists "$2"; then row "[H]" "$1" "$3"; h_count=$((h_count+1))
  else row "[H?]" "$1" "$3  ← 探针 $2 当前不在（可能本次重启后未拉起，下一轮自愈会补）"; fi
}
chk_healable "Hermes Gateway 进程"      "/tmp/hermes-gateway.pid" "hermes-start + hermes-selfheal cron (5m)"
chk_healable "Hermes runtime 本地补丁"  "$PATCH_ROOT"             "hermes-start::apply_runtime_local_patches"
chk_healable "cron 守护 + 看门狗条目"   "/usr/bin/crontab"        "root crontab + watchdog.sh (1m)"
chk_healable "Camofox 浏览器服务"       "/tmp/camofox-start.lock" "camofox-start.sh + camofox-selfheal cron (5m)"
chk_healable "Xvfb :92 显示"           "/tmp/xvfb92.pid"         "ensure-display.sh + browse-stack-start.sh (5m)"
chk_healable "NSSDB CA 信任"            "$ENHANCE_DIR/probe-profile" "setup-profile.sh（profile 在永久区，但信任库会被重置）"
chk_healable "VNC 系统包 (deb)"         "/usr/bin/x11vnc"         "camofox-browser/.vnc-stack/debs 恢复"
chk_healable "cf-probe 探针二进制"      "/usr/local/bin/cf-probe" "restore-all.sh → run-probe-install.sh"
chk_healable "MuseAutoApprove daemon"   "$HOME_ROOT/workspace/muse-guardian/MuseAutoApprove/muse-daemon.cjs" "watchdog.sh + restore-all.sh"
chk_healable "开机恢复链"               "$HOME_ROOT/init.sh"      "home-init 钩子 → restore-all.sh"
say "  —— $h_count 项：重启后确实消失，且都有自愈覆盖。"

hdr "=== D. 冗余自愈审查（第 4 步：确认已有方案是否合理）==="
redundant=0
check_redundant() { # $1=自愈实体描述 $2=被保护物是否已在永久区(0/1)
  if [ "$2" = "1" ]; then row "[R]" "$1" "被保护物已在永久区 → 此自愈冗余，可删"; redundant=$((redundant+1))
  else row "[R-ok]" "$1" "被保护物确在易失区 → 合理，保留"; fi
}

# D1. runtime 补丁自愈：被保护物=补丁包（永久区），但保护目标=工作树改动（易失）→ 合理
row "[R-ok]" "runtime 本地补丁自愈" "补丁包在永久区，工作树改动在易失区 → 合理"

# D2. guardian 是否还在管 hermes（应为 skip，否则重复自愈）
if grep -q "hermes 由用户自有自愈体系管理，guardian 跳过" "$SETUP_DIR/restore-all.sh" 2>/dev/null; then
  row "[R-ok]" "guardian 跳过 Hermes" "restore-all.sh 已 guard，无重复自愈"
else
  row "[R]" "guardian 仍管 Hermes" "restore-all.sh 未 guard → 与 hermes-start 重复自愈，应改回 skip"
  redundant=$((redundant+1))
fi

# D3. restore-hermes.sh 是否被 guard 禁用（应为禁用，否则每次 restore 下官方 latest）
if grep -q "已禁用" "$SETUP_DIR/restore-hermes.sh" 2>/dev/null; then
  row "[R-ok]" "restore-hermes.sh 已 guard" "不会下官方 latest，不钉版本架构冲突"
else
  row "[R]" "restore-hermes.sh 仍活动" "会下载官方 latest，与钉版本冲突，应 guard"
  redundant=$((redundant+1))
fi

# D4. 重复启动脚本（同一内容两份，cron 只该指向一份）
# 判定权威来源：hermes cron jobs.json 的 script 字段 + root crontab。
# cron 没引用的那份就是纯冗余（手动入口用绝对路径，少一份不会少功能）。
CRON_SCRIPTS=""
if [ -f "$HERMES_HOME/cron/jobs.json" ]; then
  CRON_SCRIPTS="$(python3 - <<'PY' 2>/dev/null
import json, pathlib
try:
    d = json.loads(pathlib.Path('/home/hatch/.hermes/cron/jobs.json').read_text())
except Exception:
    raise SystemExit
jobs = d if isinstance(d, list) else d.get('jobs', d)
if isinstance(jobs, dict):
    jobs = list(jobs.values())
for j in jobs:
    s = j.get('script') or j.get('command')
    if s:
        print(str(s).strip())
PY
)"
fi
CRON_SCRIPTS="$CRON_SCRIPTS $(crontab -l -u root 2>/dev/null | grep -oE '[^ ]+\.sh' | tr '\n' ' ')"

cron_uses() { # $1=相对文件名；cron 引用过返回 0
  case " $CRON_SCRIPTS " in *" $1 "*) return 0 ;; esac
  return 1
}

declare -A seen_md5=()      # key = 内容 md5；value = 首个见到的路径
declare -A dup_reported=()  # key = 内容 md5；已报过一次就不再报
declare -a dup_found=()
for f in "$HERMES_HOME/scripts/camofox-start.sh" "$HOME_ROOT/bin/camofox-start" \
         "$HERMES_HOME/scripts/muse-browser-start.sh" \
         "$HOME_ROOT/bin/muse-browser-start.sh" "$HERMES_HOME/scripts/camofox-start"; do
  [ -f "$f" ] || continue
  _real="$(readlink -f "$f" 2>/dev/null || echo "$f")"
  _md5=""
  [ -f "$_real" ] && _md5="$(md5sum "$_real" | cut -d' ' -f1)"
  [ -n "$_md5" ] || continue
  # 按内容去重：同一 md5 的第一份登记，后续命中即重复
  if [ -z "${seen_md5[$_md5]:-}" ]; then
    seen_md5[$_md5]="$f"
    continue
  fi
  [ -n "${dup_reported[$_md5]:-}" ] && continue
  dup_reported[$_md5]=1
  _bn="$(basename "$f")"
  _keep="${seen_md5[$_md5]}"
  if cron_uses "$_bn"; then _keep="$f"; _rm="${seen_md5[$_md5]}"; else _rm="$f"; fi
  row "[R]" "重复启动脚本" "md5 $_md5"
  row "    " "保留" "$_keep"
  row "    " "删除" "$_rm   ← 手动入口若引用它，先改绝对路径再删"
  dup_found+=("$_rm")
  redundant=$((redundant+1))
done
if [ "${#dup_found[@]}" -eq 0 ]; then
  row "[R-ok]" "无重复启动脚本" "每份内容唯一"
fi

# D5. 已接自愈但其目标本该在永久区（举例：若有 cron 在搬已经永久的东西）
if grep -q "cp -rf.*config.yaml.*/tmp" "$SETUP_DIR"/*.sh 2>/dev/null; then
  row "[R]" "可疑：把永久区内容备份到易失区" "见 setup/ 下脚本 → 备份目标应改永久区"
  redundant=$((redundant+1))
else
  row "[R-ok]" "无" "未发现'把永久区内容往易失区搬'的配置"
fi

hdr "=== 汇总 ==="
say "  [P] 永久区，不需自愈 : $p_count"
say "  [M] 该搬家不接自愈   : $m_count（多为 pid/lock，按类型分别处理）"
say "  [H] 必须接自愈        : $h_count"
say "  [R] 冗余自愈待清理     : $redundant"
say ""
say "  输出仅判定，不执行任何变更。搬家/删除请按 [M]/[R] 行的人工结论逐个做。"
if [ "$redundant" -gt 0 ]; then exit 3; fi
exit 0
