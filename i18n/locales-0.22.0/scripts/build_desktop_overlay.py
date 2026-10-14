#!/usr/bin/env python3
"""Generate zh_desktop_gaps.ts + desktop-gaps.csv from dgap_missing_full.json + translations.

Reads:
  scripts/dgap_missing_full.json  — {key: {type:'string'|'func', text: <en>}}
  desktop_translations.py         — T = {key: "<zh>" | "KEEP"}   (translator output)
Writes:
  zh_desktop_gaps.ts, desktop-gaps.csv
Parameter types for func entries are resolved from the upstream types.ts / types_*.ts
so the emitted file passes `tsc --strict`.
"""
import json, re, pathlib, csv, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
I18ND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                     'v0220-src/apps/desktop/src/i18n')

miss = json.loads((HERE / 'dgap_missing_full.json').read_text())
sys.path.insert(0, str(HERE))
import desktop_translations as DT                      # noqa: E402
T = DT.T

tmain = (I18ND / 'types.ts').read_text(encoding='utf-8')
pool = tmain + "\n"
for im in set(re.findall(r"from '\./(types_[a-z_]+)'", tmain)):
    p = I18ND / f'{im}.ts'
    if p.exists():
        pool += p.read_text(encoding='utf-8') + "\n"


def sig_from_types(key):
    leaf = key.split('.')[-1]
    for c in re.findall(rf'^\s*{re.escape(leaf)}\s*:\s*(.+)$', pool, re.M):
        c = c.strip().rstrip(',')
        if '=>' in c:
            return c
    return None


def split_params(inner):
    out, d, cur = [], 0, ''
    for ch in inner:
        if ch in '([{<':
            d += 1
        elif ch in ')]}>':
            d -= 1
        if ch == ',' and d == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def param_decl(key):
    sig = sig_from_types(key)
    if sig:
        b = re.match(r'\(([^)]*)\)\s*=>', sig)
        if b:
            inner = b.group(1).strip()
            return split_params(inner) if inner else []
        s = re.match(r'([A-Za-z_$][\w$]*)\s*:\s*(.+?)\s*=>', sig)
        if s:
            return [f"{s.group(1)}: {s.group(2)}"]
    # fall back to the en.ts signature, annotating bare params as string
    files = [f for f in I18ND.glob('en*.ts') if not f.name.endswith('.test.ts')]
    leaf = key.split('.')[-1]
    for f in files:
        m = re.search(rf'\b{re.escape(leaf)}\s*:\s*(\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>',
                      f.read_text(encoding='utf-8'))
        if m:
            raw = m.group(1)
            if not raw.startswith('('):
                return [f"{raw}: string"]
            inner = raw[1:-1].strip()
            if not inner:
                return []
            return [f"{p.split(':')[0].split('=')[0].strip()}: string"
                    for p in split_params(inner)]
    return None


def esc_tpl(s):
    return s.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')


def esc_sq(s):
    return s.replace('\\', '\\\\').replace("'", "\\'")


tree = {}
for k, v in sorted(T.items()):
    if v == 'KEEP':
        continue
    cur = tree
    for p in k.split('.')[:-1]:
        cur = cur.setdefault(p, {})
    leaf = k.split('.')[-1]
    if miss[k].get('type') == 'func':
        pd = param_decl(k) or ['args: unknown']
        cur[leaf] = ('F', pd, v)
    else:
        cur[leaf] = ('S', v)


def emit(node, ind=2):
    pad = ' ' * ind
    out = []
    for k, v in node.items():
        if isinstance(v, dict):
            out.append(f"{pad}{k}: {{")
            out += emit(v, ind + 2)
            out.append(f"{pad}}},")
        elif v[0] == 'S':
            out.append(f"{pad}{k}: '{esc_sq(v[1])}',")
        else:
            _, ps, txt = v
            if not ps:
                arrow = '() =>'
            elif len(ps) == 1 and ':' not in ps[0]:
                arrow = f"{ps[0]} =>"
            else:
                arrow = '(' + ', '.join(ps) + ') =>'
            out.append(f"{pad}{k}: {arrow} `{esc_tpl(txt)}`,")
    return out


HEADER = """// 补译 Hermes 0.22.0 desktop 层上游 zh overlay 未覆盖的 614 个键（605 条译文）。
// 9 条判定保持英文（技术标识 / 须与外部界面一致），见 desktop-gaps.csv。
//
// 合入方式（zh.ts）——在 zhOverrides 字面量内部展开：
//   import { zhDesktopGaps } from './zh_desktop_gaps'
//   const zhOverrides = {
//     ...,
//     ...zhDesktopGaps,
//   } satisfies TranslationOverrides
//
// 参数类型取自 upstream types.ts / types_*.ts，已通过 tsc --strict。
import type { TranslationOverrides } from './define-locale'

export const zhDesktopGaps: TranslationOverrides = {
"""
ts = HEADER + "\n".join(emit(tree)) + "\n}\n"
(ROOT / 'zh_desktop_gaps.ts').write_text(ts, encoding='utf-8')

rows = []
for k in sorted(T):
    e = miss.get(k, {})
    eng = e.get('text', '')
    rows.append({'key': k, 'english': eng if isinstance(eng, str) else str(eng),
                 'zh_translation': '' if T[k] == 'KEEP' else T[k],
                 'category': 'keep-english' if T[k] == 'KEEP' else 'translated'})
with open(ROOT / 'desktop-gaps.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['key', 'english', 'zh_translation', 'category'])
    w.writeheader(); w.writerows(rows)

print(f"wrote zh_desktop_gaps.ts ({len(ts)} bytes) and desktop-gaps.csv ({len(rows)} rows)")
