# Hermes 0.22.0 汉化产物

本目录是 **Hermes 0.22.0 的简体中文完整汉化**，可直接落到 runtime 使用。

## 结论摘要

| 层 | 文件 | 状态 |
|---|---|---|
| gateway / CLI / slash（主 catalog） | `zh.yaml` | ✅ 直接采用上游（3433 键，实测无缺口） |
| TUI | `zh.tui.yaml` | ✅ 直接采用上游（1301 键） |
| desktop（Electron UI） | `zh_desktop_gaps.ts` + `desktop-gaps.csv` | ✅ 上游覆盖 89.4%，补 614 条缺口（605 译 + 9 保留英文），补后 **99.8%** |

## 为什么主 catalog 与 TUI 直接用上游

实测（见 `TRANSLATION-REVIEW.md`）：上游 0.22.0 **自带完整简体中文**。
我们旧版（0.21.5）的 836 条真中文里：

- **303 条与上游逐字节相同**
- **13 条上游是超集**（我们的措辞 + 新版补充内容）
- 其余为上游在 0.21.5 就已有、未变动的译文

按用户确定的策略「**以上游为基底，仅在我们旧译文明显更贴切处替换**」，逐条复核后
**没有一条需要替换** —— 上游质量不低于我们，且是超集。故 `zh.yaml` / `zh.tui.yaml` 原样采用。

## 主 catalog / TUI 缺口复核

子会话曾机械统计出「主 4 条 + TUI 4 条」英文残留，逐条人工复核后**判定均不应翻译**：

| 键 | 实际值 | 判定 |
|---|---|---|
| `gateway.topic.setup_image_caption` | `BotFather → Bot Settings → Threads Settings` | Telegram 后台菜单路径 |
| `platform.discord.approval.by_user` | `{user} {label}` | 纯占位符 |
| `platform.telegram.approval.resolved_by_user` | `{user} {label}` | 纯占位符 |
| `platform.telegram.gmail_triage.appended_by` | `— {user} {label}` | 纯占位符 |
| `hubs.agents.detail.tokens` / `diff.tokens` | `token` | 技术单位标签 |
| `slashCmd.debug.mem.arrayBuffers` / `rss` | `array buffers` / `rss` | 调试面板字段名 |

## desktop 层（Electron UI）

上游 `apps/desktop/src/i18n/zh.ts` 的 `zhOverrides` 只覆盖 4547/5084 个叶子键（89.4%），
**614 个键缺中文**，运行时回退英文。本目录补齐其中 605 条（另有 9 条判定应保持英文）。

注：早期统计口径为 194 条，是**用正则扫描得到的偏小值** —— 正则会漏掉 import
引入的子模块与函数值条目。最终采用解析 TypeScript 结构本身的统计，缺口为 **614**。
详见 `DESKTOP-PATCH.md`。

## 验收（已跑通）

| 检查 | 结果 |
|---|---|
| 主 catalog 键 parity（zh vs en） | ✅ 3433 / 3433 |
| TUI 键 parity（vs `_keys.tui.json`） | ✅ 1301 / 1301 |
| 占位符 parity | ✅ 无差异 |
| 重复键 | ✅ 0（含按完整路径判定） |
| 主 catalog / TUI 真实渲染（跑上游 i18n 加载器） | ✅ 5 / 5 输出中文 |
| desktop overlay `tsc --strict` | ✅ exit 0 |
| desktop 运行时逐键取值（编译为 JS 后 node 加载） | ✅ 605 / 605 命中，硬失败 **0** |

desktop 的函数值条目不能只做字符串检查 —— 必须实际传参调用。实测 87 个函数条目
全部返回中文，参数类型取自上游 `types.ts`。

## 用法

```bash
HERMES_RT=$HERMES_HOME/npm/node_modules/hermes-agent/runtime/hermes-agent
cp zh.yaml      "$HERMES_RT/locales/zh.yaml"
cp zh.tui.yaml  "$HERMES_RT/locales/zh.tui.yaml"
```

desktop 层按 `DESKTOP-PATCH.md` 把 `zh_desktop_gaps.ts` 放进
`apps/desktop/src/i18n/`，并在 `zh.ts` 的 `zhOverrides` 字面量内展开：

```ts
import { zhDesktopGaps } from './zh_desktop_gaps'
// 在 `} satisfies TranslationOverrides` 之前加：
  ...zhDesktopGaps,
```

## 文件

| 文件 | 说明 |
|---|---|
| `zh.yaml` | 主 catalog 简体中文（上游 0.22.0 原样，3433 键） |
| `zh.tui.yaml` | TUI catalog 简体中文（上游 0.22.0 原样，1301 键） |
| `zh_desktop_gaps.ts` | desktop 层补译 overlay（605 条译文，可编译） |
| `desktop-gaps.csv` | desktop 层 614 条缺口明细（含英文原值、译文、分类） |
| `TRANSLATION-REVIEW.md` | 主/TUI 译文取舍逐条复核记录 |
| `DESKTOP-PATCH.md` | desktop 补译说明、合入方式、验收证据 |
| `scripts/` | 可复现脚本：缺口提取、overlay 生成、运行时校验 |
