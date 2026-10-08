#!/usr/bin/env bash
# 采集能力自检: 一眼看清重启后这套能力是否还活着
#
# 用法: bash /home/hatch/workspace/enhance/scripts/doctor.sh
# 退出码: 0=全部就绪, 1=有缺失项
set -uo pipefail

ENH="${BROWSE_STACK_ROOT:-${HOME}/.cache/browse-stack}"
APP="${CAMOFOX_APP_DIR:-${HOME}/camofox-browser}"
PROFILE=$ENH/probe-profile
DISPLAY="${BROWSE_DISPLAY:-:92}"

fail=0
ok()   { printf '  [OK]   %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=1; }
warn() { printf '  [WARN] %s\n' "$1"; }

echo "=== 1. 显示 (重启后最先丢的就是它) ==="
if DISPLAY="$DISPLAY" timeout 3 xdpyinfo >/dev/null 2>&1; then
  ok "DISPLAY $DISPLAY 可用"
else
  bad "DISPLAY $DISPLAY 不可用 -> browse.sh 会自动自举, 或手动 bash $ENH/scripts/ensure-display.sh"
fi

echo "=== 2. 浏览器二进制与依赖 ==="
[ -x "$CAMOUFOX_BIN" ] && ok "camoufox-bin 存在" || bad "camoufox-bin 缺失 (cd $APP && npx camoufox-js fetch)"
[ -d "$APP/node_modules/playwright-core" ] && ok "playwright-core 已装" || bad "playwright-core 缺失 (cd $APP && npm install)"
[ -d "$APP/node_modules/camoufox-js" ]     && ok "camoufox-js 已装"     || bad "camoufox-js 缺失"

echo "=== 3. egress CA / profile ==="
[ -f "$EGRESS_CA" ] && ok "egress CA 文件存在" || bad "egress CA 缺失"
if [ -f "$PROFILE/cert9.db" ]; then
  if CANICK_OUT=$(bash "$ENH/scripts/ca-trusted.sh" 2>/dev/null); then
    ok "probe-profile 信任 egress CA (SSL 校验通过; $CANICK_OUT)"
  else
    bad "probe-profile 有 NSSDB 但不信任 egress CA -> bash $ENH/scripts/setup-profile.sh"
  fi
else
  bad "probe-profile NSSDB 缺失 -> bash $ENH/scripts/setup-profile.sh"
fi

echo "=== 4. 验证码识别 (ddddocr) ==="
PY=$ENH/venv/bin/python
if [ -x "$PY" ]; then
  if "$PY" -c 'import ddddocr' 2>/dev/null; then
    ok "ddddocr 可导入 ($("$PY" -c 'import ddddocr,sys;print(getattr(ddddocr,"__version__","installed"))' 2>/dev/null))"
  else
    bad "venv 存在但 ddddocr 不可导入 -> $PY -m pip install ddddocr"
  fi
else
  bad "venv 缺失 ($ENH/venv); ddddocr 需重装: python3 -m venv $ENH/venv && $PY -m pip install ddddocr"
fi

echo "=== 5. 网络策略备忘 (不测, 只提醒) ==="
warn "Chromium 路线不可用: net::ERR_EMPTY_RESPONSE, 诊断见 $ENH/CHROME-PATH-FINDINGS.md"
warn "egress 代理: ${EGRESS_PROXY:-<未设置>} (环境变量对 Firefox 无效, 必须显式传入)"

echo "=== 6. 已采集数据 ==="
n_data=$(ls -1 "$ENH"/data/*.json 2>/dev/null | wc -l)
n_res=$(ls -1 "$ENH"/results-*.json 2>/dev/null | wc -l)
n_shots=$(ls -1 "$ENH"/shots/*.png 2>/dev/null | wc -l)
ok "SERP 结果文件: data/=$n_data, 根目录=$n_res, 截图=$n_shots"

echo
[ "$fail" -eq 0 ] && echo "结论: 采集能力就绪" || echo "结论: 有缺失项, 按上面提示修复"
exit "$fail"
