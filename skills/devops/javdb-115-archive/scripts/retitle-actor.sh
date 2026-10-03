#!/usr/bin/env bash
# retitle-actor.sh — 给一个演员目录批量补中文标题（工程化入口）
#
# 用法: retitle-actor.sh <演员目录名> [批次大小]
#   例: retitle-actor.sh 榊原萌 10
#
# 一步做完：冻结清单 → 切批 → 逐批 apply(--resume 断点续跑) → 前后对比。
# agent 只需最后核验它打印的计数，不需要逐步介入。
#
# 依赖的环境（脚本内已设默认，可被外部覆盖）:
#   JAVDB_SOURCE_PROXY=http://127.0.0.1:17890   krvps SSH 隧道，javdb 唯一可达出口
#   TITLE_ATTEMPTS=4                            relay 偶发空答案，逐片重试
set -u

ROOT=${JAVDB_ROOT:-/home/hatch/code/javdb}
ORG=$ROOT/115DailyOrg
PY=/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/venv/bin/python
STAMP=$(date -u +%Y%m%dT%H%M%S)

ACTOR=${1:-}
BATCH=${2:-10}
if [ -z "$ACTOR" ]; then
    echo "用法: $0 <演员目录名> [批次大小]"
    exit 2
fi

DIR="/我的视频/$ACTOR"
LOGDIR=$ROOT/logs/retitle-$ACTOR-$STAMP
mkdir -p "$LOGDIR"
echo "[$(date -u +%H:%M:%S)] actor=$ACTOR dir=$DIR batch=$BATCH"
echo "[$(date -u +%H:%M:%S)] artifacts -> $LOGDIR"

export PYTHONPATH=$ORG:$ORG/_internal:$ROOT/115re/_internal:$ROOT/115re:$ROOT/115pan/_internal:$ROOT/115pan:$ROOT
export JAVDB_ENV_ROOT=$ROOT/env
export JAVDB_SOURCE_PROXY=${JAVDB_SOURCE_PROXY:-http://127.0.0.1:17890}
export TITLE_ATTEMPTS=${TITLE_ATTEMPTS:-4}

cd "$ORG" || exit 1

# 1. 冻结清单。115driver 偶发瞬时失败（wrapper/隧道抖动），一次失败就
#    整体退出太脆，所以重试 3 次。
echo "[$(date -u +%H:%M:%S)] 冻结文件名清单"
LISTED=0
for attempt in 1 2 3; do
    if "$ROOT/env/bin/115driver" ls --json "$DIR" 2>/dev/null > "$LOGDIR/listing.json"; then
        if "$PY" -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get('success') else 1)" "$LOGDIR/listing.json"; then
            LISTED=1
            break
        fi
    fi
    echo "[$(date -u +%H:%M:%S)]   列目录第 $attempt 次失败，重试"
    sleep 5
done
if [ "$LISTED" -ne 1 ]; then
    echo "FATAL: 3 次都无法列目录 $DIR"
    exit 1
fi
"$PY" - "$LOGDIR/listing.json" "$LOGDIR/names.txt" <<'PYEOF'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding='utf-8'))
files = [x for x in data.get('data', {}).get('files', []) if not x.get('is_dir')]
with open(dst, 'w', encoding='utf-8') as f:
    for x in files:
        f.write(x['name'] + '\n')
print(f'  files={len(files)}')
PYEOF
TOTAL=$(grep -c . "$LOGDIR/names.txt" || echo 0)
echo "[$(date -u +%H:%M:%S)] 待处理文件: $TOTAL"

# 2. 切批：一批就是一个损失窗口（identify 完才落 state）
split -l "$BATCH" "$LOGDIR/names.txt" "$LOGDIR/batch-"
BATCH_N=$(ls "$LOGDIR"/batch-* 2>/dev/null | wc -l)
echo "[$(date -u +%H:%M:%S)] 切成 $BATCH_N 批"

# 3. 逐批 apply。--resume 让重跑跳过已完成项，所以整脚本可安全重复执行。
i=0
for bf in "$LOGDIR"/batch-*; do
    i=$((i+1))
    n=$(grep -c . "$bf" || echo 0)
    if [ "$n" -eq 0 ]; then continue; fi
    echo "[$(date -u +%H:%M:%S)] === 批次 $i/$BATCH_N ($n 个) ==="
    "$PY" dailyorg.py --state-dir "$ROOT/runtime/dailyorg" \
        --run-name "retitle-$ACTOR-b$i" \
        retitle --registry-dir "$DIR" --names-file "$bf" --apply --resume \
        > "$LOGDIR/batch-$i.log" 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "[$(date -u +%H:%M:%S)]   批次 $i rc=$rc → $LOGDIR/batch-$i.log"
        tail -5 "$LOGDIR/batch-$i.log" | sed 's/^/    /'
        continue
    fi
    grep -E '^(APPLIED|DRY-RUN)|^verified|^pending|^unresolved|^failed' "$LOGDIR/batch-$i.log" | sed 's/^/    /'
done

# 4. 前后对比：按 file_id diff，不要数数（前 N 个已改名会看起来像完成）
echo "[$(date -u +%H:%M:%S)] 重列目录做前后对比"
LISTED2=0
for attempt in 1 2 3; do
    if "$ROOT/env/bin/115driver" ls --json "$DIR" 2>/dev/null > "$LOGDIR/listing-after.json"; then
        LISTED2=1
        break
    fi
    echo "[$(date -u +%H:%M:%S)]   重列第 $attempt 次失败，重试"
    sleep 5
done
"$PY" - "$LOGDIR/listing.json" "$LOGDIR/listing-after.json" "$ACTOR" <<'PYEOF'
import json, re, sys
before_p, after_p, actor = sys.argv[1], sys.argv[2], sys.argv[3]

def load(p):
    d = json.load(open(p, encoding='utf-8'))
    return {x['file_id']: x for x in d.get('data', {}).get('files', [])}

b, a = load(before_p), load(after_p)
# 裸名判据：'<演员> <番号>.ext'，去掉演员名与番号后无别的内容。
# 注意不能用「含汉字」判据——演员名本身就是汉字。
bare = re.compile(r'^' + re.escape(actor) + r'\s+[A-Za-z0-9][A-Za-z0-9\-_]*\.[A-Za-z0-9]+$')

def classify(m):
    files = {k: v for k, v in m.items() if not v.get('is_dir')}
    naked = [k for k, v in files.items() if bare.match(v['name'])]
    return len(files), len(naked)

tb, nb = classify(b)
ta, na = classify(a)
print(f'  文件: {tb} -> {ta}')
print(f'  裸名(缺标题): {nb} -> {na}')
renamed = [k for k in a if k in b and a[k]['name'] != b[k]['name']]
missing = [k for k in b if k not in a]
added = [k for k in a if k not in b]
print(f'  改名: {len(renamed)}  消失: {len(missing)}  新增: {len(added)}')
for k in missing[:10]:
    print('    MISSING', b[k]['name'])
for k in added[:10]:
    print('    ADDED  ', a[k]['name'])
PYEOF

echo "[$(date -u +%H:%M:%S)] 完成。证据在 $LOGDIR/"
