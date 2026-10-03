#!/usr/bin/env bash
# 浏览器采集统一入口 (重启自愈版)
#
# 用法:
#   browse.sh serp   <engine:bing|google> <query> [outname]
#   browse.sh site   <url> [more urls...]
#   browse.sh zhihu  <hot|url>
#   browse.sh weibo  <hot|search:keyword>
#   browse.sh doctor
#
# 重启自愈三要素 (缺一重启后必坏):
#   1. Xvfb :92 会随容器重启消失  -> 先跑 ensure-display.sh 自举
#   2. node_modules 解析依赖 cwd  -> 永远 cd /home/hatch/camofox-browser 再执行
#   3. egress MITM 代理           -> proxy 显式写进启动参数 (环境变量对 Firefox 无效),
#                                    profile 必须已导入 egress CA (trust=CT,C,C)
#   不要用 Chromium: 本机 Chrome 经该代理一律 net::ERR_EMPTY_RESPONSE
#   (完整诊断见 /home/hatch/workspace/enhance/CHROME-PATH-FINDINGS.md)
set -uo pipefail

APP=/home/hatch/camofox-browser
ENH=/home/hatch/workspace/enhance
SCRIPTS=$ENH/scripts
DATA=$ENH/data
mkdir -p "$DATA" "$ENH/logs"

# --- 依赖自检 (缺什么说什么, 不要静默失败) ---
if [ ! -x /home/hatch/.cache/camoufox/camoufox-bin ]; then
  echo "FATAL: camoufox-bin 缺失 (~/.cache/camoufox). 恢复: cd $APP && npx camoufox-js fetch" >&2; exit 1
fi
if [ ! -d "$APP/node_modules/playwright-core" ] || [ ! -d "$APP/node_modules/camoufox-js" ]; then
  echo "FATAL: camofox-browser 依赖缺失. 恢复: cd $APP && npm install" >&2; exit 1
fi
if [ ! -f "$ENH/probe-profile/cert9.db" ]; then
  echo "FATAL: probe-profile NSSDB 缺失. 恢复: bash $SCRIPTS/setup-profile.sh" >&2; exit 1
fi

bash "$SCRIPTS/ensure-display.sh" || { echo "FATAL: display 不可用" >&2; exit 1; }
export DISPLAY="${BROWSE_DISPLAY:-:92}"
export CAMOFOX_DISABLE_DEFAULT_ADDONS=1
cd "$APP"

cmd="${1:-help}"; shift || true
case "$cmd" in
  serp)
    engine="${1:?engine: bing|google}"; query="${2:?query}"; out="${3:-$(date +%s)}"
    node "$SCRIPTS/crawl-search.mjs" "$engine" "$query" "$DATA/serp-${engine}-${out}.json" 2>"$DATA/serp-${engine}-${out}.log"
    python3 -c "
import json
d=json.load(open('$DATA/serp-${engine}-${out}.json'))
print('engine=%s query=%s results=%s captcha=%s' % (d.get('engine'), d.get('query'), d.get('resultCount'), d.get('captchaFlag')))
for r in d.get('results', [])[:10]:
    print(' -', (r.get('title') or '')[:60], '|', (r.get('url') or '')[:80])
" ;;
  site)
    node "$SCRIPTS/probe-site.mjs" "$@" ;;
  zhihu)
    target="${1:-hot}"
    case "$target" in
      hot)      node "$SCRIPTS/probe-site.mjs" 'https://www.zhihu.com/hot' ;;
      explore)  node "$SCRIPTS/probe-site.mjs" 'https://www.zhihu.com/explore' ;;
      column)   node "$SCRIPTS/probe-site.mjs" 'https://zhuanlan.zhihu.com/' ;;
      http*)    node "$SCRIPTS/probe-site.mjs" "$target" ;;
      *)        echo "usage: browse.sh zhihu {hot|explore|column|<url>}" >&2; exit 1 ;;
    esac ;;
  weibo)
    target="${1:-hot}"
    case "$target" in
      hot)   node "$SCRIPTS/probe-site.mjs" 'https://s.weibo.com/top/summary' ;;
      search) node "$SCRIPTS/probe-site.mjs" "https://s.weibo.com/weibo?q=${2:?keyword}" ;;
      *)      node "$SCRIPTS/probe-site.mjs" 'https://s.weibo.com/top/summary' ;;
    esac ;;
  doctor)
    exec bash "$SCRIPTS/doctor.sh" ;;
  *)
    echo "usage: browse.sh {serp|site|zhihu|weibo|doctor} ..."; exit 1 ;;
esac
