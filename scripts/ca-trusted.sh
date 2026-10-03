#!/usr/bin/env bash
# 公共检查: probe-profile 是否信任 egress CA
#
# 为什么不能用固定 nickname:
#   camoufox 会自动把 CA 导成 "<CN> - Hatch", 我们 setup 用裸 CN 导入会变成
#   第二条; 两边 nickname 不一致会让 "certutil -V -n <CN>" 误报缺失。
#   所以判据与别称无关: DB 里是否存在 trust 含 C,C 且指纹匹配的条目。
#
# 两个易踩的坑 (本机实测):
#   1. nickname 含空格 -> 不能 awk '{print $1}', 要从行尾 trust 反推切分
#   2. certutil -L -n <nick> 输出人读文本不是 PEM -> 必须加 -a 才能喂 openssl
#
# 退出码: 0=已信任, 1=未信任/缺失
set -u
PROFILE=/home/hatch/workspace/enhance/probe-profile
CA=/home/hatch/.camofox/egress-ca.pem

[ -f "$PROFILE/cert9.db" ] || exit 1
[ -f "$CA" ] || exit 1

FP=$(openssl x509 -in "$CA" -noout -fingerprint -sha256 2>/dev/null | sed -n 's/.*=//p' | tr -d ':')
[ -n "$FP" ] || exit 1

# trust 在最后一列, nickname 是它之前的所有内容 (nickname 可含空格)
# 注意: while 在管道子 shell 里, exit 出不去 -> 用临时文件回传结果
RES=$(mktemp)
trap 'rm -f "$RES"' EXIT
# NR>3 跳过表头两行+空行; NF>=2 保证至少有 nickname 和 trust
certutil -d "sql:$PROFILE" -L 2>/dev/null | awk 'NR>3 && NF>=2 {trust=$NF; $NF=""; sub(/[ \t]+$/,""); print $0 "\t" trust}' > /tmp/_ca_list.$$
while IFS="$(printf '\t')" read -r nick trust; do
  [ -n "$nick" ] || continue
  case "$trust" in *C,C*) ;; *) continue ;; esac
  db_fp=$(certutil -d "sql:$PROFILE" -L -n "$nick" -a 2>/dev/null \
          | openssl x509 -noout -fingerprint -sha256 2>/dev/null \
          | sed -n 's/.*=//p' | tr -d ':')
  if [ -n "$db_fp" ] && [ "$db_fp" = "$FP" ]; then
    echo "$nick" > "$RES"
    break
  fi
done < /tmp/_ca_list.$$
rm -f /tmp/_ca_list.$$

if [ -s "$RES" ]; then
  echo "trusted via: $(cat "$RES")"
  exit 0
fi
exit 1
