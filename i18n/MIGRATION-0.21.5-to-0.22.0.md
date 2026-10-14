# Hermes 汉化迁移：0.21.5 → 0.22.0

> 全盘扫描与适配分析报告。
> 基线：`f97608f`（v2026.9.24 / npm 0.21.5）→ `e06df9c`（v0.22.0 / npm 0.22.0）
> 方法：所有数字均来自实测脚本，可复跑。复核记录见文末。

---

## 0. 执行摘要

主节点 agent 反馈"汉化文本对不上，新版本需要单独适配"。**本次扫描确认了原因，并发现实际工作量远小于预期。**

**根因**：我们旧版的汉化是按**旧键名**（如 `status.free_tier`、`platform.tier_admin`、`review.*`、`cron.manage_hint`）
注入 locale 目录的。0.22.0 把 locale 目录从 **965 键扩到 3433 键**，并大规模**重命名/重分段**
（`review.*` → `display.review.*`、`platform.*` → `gateway.whoami.*`、`gateway.session.retry_*` → `gateway.retry.*`）。
旧译文因此落到了没人再读的键上 —— 表现为"对不上"。

**关键发现：上游 0.22.0 已自带完整简体中文。**

| 层 | 键数 | 上游已翻译 | 真·未汉化缺口 |
|---|---|---|---|
| `locales/zh.yaml`（gateway/CLI/slash） | 3433 | 3433 | **4** |
| `locales/zh.tui.yaml`（TUI） | 1301 | 1301 | **4** |
| `apps/desktop/src/i18n/zh*.ts`（Electron UI） | 28 文件 | 已翻译 | 0（待抽验） |

**我们旧版 905 个汉化键的命运**：

| 分类 | 数量 | 占比 |
|---|---|---|
| **上游已自行汉化**（MOVED-TO-UPSTREAM） | **809** | **89.4%** |
| GONE（上游删功能） | 48 | 5.3% |
| RENAMED（换键名，需重新挂钩） | 48 | 5.3% |

→ **89.4% 的既有汉化工作上游已经替我们做了。** 真正需要人工的：48 条重命名 + 8 条新译。

---

## 1. 规模变化（实测）

| 项 | 0.21.5 | 0.22.0 | 变化 |
|---|---|---|---|
| tracked 文件 | 15075 | 18556 | +3831 / −350 |
| `locales/en.yaml` 叶子键 | 965 | 3433 | ×3.6 |
| TUI catalog（`*.tui.yaml`） | 无 | 17 语言 | **全新一层** |
| desktop catalog（`_keys.desktop.json`） | 无 | 有 | **全新一层** |
| i18n 模块 | — | `agent/i18n_languages.py`、`agent/i18n_layers.py` | 架构重构 |
| 本机 runtime 补丁 bundle | 10 个 / 89 patch | — | — |

---

## 2. 我们在旧版改了什么（Deliverable ①）

**10 个 bundle 目录，89 个 patch 文件**，全部 `TARGET_COMMIT=f97608f…`（0.21.5）。

| # | bundle | 文件 | 汉化相关 | 性质 |
|---|---|---|---|---|
| 1 | `locale-i18n-zh` | 28 | ✅ | locale 键补丁（17 yaml）+ 硬编码改走 i18n + 3 个校验脚本 |
| 2 | `gateway-i18n-zh` | 11 | ✅ | 网关/执行审批中文化；含恢复续跑策略 |
| 3 | `feishu-adapter-local` | 1 | ⚠️ 部分 | 飞书卡片 i18n + **2 处非汉化修复** |
| 4 | `_unassigned` | 26 | ✅ 主体 | **未归类**；slash/whoami/平台 + 前端 `sg` |
| 5 | `main-session-notifier` | 6 | ⚠️ 部分 | 主会话提醒路由（功能）+ 顺带 i18n |
| 6 | `full-trust-delegation` | 11 | ❌ | 全托管"一次做完" |
| 7 | `heartbeat-terminal-stamp` | 2 | ❌ | 心跳终态标记 |
| 8 | `camofox-tab-recreate` | 2 | ❌ | Camofox tab 410→404 重建 |
| 9 | `local-relay-fastmode` | 1 | ❌ | 中继 fast-mode |
| 10 | `doctor-vendor-slug-declared-models` | 1 | ❌ | doctor vendor-slug 修复 |

**汉化改动量**：en.yaml 新增 906 键行（去重 848）；zh.yaml 真实中文 826 行；新增 `sg.yaml` 965 键；
代码侧 `t(...)` 调用点 **134 处**；前端 i18n 12 文件；新增汉化测试 10 个。

完整逐文件明细见 `migration/legacy-changes.md`。

---

## 3. 上游 0.22.0 覆盖度审计（Deliverable ③）

**上游已自行实现、我们的补丁应「撤除而非重打」的 13 处源改动**：

| bundle | 上游已覆盖 | 证据要点 |
|---|---|---|
| `gateway-i18n-zh` | 5 处 | exec_approval 变成 `ea_*()` 访问器；`run.py`/`run_busy.py` 已用 `t("gateway.errors.*")`、`t("gateway.busy.*")` |
| `locale-i18n-zh` | 3 处 | `tips.py` 重写为 `tips.tNNN` 方案；`background_review` 改用 `display.review.*`；`yuanbao.py` 采用了我们的常量方案 |
| `_unassigned` | 5 处 + web/desktop | 前端/桌面 i18n 已全部内置 |
| 全 15 locale parity 补丁 | 15 文件 | 上游自带 3433 键 parity，无需我们填充 |

**必须保留（上游未覆盖）**：
- `agent/onboarding.py` 的 4 个 busy hint dict —— 上游**仍是英文硬编码**
- `agent/chat_completion_wait_notice.py` 的 `_PHASE_TEXT` —— 上游**仍是英文**
- `cron/scheduler_delivery.py` 的 cron 包装头 —— 上游**仍是 f-string**
- 3 个 catalog 生成脚本（`gen_tips_catalog.py` 等）—— 上游未提供
- `feishu-adapter-local` 的 2 处非汉化修复

详表见 `migration/upstream-coverage.md`。

---

## 4. 键命运与缺口

### 4.1 旧键命运（905 键）

见 `migration/key-fate-summary.md` 与机器可读 `migration/key-fate.csv`。

**48 条 RENAMED 的主要搬迁模式**：

| 旧命名空间 | 新命名空间 |
|---|---|
| `review.*` | `display.review.*` |
| `platform.tier_*` | `gateway.whoami.tier_*` |
| `gateway.session.retry_*` | `gateway.retry.*` |
| `gateway.busy_ack.*` | `gateway.busy.*` |
| `provider.*` | `gateway.errors.*` |
| `cron_interrupt.*` | `gateway.shutdown.cron_interrupted` |

### 4.2 真·未汉化缺口（8 条）

主 catalog 无 CJK 候选 82 条 → 其中 **77 条本就不该翻译**（68 版式/占位符/图标 + 7 专有名词 + 2 CLI 用法），
只有 **4 条是真英文文案**：

| 键 | 问题 |
|---|---|
| `gateway.topic.setup_image_caption` | BotFather 菜单路径 |
| `platform.discord.approval.by_user` | `{label} by {user}` 连接词丢失 |
| `platform.telegram.approval.resolved_by_user` | 同上 |
| `platform.telegram.gmail_triage.appended_by` | 同上 |

TUI 层 29 条候选 → **25 条不该翻译**（13 颜文字 + 12 版式），**4 条真缺口**：
`hubs.agents.detail.tokens`、`hubs.agents.diff.tokens`、`slashCmd.debug.mem.arrayBuffers`、`slashCmd.debug.mem.rss`。

**另注**：`zh.yaml` 中还有 25 条值含全角中文标点（`：`、`，`）而无汉字，如 `gateway.busy.ack_detail_joiner = '，'`
—— 这些**是中文**（标点承载语义），不应计入缺口。

详见 `migration/translation-gaps.md`。

---

## 5. 适配策略（Phase D 定稿）

| 动作 | 对象 | 数量 |
|---|---|---|
| **撤除** | 上游已自行 i18n 的源补丁 | 13 |
| **撤除** | 全语言 parity 填充补丁 | 15 文件 |
| **撤除** | 因键名变更失效的测试补丁 | ~8 |
| **保留** | 上游未覆盖的补丁 | ~8 |
| **重新挂钩** | 旧→新键名 | 48 条 |
| **新译** | 真缺口 | 8 条 |
| **照旧搬运** | 非汉化功能补丁 | 5 bundle |
| **先归组** | `_unassigned` | 26 文件 |

**译文取舍（用户已定）**：以上游 `zh.yaml` 为基底，仅在我们旧译文明显更贴切处替换。

**必须保留的非汉化改动**（易被误删）：
- `gateway/run.py` `build_resume_recovery_note` 的行为改动（空恢复一律续跑）
- `feishu-adapter-local`：允许名单 user_id、99992402 线程路由重建
- 契约串 `CRON_RESPONSE_PREFIX`、`memory` 分类 label —— **刻意保持英文**，外部消费者解析

---

## 6. 环境与安全边界

- 迁移全程在隔离目录 `/home/hatch/workspace/hermes-0220-migration/`，**线上 0.21.5 未受影响**。
- 未重启任何主机/容器/网关；未改动守护链与既有 bundle 的 `TARGET_COMMIT`。
- 报告内不含任何 token/密钥。

---

## 7. 复核记录（主 Agent 亲自复算）

| 数字 | 复核方式 | 结果 |
|---|---|---|
| zh.yaml 无 CJK 候选 81 | 独立脚本复算 | **82**（我含全角区块，多 1 条）；查明为全角标点条目，**结论不变** |
| 上游已汉化 809/905 | 修好中断脚本后亲自复跑 | 确认 89.4% |
| 可撤除补丁 13 | 抽读证据链 | 确认 |
| 真缺口 4（主） | 抽查翻译口径 | 一致 |

*本报告由主 Agent 整合四份子会话实测产物并独立复核后撰写。*
