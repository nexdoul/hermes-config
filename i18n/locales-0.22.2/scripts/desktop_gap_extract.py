#!/usr/bin/env python3
"""
desktop_gap_extract.py — 提取 Hermes 0.22.0 desktop i18n 的 "en 有、zh overlay 无" 键。

原理（与上游 overlay-completeness.test.ts 同口径）：
  - en.ts 导出 `en: Translations`（完整英文基线）
  - zh.ts 导出 `zhOverrides`（部分覆盖），经 defineLocale 深合并到 en 之上
  - flattenMessageKeys(tree) 收集全部叶键（函数/数组也算一个叶）
  - 缺口 = flatten(en) - flatten(zhOverrides)

本脚本用纯 Python 解析 TS 对象字面量（无 node_modules，无法跑 tsc/vitest），
处理：字面量字符串、模板字面量、箭头函数模板、嵌套对象、以及从 zh_*.ts / en_*.ts
import 进来的具名对象（按 import 图递归解析）。

输出：JSON（键 -> 英文值）到 stdout 或文件。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

I18N = Path("/home/hatch/workspace/hermes-0220-migration/v0220-src/apps/desktop/src/i18n")


# ---------------------------------------------------------------------------
# 极简 TS 词法/结构扫描器
# ---------------------------------------------------------------------------

def strip_comments(src: str) -> str:
    """去掉 // 行注释与 /* */ 块注释（不进入字符串）。"""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in ("'", '"', "`"):
            # 复制整个字符串字面量
            q = c
            out.append(c)
            i += 1
            while i < n:
                if src[i] == "\\":
                    out.append(src[i:i + 2])
                    i += 2
                    continue
                out.append(src[i])
                if src[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def find_matching_brace(src: str, start: int) -> int:
    """src[start] == '{' ，返回配对 '}' 的下标。字符串/模板内的括号不计。"""
    depth = 0
    i = start
    n = len(src)
    while i < n:
        c = src[i]
        if c in ("'", '"', "`"):
            q = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                # 模板里的 ${...} —— 内部可能含对象字面量，但键值不影响括号平衡的大部分情形
                if q == "`" and src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                    j = i + 2
                    d = 1
                    while j < n and d:
                        if src[j] == "{":
                            d += 1
                        elif src[j] == "}":
                            d -= 1
                        j += 1
                    i = j
                    continue
                i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces")


# `.match(body, i)` 已把匹配锚在 i 处，故模式里不能再用 `^`（会变成只匹配串首）
KEY_RE = re.compile(r"""\s*["']?([A-Za-z_$][A-Za-z0-9_$]*)["']?\s*:""")
# 键可能带引号（含点/连字符），如 'command-palette': 或 'local-runtime-update':
QKEY_RE = re.compile(r"""\s*["']([^"']+)["']\s*:""")


def parse_object(src: str, start: int, imported: dict[str, object]) -> dict:
    """解析从 src[start]=='{' 开始的对象字面量 -> dict（叶值用哨兵表示）。"""
    end = find_matching_brace(src, start)
    body = src[start + 1:end]
    return parse_body(body, imported)


def parse_body(body: str, imported: dict[str, object]) -> dict:
    result: dict[str, object] = {}
    i = 0
    n = len(body)
    while i < n:
        # 键只能出现在 { 或 , 之后（允许空白/注释已剥离），避免匹配到值内部的 `foo:`
        k = i
        while k < n and body[k] in " \t\r\n":
            k += 1
        p = k - 1
        while p >= 0 and body[p] in " \t\r\n":
            p -= 1
        if p >= 0 and body[p] not in "{,":
            # 上一个非空白字符不是 { 或 , —— i 落在值内部，跳过
            i = k + 1
            continue
        m_q = QKEY_RE.match(body, k)
        m_k = KEY_RE.match(body, k)
        m = None
        if m_q and m_k:
            m = m_q if m_q.start() <= m_k.start() else m_k
        elif m_q:
            m = m_q
        elif m_k:
            m = m_k
        if not m:
            # 匿名 spread（`...obj,` 无键名）——直接展开到当前层
            if body[k:k + 3] == "...":
                sm = re.match(r"\.\.\.\s*([A-Za-z_$][A-Za-z0-9_$.]*)", body[k:])
                if sm:
                    val = resolve_ident(sm.group(1), imported)
                    if isinstance(val, dict):
                        for sk, sv in val.items():
                            result[sk] = sv
                    i = k + sm.end()
                    continue
            i = k + 1
            continue
        key = m.group(1)
        j = m.end()
        while j < n and body[j] in " \t\n\r":
            j += 1
        if j >= n:
            break
        value, nxt = parse_value(body, j, imported)
        if isinstance(value, dict) and "__spread__" in value:
            spread = value["__spread__"]
            if isinstance(spread, dict):
                b = result
                for sk, sv in spread.items():
                    if isinstance(b, dict):
                        b[sk] = sv
        else:
            result[key] = value
        i = nxt

    return result


def parse_value(body: str, j: int, imported: dict[str, object]):
    """
    返回 (值, 下一个待扫描下标)。
    值形式：
      '{' ... '}'             -> 嵌套对象 -> dict
      标识符                   -> 若在 imported 中，取其对象；否则字符串占位（如 FIELD_LABELS.x）
      '...' / "..."           -> 字符串
      `...`                   -> 模板字符串（含 ${} 视为函数）
      ( ... ) => `...`        -> 函数
      x => `...`              -> 函数
      [ ... ]                 -> 数组
    """
    n = len(body)
    c = body[j]

    if c == "{":
        end = find_matching_brace(body, j)
        obj = parse_body(body[j + 1:end], imported)
        return obj, end + 1

    if c in ("'", '"'):
        s, nxt = read_string(body, j)
        return s, nxt

    if c == "`":
        template, nxt = read_template(body, j)
        return {"__type": "string", "__text": template}, nxt  # 模板字面量本身也是字符串叶

    if c == "[":
        end = read_bracket(body, j)
        return {"__type": "array"}, end

    # 箭头函数：可能形如 `x => ` 或 `(a, b) => ` 或 `async x => `
    arrow = re.match(r"(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>\s*", body[j:])
    if arrow:
        k = j + arrow.end()
        # 箭头体可能是模板、字符串、对象、三元、或调用
        if k < n and body[k] == "`":
            tmpl, nxt = read_template(body, k)
            return {"__type": "func", "__text": tmpl}, nxt
        if k < n and body[k] in ("'", '"'):
            s, nxt = read_string(body, k)
            return {"__type": "func", "__text": s}, nxt
        if k < n and body[k] == "{":
            end = find_matching_brace(body, k)
            return {"__type": "func-obj"}, end + 1
        # 复杂表达式：吃到顶层逗号/换行
        nxt = skip_expression(body, k)
        return {"__type": "func"}, nxt

    # 标识符 / 复杂表达式（spread、导入对象、函数调用、常量引用）
    if body[j:j+3] == "...":
        m = re.match(r"\.\.\.\s*([A-Za-z_$][A-Za-z0-9_$.]*)", body[j:])
        if m:
            ident = m.group(1)
            nxt = j + m.end()
            val = resolve_ident(ident, imported)
            return {"__spread__": val}, nxt

    m = re.match(r"[A-Za-z_$][A-Za-z0-9_$.]*", body[j:])
    if m:
        ident = m.group(0)
        nxt = j + len(ident)
        val = resolve_ident(ident, imported)
        if val is not _UNRESOLVED:
            return val, nxt
        return {"__type": "expr", "raw": ident}, nxt

    # 兜底：跳过
    nxt = skip_expression(body, j)
    return {"__type": "expr", "raw": body[j:nxt].strip()[:60]}, nxt


_UNRESOLVED = object()


def resolve_ident(ident: str, imported: dict[str, object]):
    """解析 `A` 或 `A.b.c`，在 imported 表里逐层下钻；未解析返回 _UNRESOLVED。"""
    parts = ident.split(".")
    cur = imported.get(parts[0])
    if cur is None:
        return _UNRESOLVED
    for p in parts[1:]:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return _UNRESOLVED
    return cur


def skip_expression(body: str, j: int) -> int:
    """从 j 起跳到顶层逗号或换行（用于丢弃复杂表达式）。"""
    n = len(body)
    depth = 0
    while j < n:
        c = body[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return j
            depth -= 1
        elif c in ("'", '"', "`"):
            q = c
            j += 1
            while j < n:
                if body[j] == "\\":
                    j += 2
                    continue
                if body[j] == q:
                    j += 1
                    break
                j += 1
            continue
        elif c == "," and depth == 0:
            return j
        elif c == "\n" and depth == 0:
            return j
        j += 1
    return j


def read_string(body: str, j: int):
    q = body[j]
    i = j + 1
    n = len(body)
    buf = []
    while i < n:
        if body[i] == "\\":
            buf.append(body[i:i + 2])
            i += 2
            continue
        if body[i] == q:
            i += 1
            break
        buf.append(body[i])
        i += 1
    raw = "".join(buf)
    return decode_ts_string(raw), i


def decode_ts_string(raw: str) -> str:
    out = []
    i = 0
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            e = raw[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", "'": "'", '"': '"', "`": "`", "\\": "\\"}
            out.append(mapping.get(e, "\\" + e))
            i += 2
        else:
            out.append(raw[i])
            i += 1
    return "".join(out)


def read_template(body: str, j: int):
    """读取模板字面量，返回 (文本内容, 结束下标)。文本保留 ${expr} 原样。"""
    q = "`"
    i = j + 1
    n = len(body)
    buf = []
    while i < n:
        if body[i] == "\\":
            buf.append(body[i:i + 2])
            i += 2
            continue
        if body[i] == "$" and i + 1 < n and body[i + 1] == "{":
            # 保留 ${...} 表达式原文
            start = i
            i += 2
            d = 1
            while i < n and d:
                if body[i] == "{":
                    d += 1
                elif body[i] == "}":
                    d -= 1
                i += 1
            buf.append(body[start:i])
            continue
        if body[i] == q:
            i += 1
            break
        buf.append(body[i])
        i += 1
    return decode_ts_string("".join(buf)), i


def read_bracket(body: str, j: int) -> int:
    depth = 0
    i = j
    n = len(body)
    while i < n:
        c = body[i]
        if c in ("'", '"', "`"):
            q = c
            i += 1
            while i < n:
                if body[i] == "\\":
                    i += 2
                    continue
                if body[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


# ---------------------------------------------------------------------------
# 导入解析：加载 zh_*.ts / en_*.ts 中的导出对象
# ---------------------------------------------------------------------------

def load_module_exports(path: Path, imported: dict[str, object]) -> dict[str, object]:
    """解析一个 TS 文件里所有 `export const NAME... = {...}` 导出对象。"""
    src = strip_comments(path.read_text(encoding="utf-8"))
    exports: dict[str, object] = {}
    # 递归解析该文件自己的 import（子模块可能还引用更深的文件）
    local_imports = dict(imported)
    for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", src):
        names = [x.strip().split(" as ")[-1] for x in m.group(1).split(",") if x.strip()]
        mod = m.group(2)
        if not mod.startswith("."):
            continue
        dep = (path.parent / mod).resolve()
        for cand in (dep.with_suffix(".ts"), dep, dep.with_suffix(".tsx")):
            if cand.exists() and cand.is_file():
                sub = load_module_exports(cand, {})
                local_imports.update(sub)
                break
    for m in re.finditer(r"export\s+const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?::[^=]+)?=\s*", src):
        name = m.group(1)
        j = m.end()
        if j < len(src) and src[j] == "{":
            exports[name] = parse_object(src, j, local_imports)
        else:
            # 形如 defineFieldCopy({ ... }) / 其它包装调用：找第一个 `({` 并解析
            call = re.match(r"[A-Za-z_$][A-Za-z0-9_$.]*\s*\(\s*\{", src[j:])
            if call:
                brace = j + call.end() - 1
                exports[name] = parse_object(src, brace, local_imports)
    return exports


def load_external_object(path: Path, const_name: str) -> dict:
    """加载外部模块（如 @/app/settings/constants）中的某个导出对象。"""
    exports = load_module_exports(path, {})
    return exports.get(const_name, {})


def load_locale(fileglob: str) -> dict:
    """加载主文件（如 zh.ts）的指定导出。"""
    path = I18N / fileglob
    src = strip_comments(path.read_text(encoding="utf-8"))
    imported: dict[str, object] = {}
    ext = I18N.parent  # apps/desktop/src
    for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", src):
        names = [x.strip() for x in m.group(1).split(",") if x.strip()]
        mod = m.group(2)
        local = [x for x in names if x and not x.startswith("type ")]
        if mod.startswith("@/app/settings/constants"):
            for n in ("FIELD_LABELS", "FIELD_DESCRIPTIONS"):
                obj = load_external_object(ext / "app" / "settings" / "constants.ts", n)
                if obj:
                    imported[n] = obj
            continue
        if not mod.startswith("."):
            continue
        dep = (path.parent / mod).resolve()
        for cand in (dep.with_suffix(".ts"), dep.with_suffix(".tsx")):
            if cand.exists():
                sub = load_module_exports(cand, {})
                for n in local:
                    if n in sub:
                        imported[n] = sub[n]
                break
    # 主文件自身导出的对象
    own = load_module_exports(path, imported)
    own.update(imported)
    return own


def flatten(tree: object, prefix: str = "") -> dict[str, object]:
    """叶键收集：dict 递归；其余（含 __type 哨兵）视为叶。"""
    keys: dict[str, object] = {}
    if isinstance(tree, dict) and "__type" not in tree:
        for k, v in tree.items():
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict) and "__type" not in v:
                keys.update(flatten(v, p))
            else:
                keys[p] = v
    elif prefix:
        keys[prefix] = tree
    return keys


def value_repr(v: object) -> str:
    if isinstance(v, dict):
        t = v.get("__type")
        if t == "func" or t == "func-obj":
            return "(function)"
        if t == "array":
            return "(array)"
        if t == "string":
            return "(template)"
        return "(expr: %s)" % v.get("raw", "")
    return str(v)


def main():
    en_exports = load_locale("en.ts")
    zh_exports = load_locale("zh.ts")

    en_tree = en_exports.get("en")
    zh_tree = zh_exports.get("zhOverrides")
    if en_tree is None or zh_tree is None:
        print("FATAL: could not locate en / zhOverrides export", file=sys.stderr)
        sys.exit(1)

    en_flat = flatten(en_tree)
    zh_flat = flatten(zh_tree)

    # 上游 overlay-completeness.test.ts 排除 intro.*（display-only）
    def translatable(d):
        return {k: v for k, v in d.items() if not k.startswith("intro.")}

    en_t = translatable(en_flat)
    zh_t = translatable(zh_flat)

    missing = {k: en_t[k] for k in sorted(en_t) if k not in zh_t}

    out = {
        "en_keys": len(en_t),
        "zh_overlay_keys": len(zh_t),
        "missing_count": len(missing),
        "missing": {k: value_repr(v) for k, v in missing.items()},
        "__raw_types": {k: (v.get("__type") if isinstance(v, dict) else "string") for k, v in missing.items()},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
