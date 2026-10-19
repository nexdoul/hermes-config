# Hermes Desktop / 主 catalog 汉化 — v0.22.2 交付

对应上游：`hermes-agent` **v0.22.2**（commit `d923a5e`）。

## 文件

| 文件 | 层 | 说明 |
|---|---|---|
| `zh.yaml` | 主 catalog（gateway / CLI） | 3433 键，与上游 `en.yaml` 键集**完全一致** |
| `zh.tui.yaml` | TUI（Ink） | 1301 键，与上游 `zh.tui.yaml` **逐字节相同** |
| `zh_desktop_gaps.ts` | Desktop（Electron） | 614 条 overlay，补齐上游 `zh.ts` 的缺口 |
| `desktop-gaps.csv` | 参考 | 614 条 key→中文 对照表 |
| `scripts/` | 工具 | `desktop_gap_extract.py`、`verify_runtime.cjs` |

## 与 0.22.0 交付物的关系

**0.22.0 的汉化产物可原样用于 0.22.2。** 实测：

- `locales/en.yaml`、`zh.yaml`、`zh.tui.yaml`、`_keys.tui.json` —— 两版 **md5 全同**
- desktop `en.ts` / `zh.ts` / `types.ts` / `define-locale.ts` —— 两版 **md5 全同**
- 唯一上游新增：`keepAwakeOffer.{title,message,action}`（`zh_notices.ts` **上游已自带中文**）

本版在此基础上补了 9 条 desktop 键（`connectorsPage.add.*` 8 条技术标识 + `editJson`，
以及 `connectorsPage.tools.moreHints` 函数）。

## 验证结果（2026-10-19 实测）

| 层 | 方法 | 结果 |
|---|---|---|
| 主 catalog | 0.22.2 真实 `agent/i18n.py` 加载 + 叶子展开 + 占位符比对 | 3433/3433，缺 0 多 0，占位符不一致 0 |
| TUI | 与上游 `zh.tui.yaml` 叶子集比对 | 1301/1301，逐键相同 |
| Desktop | `tsc` 编译 → Node 加载真实 `en.ts`/`zh.ts`/overlay + 真实 `defineFieldCopy` + 真实 `mergeTranslations` | en 4934 / zhOverrides 4657 / overlay 614 → **缺 460，补后 0** |
| 类型 | `tsc --strict` 对真实 `TranslationOverrides` | `zh_desktop_gaps.ts` **0 错误** |

**107 条主 catalog 非中文已逐条核查**：全部是纯格式串、占位符、emoji 或技术标识
（`FAST` / `ON` / `MCP` / `TTS` / `n/a`），**无一条是漏译句子**。

## 部署注意

**升级版本与部署汉化必须是同一个原子动作。**

0.22 做了键命名空间迁移（`approval.action_once` → `gateway.exec_approval.action_once`），
本 `zh.yaml` 对 0.21.5 的在用键覆盖率仅 17/890 —— 单独部署汉化会让 873 键
渲染成裸键名。必须先升级到 0.22.2，再落地 locale 文件。

`zh.yaml` / `zh.tui.yaml` 直接 `cp` 进 runtime 的 `locales/` 即可。
`zh_desktop_gaps.ts` 是**源码级 overlay**，需 `import` 进 `zh.ts` 的 spread 并重建桌面客户端：

```ts
import { zhDesktopGaps } from './zh_desktop_gaps';
export const zhOverrides = { ...zhOverridesBase, ...zhDesktopGaps };
```

缺任一步，运行时会只到 253/614。

## 测法提醒

Desktop 键集**不能用正则或括号计数器从 TS 源码里抠**。模板字面量、多行字符串、
字符串内的引号、函数值、`defineFieldCopy(...)` 包装都会让朴素解析器出错 ——
本仓 0.22.0 交付的 `desktop_gap_extract.py` 就把 `fieldLabels: defineFieldCopy({...})`
当成了叶子，虚报了 149 条缺失。**一律走真编译器 + 真运行时取证。**
