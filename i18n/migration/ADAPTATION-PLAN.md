# 适配策略（ADAPTATION-PLAN）—— Hermes 0.21.5 → 0.22.0

> 阶段 D 产物。合并 B（旧版改动清单）、C（键命运）、C2（上游覆盖度）、C2b（未汉化缺口）四份实测结果。
> 全部数字经主 Agent 独立复算或抽查复核（见文末「复核记录」）。

## 0. 一句话结论

**这次迁移的主体工作不是"翻译"，而是"给旧补丁做减法"。**
我们旧版 905 个汉化键里 **809 个（89.4%）上游 0.22.0 已自行汉化**，13 个源补丁上游已自行实现应**撤除**；
真正需要人工处理的只有 **48 条重命名**、**8 条真缺口**、**约 8 处上游未覆盖的补丁**。

## 1. 动作分类总表

| 动作 | 对象 | 数量 | 依据 |
|---|---|---|---|
| **RETIRE（撤除）** | 上游已自行 i18n 的源补丁 | **13** 处（跨 4 bundle） | upstream-coverage.md |
| **RETIRE（撤除）** | 全语言 parity 填充补丁（15 locale） | 15 文件 | upstream 自带 3433 键 parity |
| **RETIRE（撤除）** | 因键名变更而失效的测试补丁 | ~8 | upstream-coverage.md |
| **KEEP（保留）** | 上游未覆盖的补丁 | ~8 | upstream-coverage.md |
| **RENAMED（重新挂钩）** | 旧→新键名映射 | **48** 条 | key-fate.csv |
| **NEW-TRANSLATE（新译）** | 真·未汉化缺口 | **8** 条（主 4 + TUI 4） | translation-gaps.md |
| **MOVE（照旧搬运）** | 非汉化功能补丁 | 5 bundle | legacy-changes.md |
| **REGROUP（先归组）** | `_unassigned` 未登记 bundle | 26 文件 | legacy-changes.md §5 |

## 2. 逐 bundle 处置表

| bundle | 文件数 | 处置 | 理由 |
|---|---|---|---|
| `locale-i18n-zh` | 28 | **部分撤除 + 保留工具脚本** | tips/cli_info/background_review 上游已重写（撤）；3 个生成脚本上游未提供（保留） |
| `gateway-i18n-zh` | 11 | **撤大部分，保留 2 处** | exec_approval / run / run_busy 上游已实现（撤）；`agent/onboarding.py`、`chat_completion_wait_notice.py` 上游**仍是英文**（留，但保留我们的键名） |
| `_unassigned` | 26 | **先归组，再逐文件判** | 未登记进清单，含网关 slash/whoami/平台 + 前端 `sg` 注册 |
| `feishu-adapter-local` | 1 | **拆开处理** | i18n 部分随上游；2 处非汉化修复（user_id 允许名单、99992402 线程路由）**必须保留且需重新适配** |
| `main-session-notifier` | 6 | **保留功能** | 主会话提醒路由是功能，非汉化；附带 `gateway.turn.*` 走 i18n 处随上游 |
| `full-trust-delegation` | 11 | **照旧搬运** | 非汉化 |
| `heartbeat-terminal-stamp` | 2 | **照旧搬运** | 非汉化 |
| `camofox-tab-recreate` | 2 | **照旧搬运** | 非汉化 |
| `local-relay-fastmode` | 1 | **照旧搬运** | 非汉化 |
| `doctor-vendor-slug-declared-models` | 1 | **照旧搬运** | 非汉化 |

## 3. 必须保留的非汉化修复（易被汉化迁移误删）

| 位置 | 内容 | 处置 |
|---|---|---|
| `gateway/run.py` `build_resume_recovery_note` | **行为改动**：空恢复一律续跑 | 保留，勿被上游覆盖 |
| `feishu-adapter-local` | 允许名单 user_id + 99992402 线程路由重建 | 保留并重新适配到 0.22.0 |
| 契约串 | `CRON_RESPONSE_PREFIX`、`memory` 分类 label | **刻意保持英文**（外部消费者解析），不得汉化 |
| `sg.yaml` | 本地新增 locale（内容=zh 副本） | 上游若不认识 `sg`，需保留 alias/config 改动 |

## 4. 译文取舍策略（用户已定）

**以上游 `zh.yaml` 为基底，仅在我们旧译文明显更贴切处替换。** 具体：
1. 先取上游 0.22.0 的 `zh.yaml` / `zh.tui.yaml` / desktop `zh*.ts` 原样作基底；
2. 对 48 条 RENAMED：把我们的旧译文挂钩到新键名，与上游译文比对，择优；
3. 对 8 条真缺口：新译；
4. 其余 77 + 25 条"本就不该翻译"项：**保持英文**。

## 5. 待用户/上游确认项

1. `{label} by {user}` 三条（platform.discord/telegram）—— 口径敏感，可能属"不该翻译"。
2. `arrayBuffers` / `rss` —— 调试字段名，是否汉化取决于产品判断。
3. `setup_image_caption` —— Telegram 后台菜单路径，翻成中文可能反与实际界面不符。
4. `token` 单复数 —— 可能是有意保留的英文单位标签。

## 6. 复核记录（主 Agent 亲自复算）

| 数字 | 来源 | 复核方式 | 结果 |
|---|---|---|---|
| 上游 zh 无 CJK 候选 = 81 | 子会话 C2b | 独立脚本复算（Unicode 区间） | **82**（差 1，因我含全角区块）；逐条查明：25 条含全角中文标点、实为中文，**结论不变** |
| 主 catalog 真缺口 = 4 | 子会话 C2b | 抽查翻译口径 | 一致 |
| 旧键 809 MOVED-TO-UPSTREAM | 子会话 C | 亲自修好中断脚本并复跑 | 确认 |
| 可撤除补丁 = 13 | 子会话 C2 | 抽读 upstream-coverage.md 原文 | 确认（含清晰证据链） |
