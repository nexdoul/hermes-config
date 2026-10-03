#!/bin/bash
# 云下载硬停：北京时间 23:55 之后停止所有云下载动作。
# 做法：给 collect5 driver 及其 run.py 子进程发 TERM（run.py 有断点，
# 已提交的离线任务与已抓到的 records checkpoint 都会保留在盘上）。
# pattern 写在本文件内，不进命令行 —— 否则 pgrep 会匹配到自己的 exec shell。
set -u
SELF=$$
STAMP=/home/hatch/code/javdb/logs/.clouddl-stopped-at
echo "[hardstop $(date -u +%H:%M:%S)] sending TERM"
for pid in $(pgrep -f 'collect5-driver' ; pgrep -f 'run.py --name' ) ; do
    [ -z "$pid" ] && continue
    [ "$pid" = "$SELF" ] && continue
    cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null || true)
    case "$cmd" in
        *pgrep*|*pkill*|*kill-collect5*|*clouddl-hardstop*) continue ;;
    esac
    echo "TERM $pid :: ${cmd:0:120}"
    kill -TERM "$pid" 2>/dev/null || true
done
sleep 5
for pid in $(pgrep -f 'run.py --name') ; do
    [ -z "$pid" ] && continue
    [ "$pid" = "$SELF" ] && continue
    cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null || true)
    case "$cmd" in *pgrep*|*pkill*) continue ;; esac
    echo "KILL $pid :: ${cmd:0:120}"
    kill -KILL "$pid" 2>/dev/null || true
done
date -u +%s > "$STAMP"
echo "[hardstop $(date -u +%H:%M:%S)] done"
exit 0
