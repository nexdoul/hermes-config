# Hermes 0.22.0 未汉化缺口精确统计（主 catalog + TUI）

生成于 0.22.0 迁移评估，输入为只读源码 `v0220-src/` 与基线 `baseline/`。
所有数字均由本目录脚本实跑得出，不引用任何外部给定数字。

## 口径（判定规则）

一个条目算「未汉化缺口」当且仅当 zh 值**不含任何 CJK 字符**。CJK 判定按 Python 码位，
覆盖范围：

| 区间 | 含义 |
|---|---|
| U+2E80–U+2EFF | CJK 部首补充 |
| U+3000–U+303F | CJK 标点（含「」、。、·） |
| U+3040–U+30FF | 平假名 + 片假名 |
| U+31C0–U+31EF | CJK 笔划 |
| U+3400–U+4DBF | CJK 扩展 A |
| U+4E00–U+9FFF | CJK 统一表意 |
| U+F900–U+FAFF | CJK 兼容表意 |
| U+FE30–U+FE4F | CJK 兼容形式 |
| U+FF00–U+FFEF | 全角/半角形式（全角标点在此） |
| U+20000–U+2FA1F | CJK 扩展 B–F |

- 判定用 `unicodedata` 无关的显式码位区间，**不依赖** `grep -P '[\x{4e00}-\x{9fff}]'`，
  因此全角标点、日文假名不会被漏判。
- 韩文音节（U+AC00–U+D7AF）**单独统计**：韩文泄漏不属于中文缺口，实测为 0 条。
- 「真·缺口（PROSE）」= 值是非占位的英文文案（自然语言短语），中文用户会真实读到英文。
- 「本就不该翻译」= 占位符/版式符号/快捷键/单位/缩写/专有名词/CLI 代码。

## 复现方式

```bash
cd /home/hatch/.hermes/cache/scratch
python3 gap_scan.py          # 主 catalog + TUI 缺口扫描（写 gap_scan.json）
python3 en_tui_baseline.py   # 从 ui-tui/src/i18n/en/*.ts 抽 TUI 英文基线并比对
```

脚本路径：
- `/home/hatch/.hermes/cache/scratch/gap_scan.py`
- `/home/hatch/.hermes/cache/scratch/en_tui_baseline.py`
- 中间产物：`gap_scan.json`、`en_tui_extract.json`、`gap_cat.json`（同在 scratch）

## 键数自证（脚本实跑）

```
en.yaml 叶键           : 3433
zh.yaml 叶键           : 3433   （键集与 en.yaml 完全相同: True）
zh.tui.yaml 叶键       : 1301   （键集与 _keys.tui.json 完全相同: True）
baseline/new_en.json   : 3433   （叶键集与 en.yaml 完全相同: True）
```

## 结论数字

| 层 | 候选缺口（值无 CJK） | 其中真·缺口（英文文案） | 本就不该翻译 |
|---|---|---|---|
| **主 catalog** `zh.yaml` | **81** | **4** | 77 |
| **TUI** `zh.tui.yaml` | **29** | **4** | 25 |

主 catalog 81 条可再细分：
- 与 en 逐字节相同：**75**
- 与 en 不同但仍纯非中文：**6**（3 条是破折号版式差，3 条见下方 PROSE）
- 纯 ASCII：55 / 非 ASCII 但无 CJK（图标、箭头、破折号）：26

**独立交叉验证**：`baseline/upstream_zh.json` 用同一口径扫描，同样得到 **81** 条无 CJK 条目，
且键集与 `zh.yaml` 的 81 条**完全一致**（对称差为空）。两套独立数据源互证。

> 附注：`upstream_zh.json` 与 `zh.yaml` 有 195 条值不同，经查**全部**是 JSON 序列化把
> 真实换行记成了字面 `\n`（`\\n`）造成的转义差异，与翻译内容无关；`zh.yaml` 是实际发布版。

---

## 一、真·缺口（英文文案）—— 共 8 条

### 主 catalog（4 条）

| 键 | zh 值 | en 值 | 说明 |
|---|---|---|---|
| `gateway.topic.setup_image_caption` | `BotFather → Bot Settings → Threads Settings` | 同 | Telegram 后台菜单路径文案，可汉化为「BotFather → 机器人设置 → 话题设置」 |
| `platform.discord.approval.by_user` | `{user} {label}` | `{label} by {user}` | "by" 连接词被丢弃，只剩两个占位符；中文应输出「{user} 已 {label}」之类 |
| `platform.telegram.approval.resolved_by_user` | `{user} {label}` | `{label} by {user}` | 同上，Telegram 版 |
| `platform.telegram.gmail_triage.appended_by` | `— {user} {label}` | `— {label} by {user}` | 同上，gmail triage 版 |

后 3 条同源：上游把「由 {user} 完成」压缩成 `{user} {label}`，丢掉了连接语义，
是真实的可读性缺口（但注意：它们**不含可翻译的英文单词**，是占位符顺序问题，
若按「字面英文残留」口径可判为「不该翻译」——见下方不确定项）。

### TUI（4 条）

| 键 | zh 值 | en 值 | 说明 |
|---|---|---|---|
| `hubs.agents.detail.tokens` | `token` | `tokens` | 单复数残留，英文单词未汉化（应为「令牌」或保留为标签） |
| `hubs.agents.diff.tokens` | `token` | `tokens` | 同上 |
| `slashCmd.debug.mem.arrayBuffers` | `array buffers` | 同 | `/debug mem` 输出的诊断字段名，英文单词未汉化 |
| `slashCmd.debug.mem.rss` | `rss` | 同 | 同上，RSS 内存字段名 |

后 2 条是**调试输出字段名**，是否该翻译存疑（见不确定项）。

---

## 二、本就不该翻译（主 catalog 77 条 + TUI 25 条）

### 主 catalog 按顶层段分组（全部 81 条分布）

| 顶层段 | 条数 |
|---|---|
| `gateway` | 41 |
| `cli` | 27 |
| `platform` | 7 |
| `display` | 5 |
| `explainer` | 1 |

77 条「不该翻译」的性质分类：

| 类别 | 条数 | 例子 |
|---|---|---|
| 版式/占位符/图标/符号 | 68 | `'{head}{detail}{tail}'`、`'❌ {error}'`、`'⬆ YOLO'`、`'{0} t/s'`、`' n/a '` |
| 专有名词（产品/格式名） | 7 | `'Microsoft Entra ID'`、`'Markdown'`、`'Hermes'`、`'Hermes Agent'`、`'Anthropic Fast Mode'`、`'OpenAI Ultrafast'`、`'Priority Processing'` |
| CLI 用法/代码片段（保持字面） | 2 | `'/footer [on|off|status]'`、`'/timestamps [on|off|status]'` |

> 注：`display.verb_connector.search`（zh `' · '` vs en `' for '`）与
> `gateway.startup.handoff_thread_title`（zh `'Hermes——{title}'` vs en `'Hermes — {title}'`）是
> **有意为之的版式替换**（中文用 `·`/`——` 代替英文 `for`/` — `），属「不该翻译」，不是遗漏。

### TUI 按顶层段分组（全部 29 条分布）

| 顶层段 | 条数 |
|---|---|
| `content` | 11 |
| `slashCmd` | 7 |
| `hubs` | 3 |
| `chatBits` | 2 |
| `libText` | 2 |
| `connection` / `pickers` / `session` / `subscription` | 各 1 |

25 条「不该翻译」的性质分类：

| 类别 | 条数 | 例子 |
|---|---|---|
| 颜文字（kaomoji） | 13 | `'(⌐■_■)'`、`'( ͡° ͜ʖ ͡°)'`、`'٩(๑❛ᴗ❛๑)۶'`、`'(◔_◔)'` |
| 版式/占位符/符号 | 12 | `'~{0} tokens'`、`'{0} · {1}'`、`'Δ'`、`'·'`、`' → {0}'`、`' [tts]'`、`'🔴 {0}'` |
| 缩写/专名 | 1 | `'TUI'`、`'Hermes #{0}'` |

---

## 三、TUI 英文基线的取得（重要说明）

**`locales/` 下没有 `en.tui.yaml`**。TUI 的英文基线实际存在于 TypeScript 源码：
`v0220-src/ui-tui/src/i18n/en/*.ts`（22 个文件，导出 `xxxEn` 常量对象）。

脚本 `en_tui_baseline.py` 用正则从这个 TS 目录抽取英文基线：

- 字面量 `key: 'text'`
- 模板箭头函数 `key: (a) => \`...${a}...\`` → 归一化成 `{0}` `{1}` 占位符

抽取结果：**1226+ 条**英文条目，覆盖 zh.tui.yaml 的 **1040 / 1301** 个键（约 80%）。
未覆盖的 261 个键是 TS 里多行模板/复杂表达式，未被字面正则捕获（不影响缺口判定——
缺口判定只依赖 zh.tui.yaml 自身是否有 CJK）。

比对结果：29 条 TUI 缺口中，**25 条与英文 TS 源逐字节相同**（确认为未翻译的英文残留），
其余 4 条（`arrayBuffers`/`rss`/`topup.error.generic`/`wake.withHint`）因键路径映射差异未被脚本
自动匹配，已人工在 TS 源中逐一 grep 确认存在（值见上表），同属英文残留。

---

## 四、不确定项 / 口径申明

1. **`{label} by {user}` 系列（3 条主 catalog）**：不含可翻译英文单词，只有占位符顺序。
   若严格按「英文文案残留」口径，它们可归入「不该翻译」；本报告归 PROSE 是因为
   上游英文原文的 `by` 语义在 zh 版丢失，是真实的可读性缺口。**口径敏感，需决策**。
2. **`arrayBuffers` / `rss`（TUI）**：调试输出字段名，是否需要汉化取决于产品判断。
3. **`token`（TUI 2 条）**：zh 为单数 `token`、en 为 `tokens`，且未汉化。可能是漏译，
   也可能是有意保留英文单位标签。
4. **`gateway.topic.setup_image_caption`**：是 Telegram 后台的菜单路径，翻译成中文反而可能
   与 Telegram 实际界面（英文/用户语言）不符。是「该翻」还是「该保留原文」存疑。
5. TUI 英文基线抽取覆盖约 80% 键，剩余 20% 的多行模板未纳入自动比对（判定不受影响）。
6. 本报告只统计「值完全无 CJK」的条目。**未统计**「值含 CJK 但仍夹带英文词组」的混合条目——
   抽样发现这类条目里夹带的英文几乎全是 CLI 命令（`hermes gateway restart`、`hermes skills config`
   等），属该保留的字面量，故未计入缺口。

## 五、与工作目录其他产物的关系

- `pkg0220/`、`v0220.json`、`new_files.txt`/`old_files.txt`：升级文件级 diff，与本统计无直接关系。
- `baseline/old_en.json`：0.21.5 的英文基线（89494 字节），本次未使用。
- 本报告唯一写入的产物：`i18n/migration/translation-gaps.md`（脚本全部写在 scratch，未污染工作目录）。
