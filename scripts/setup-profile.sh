#!/usr/bin/env bash
# 一次性环境修复: 重建 probe-profile 的 NSSDB 并导入 egress CA
#
# 何时需要跑:
#   - probe-profile 目录被删/损坏
#   - 容器重启后该目录内容丢失 (保险起见提供自修复)
#
# 为什么必须: 本机 HTTPS 全部经 MITM 代理, Firefox 不信任 egress CA 时
# 所有站点都打不开 (表现为超时或 SEC_ERROR)。trust 标志必须是 CT,C,C,
# 写成 C,, 会只信 S/MIME 不信 SSL —— 这是踩过的坑。
set -euo pipefail

PROFILE="${BROWSE_PROFILE:-${HOME}/.cache/browse-stack/probe-profile}"
CA="${EGRESS_CA:-${CAMOFOX_STATE_DIR:-${HOME}/.camofox}/egress-ca.pem}"

[ -f "$CA" ] || { echo "FATAL: egress CA 不存在: $CA" >&2; exit 1; }
command -v certutil >/dev/null 2>&1 || { echo "FATAL: certutil 未安装 (libnss3-tools)" >&2; exit 1; }

# NICKNAME 必须是 CA 证书自身的 CN。写成 'hatch-egress' 时 certutil 会用这个
# 字符串做新条目名, 但后续 certutil -L/-V -n 查不到 -> 会误判"CA 没导进去"。
NICKNAME=$(openssl x509 -in "$CA" -noout -subject -nameopt multiline 2>/dev/null | sed -n 's/^ *commonName *= *//p' | head -1)
[ -n "$NICKNAME" ] || { echo "FATAL: 无法从 $CA 读取 CN" >&2; exit 1; }
echo "CA nickname (来自证书 CN): $NICKNAME"

if [ ! -f "$PROFILE/cert9.db" ]; then
  echo "创建 NSSDB: $PROFILE"
  mkdir -p "$PROFILE"
  certutil -N --empty-password -d "sql:$PROFILE"
else
  echo "NSSDB 已存在: $PROFILE"
fi

echo "导入 egress CA (trust=CT,C,C, nickname=$NICKNAME)"
# 若 DB 里已有该 CA 的其它别称 (camoufox 会导成 "<CN> - Hatch"),
# certutil -A 会新建一条而不是覆盖, 之后 -n <CN> 查不到 -> 先按指纹删旧条目。
# 坑: nickname 含空格, 不能 awk '{print $1}'。
FP=$(openssl x509 -in "$CA" -noout -fingerprint -sha256 2>/dev/null | sed -n 's/.*=//p' | tr -d ':')
if [ -n "$FP" ]; then
  # NR>3 跳过表头两行+空行; NF>=2 保证至少有 nickname 和 trust
  certutil -d "sql:$PROFILE" -L 2>/dev/null \
    | awk 'NR>3 && NF>=2 {trust=$NF; $NF=""; sub(/[ \t]+$/,""); print $0 "\t" trust}' > /tmp/_setup_list.$$
  while IFS="$(printf '\t')" read -r nick trust; do
    [ -n "$nick" ] || continue
    # 坑: certutil -L -n 输出人读文本, 必须加 -a 才能喂 openssl 算指纹
    db_fp=$(certutil -d "sql:$PROFILE" -L -n "$nick" -a 2>/dev/null \
            | openssl x509 -noout -fingerprint -sha256 2>/dev/null \
            | sed -n 's/.*=//p' | tr -d ':')
    if [ "$db_fp" = "$FP" ]; then
      echo "删除同指纹旧条目: $nick"
      certutil -D -n "$nick" -d "sql:$PROFILE" 2>/dev/null || true
    fi
  done < /tmp/_setup_list.$$
  rm -f /tmp/_setup_list.$$
fi
certutil -A -n "$NICKNAME" -t 'CT,C,C' -i "$CA" -d "sql:$PROFILE"

echo "--- 结果 ---"
certutil -d "sql:$PROFILE" -L | tail -5
# 用与别称无关的判据确认 (ca-trusted.sh)
if bash "$(dirname "$0")/ca-trusted.sh" >/dev/null 2>&1; then
  echo "OK: egress CA 已作为 SSL CA 被信任"
else
  echo "FAIL: 导入后仍未通过信任检查" >&2
  exit 1
fi
