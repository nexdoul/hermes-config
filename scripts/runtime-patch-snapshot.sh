#!/usr/bin/env bash
#
# runtime-patch-snapshot.sh — 把 runtime 里的本地改动重新生成为自愈补丁包。
#
# 干什么：
#   读 $HERMES_HOME/runtime-local-patches.list 里登记的每个 bundle，按各自的
#   files 清单把 runtime 工作树里的当前改动导出成 *.patch；
#   凡是改了但没登记进任何 bundle 的文件，自动扫进 _unassigned（绝不丢改动）。
#
# 何时跑：
#   - 本机 runtime 被基线重装清空后（hermes-start 已自动按 patches/ 重应用，
#     之后需要重生成更正版本时）
#   - 你新写了代码/改了 runtime 文件，想把它加进自愈名单时
#   - 钉版本基线变了（PINNED_UPSTREAM_COMMIT 变更），旧补丁目标 commit 不符需重生成时
#
# 幂等：重复跑得到同样的补丁；不碰 runtime 工作树内容（只在生成新文件补丁时
# 临时 add -N，跑完 reset 掉）。
#
set -uo pipefail

HERMES_HOME="/home/hatch/.hermes"
RUNTIME_GIT="$HERMES_HOME/npm/node_modules/hermes-agent/runtime/hermes-agent"
PATCH_ROOT="$HERMES_HOME/patches"
LIST_FILE="$HERMES_HOME/runtime-local-patches.list"

log()  { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

[ -f "$LIST_FILE" ] || { warn "清单不存在: $LIST_FILE"; exit 1; }
[ -d "$RUNTIME_GIT/.git" ] || { warn "runtime git 目录不存在: $RUNTIME_GIT"; exit 1; }

TARGET_COMMIT="$(git -C "$RUNTIME_GIT" rev-parse HEAD 2>/dev/null || true)"
[ -n "$TARGET_COMMIT" ] || { warn "取不到 runtime HEAD"; exit 1; }
log "runtime HEAD = ${TARGET_COMMIT:0:7}"
log "补丁目标 commit（写入各 bundle 的 meta）= $TARGET_COMMIT"

NEW_FILE_STAGED=""   # 需要跑完 reset 掉的 add -N 文件

# flatten <repo-relative-path> -> patch 文件名
flatten() { printf '%s' "$1" | tr '/' '_'; }

# export_one <bundle_dir> <repo-relative-path>
# 生成一个 patch；返回 0=有改动并生成，1=无改动（跳过），2=出错
export_one() {
  local _dir="$1" _f="$2" _flat _out
  _flat="$(flatten "$_f")"
  _out="$_dir/$_flat.patch"
  if git -C "$RUNTIME_GIT" ls-files --error-unmatch "$_f" >/dev/null 2>&1; then
    if git -C "$RUNTIME_GIT" diff --quiet -- "$_f"; then
      log "  SKIP   $_f（相对 HEAD 无改动）"
      return 1
    fi
    git -C "$RUNTIME_GIT" diff -- "$_f" > "$_out" || return 2
  else
    # untracked：add -N 让 git diff 输出 new-file 补丁，跑完统一 reset
    git -C "$RUNTIME_GIT" add -N -- "$_f" 2>/dev/null || return 2
    NEW_FILE_STAGED="$NEW_FILE_STAGED $_f"
    git -C "$RUNTIME_GIT" diff -- "$_f" > "$_out" || return 2
  fi
  if [ ! -s "$_out" ]; then
    warn "补丁为空: $_f"
    rm -f "$_out"
    return 2
  fi
  log "  EXPORT $_f  ->  $_out($(wc -c < "$_out") bytes)"
  return 0
}

# ---- 1. 按登记的 bundle 生成 ----
declare -a ALL_ASSIGNED=()
declare -a BUNDLE_DIRS=()
rc=0

while IFS='|' read -r _bundle _desc _rest; do
  case "$_bundle" in ''|\#*) continue ;; esac
  _desc="${_desc:-未命名 bundle}"
  _dir="$PATCH_ROOT/$_bundle"
  _files="$_dir/files"
  if [ ! -f "$_files" ]; then
    warn "bundle $_bundle 缺少 files 清单 ($_files)，跳过"
    rc=1
    continue
  fi
  log ""
  log "=== bundle: $_bundle ($_desc) ==="
  mkdir -p "$_dir"
  rm -f "$_dir"/*.patch
  _n=0
  while IFS= read -r _f || [ -n "$_f" ]; do
    case "$_f" in ''|\#*) continue ;; esac
    ALL_ASSIGNED+=("$_f")
    _n=$((_n+1))
    export_one "$_dir" "$_f" || { rc=1; }
  done < "$_files"
  # 登记但实际没改动的文件不进 meta 的 PATCH_COUNT 也没关系，count 只作信息
  {
    printf 'TARGET_COMMIT=%s\n' "$TARGET_COMMIT"
    printf 'BUNDLE=%s\n' "$_bundle"
    printf 'DESCRIPTION=%s\n' "$_desc"
    printf 'DECLARED_FILES=%s\n' "$_n"
    printf 'PATCH_COUNT=%s\n' "$(ls -1 "$_dir"/*.patch 2>/dev/null | wc -l)"
    printf 'SNAPSHOT_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$_dir/meta"
  log "  meta: $(ls -1 "$_dir"/*.patch 2>/dev/null | wc -l) patch, $_n declared"
done < "$LIST_FILE"

# ---- 2. 扫出未登记的本地改动，自动进 _unassigned ----
if [ -n "$NEW_FILE_STAGED" ] || true; then :; fi
dirty="$(git -C "$RUNTIME_GIT" status --porcelain 2>/dev/null || true)"
is_assigned() {
  local _x="$1" _a
  for _a in "${ALL_ASSIGNED[@]+"${ALL_ASSIGNED[@]}"}"; do
    [ "$_a" = "$_x" ] && return 0
  done
  return 1
}

declare -a UNASSIGNED=()
if [ -n "$dirty" ]; then
  while IFS= read -r _line; do
    [ -n "$_line" ] || continue
    # porcelain 前两列是 XY 状态码，第三列起才是空格+路径。
    # "?? path" / " M path" / "MM path" / " A path" 统一取前 2 字符之后的路径。
    _p="${_line#??}"
    _p="${_p# }"
    _p="${_p#\"}"
    _p="${_p%\"}"
    [ -n "$_p" ] || continue
    if is_assigned "$_p"; then continue; fi
    UNASSIGNED+=("$_p")
  done <<< "$dirty"
fi

if [ "${#UNASSIGNED[@]}" -gt 0 ]; then
  _dir="$PATCH_ROOT/_unassigned"
  log ""
  log "=== bundle: _unassigned (发现 ${#UNASSIGNED[@]} 个未登记改动) ==="
  mkdir -p "$_dir"
  rm -f "$_dir"/*.patch
  : > "$_dir/files"
  for _p in "${UNASSIGNED[@]}"; do
    echo "$_p" >> "$_dir/files"
    export_one "$_dir" "$_p" || rc=1
  done
  {
    printf 'TARGET_COMMIT=%s\n' "$TARGET_COMMIT"
    printf 'BUNDLE=_unassigned\n'
    printf 'DESCRIPTION=未归类本地改动（待人工归组到正式 bundle）\n'
    printf 'DECLARED_FILES=%s\n' "${#UNASSIGNED[@]}"
    printf 'PATCH_COUNT=%s\n' "$(ls -1 "$_dir"/*.patch 2>/dev/null | wc -l)"
    printf 'SNAPSHOT_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$_dir/meta"
  warn "有 ${#UNASSIGNED[@]} 个改动未登记到任何 bundle："
  for _p in "${UNASSIGNED[@]}"; do warn "  - $_p"; done
  warn "已自动收进 patches/_unassigned/（自愈名单内，不会丢）；"
  warn "但请把它归组：把路径写进正式 bundle 的 files 清单后重跑本脚本。"
else
  # 没有未登记改动：清掉残留的 _unassigned
  if [ -d "$PATCH_ROOT/_unassigned" ]; then
    rm -f "$PATCH_ROOT/_unassigned"/*.patch
    rm -f "$PATCH_ROOT/_unassigned/files"
    rmdir "$PATCH_ROOT/_unassigned" 2>/dev/null || true
    log ""
    log "_unassigned 已无内容，清空"
  fi
fi

# ---- 3. 撤掉临时 add -N（恢复 index 原状）----
if [ -n "$NEW_FILE_STAGED" ]; then
  git -C "$RUNTIME_GIT" reset -q -- $NEW_FILE_STAGED 2>/dev/null || true
fi

# ---- 4. 汇总 ----
log ""
log "=== 汇总 ==="
_total=0
for _d in "$PATCH_ROOT"/*/; do
  [ -d "$_d" ] || continue
  _n="$(ls -1 "$_d"*.patch 2>/dev/null | wc -l)"
  _total=$((_total+_n))
  printf '  %-34s %s patch\n' "$(basename "$_d")" "$_n"
done
log "  共 $_total 个补丁 -> $PATCH_ROOT"
log ""
log "自愈应用由 hermes-start 在基线重装后自动执行；登记新文件请编辑"
log "  $HERMES_HOME/runtime-local-patches.list   (bundle 列表)"
log "  $PATCH_ROOT/<bundle>/files               (每个 bundle 的路径清单)"
log "然后重跑本脚本。"

[ "$rc" = "0" ] && log "" && log "OK: 快照完成" || { log ""; log "OK: 快照完成（有 WARN，见上）"; }
exit 0
