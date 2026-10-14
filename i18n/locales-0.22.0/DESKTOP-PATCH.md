# desktop-gaps.csv / zh_desktop_gaps.ts — Hermes 0.22.0 desktop 层补译

## 这是什么

上游 0.22.0 的 desktop 层（Electron UI）自带简体中文 overlay（`apps/desktop/src/i18n/zh.ts`
的 `zhOverrides`），但**未覆盖全部键**。本目录补齐缺口。

| 指标 | 数值 |
|---|---|
| en 基线叶子键总数 | 5084 |
| 上游 zh overlay 已覆盖 | 4547（89.4%） |
| 缺口 | **614** |
| 其中判定需翻译 | **605** |
| 判定保持英文（KEEP） | 9 |
| 补译后覆盖率 | **99.8%** |

覆盖率统计用 `apps/desktop/src/i18n/` 的 TypeScript 结构本身（解析 import 递归 + 展平
嵌套对象），不是正则扫描 —— 正则会漏掉 import 引入的子模块与函数值条目。

## 缺口分布（605 条）

| 顶层组 | 条数 |
|---|---|
| `connectorsPage` | 217 |
| `settings` | 173 |
| `assistant` | 71 |
| `boot` | 31 |
| `skills` | 26 |
| `keybinds` | 17 |
| `appTour` | 15 |
| `freeTier` | 14 |
| `notifications` | 8 |
| `cron` | 4 |
| `onboarding` | 4 |
| `sidebar` | 4 |
| `messaging` | 3 |
| `profiles` | 3 |
| `updates` | 3 |
| `errors` | 2 |
| `externalOpenFailed` | 2 |
| `install` | 2 |
| `composer` | 1 |
| `connectors` | 1 |
| `desktop` | 1 |
| `fileMenu` | 1 |
| `preview` | 1 |
| `prompts` | 1 |

## 两个产物

### 1. `desktop-gaps.csv`
614 行，每行一条缺口：

| 列 | 含义 |
|---|---|
| `key` | 点号路径（相对 desktop i18n 根） |
| `english` | 上游英文原值 |
| `zh_translation` | 简体中文译文（`KEEP` 条目留空） |
| `category` | `translated` / `keep-english` |

### 2. `zh_desktop_gaps.ts`
可直接合入的 TypeScript overlay，导出 `zhDesktopGaps`。

**合入方式**（改 `apps/desktop/src/i18n/zh.ts`）：

```ts
import { zhDesktopGaps } from './zh_desktop_gaps'
// 在 zhOverrides 对象字面量末尾（`} satisfies TranslationOverrides` 之前）加一行：
  ...zhDesktopGaps,
```

注意 `zh.ts` 的结构是 `const zhOverrides = { ... } satisfies TranslationOverrides`，
所以要在**字面量内部**展开，不能改成 `{...base, ...gaps}` —— 文件里
`export const zh = defineLocale(zhOverrides)` 直接引用同名变量。

## 已验证

| 检查 | 方法 | 结果 |
|---|---|---|
| TypeScript 类型 | `tsc --strict` 编译（含真实 `TranslationOverrides` 约束） | ✅ exit 0 |
| 参数类型 | 87 个函数值条目的参数类型取自 `types.ts` / `types_*.ts` | ✅ 全部显式标注 |
| 运行时解析 | 编译为 JS 后用 node 加载 `zh`，逐键取值 | ✅ 605/605 命中 |
| 中文落地 | 对字符串值 grep CJK；对函数值传参调用后 grep CJK | ✅ 518 + 86 |
| 残留英文散文 | 605 条中非 CJK 且非格式串的条目 | ✅ **0 条** |
| 硬失败 | 键缺失 / 类型不符 / 调用抛错 | ✅ **0** |

函数值条目不能只做字符串检查 —— 必须实际调用。参数名与类型来自上游
`types.ts`（如 `mainAppliedMessage: (model: string) => string`），
`ErrorCardCopy` 族的参数为 `provider: string`。

## KEEP 的 9 条（有意保留英文）

| 键 | 英文 | 理由 |
|---|---|---|
| `connectorsPage.add.authOauth` | `OAuth` | 协议名 |
| `connectorsPage.add.typeHttp` | `Streamable HTTP` | 协议名 |
| `connectorsPage.add.typeStdio` | `STDIO` | 协议名 |
| `connectorsPage.add.url` | `URL` | 技术标识 |
| `connectorsPage.add.keyPlaceholder` | `KEY` | 表单占位符 |
| `connectorsPage.add.valuePlaceholder` | `value` | 表单占位符 |
| `connectorsPage.add.pastePlaceholder` | `npx -y @modelcontextprotocol/server-filesystem /path/to/dir` | 可复制命令，翻译会坏事 |
| `connectorsPage.add.editJson` | `Edit mcp.json` | 指向真实文件名 |
| `connectorsPage.tools.moreHints` | `+${count}` | 纯格式串 |

## 复现

```bash
# 1. 从上游源码提取缺口（需 v0.22.0 源码）
python3 scripts/desktop_gap_extract.py    # -> dgap_missing_full.json（含每个键的 en 原值与类型）

# 2. 生成 TS overlay + CSV
python3 scripts/build_desktop_overlay.py

# 3. 校验（需 typescript）
npx tsc --strict zh_desktop_gaps.ts       # 或用本目录 harness
```
