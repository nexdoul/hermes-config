# Hermes 0.21.5 → 0.22.0 迁移：旧版本地改动全量盘点（legacy-changes.md）

**生成时间**：2026-10-14
**数据源（全程只读）**：
- `/home/hatch/.hermes/patches/`（10 个 bundle 目录）
- `/home/hatch/.hermes/runtime-local-patches.list`（登记清单，30 行）
- `/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent`（旧版 runtime，未改动）

**基线 commit**：所有 bundle 的 `meta` 中 `TARGET_COMMIT=f97608f178d1ffeca59860195ab7da295f7c8e5f`（10/10 一致）
**快照时间**：`SNAPSHOT_AT=2026-10-13T07:35:3x Z`

---

## 0. 结论速览（总表）

| 指标 | 数值 |
|---|---|
| bundle 目录数 | **10**（9 个已登记 + 1 个 `_unassigned` 未归类） |
| declared 目标文件总数（去重累加） | **89** |
| 实际 `.patch` 文件数 | **89** |
| **汉化相关 bundle** | **5**：`locale-i18n-zh`、`gateway-i18n-zh`、`feishu-adapter-local`（部分）、`_unassigned`（主体）、`main-session-notifier`（部分） |
| **纯运维/非汉化 bundle** | **4**：`heartbeat-terminal-stamp`、`camofox-tab-recreate`、`local-relay-fastmode`、`doctor-vendor-slug-declared-models` + `full-trust-delegation`（功能，非汉化） |
| 新增 locale 键（en.yaml 增量，含重复行） | **906** 行（去重后 848 个不同的键 token） |
| zh.yaml 实际中文译文新增行（含 CJK） | **826** 行 |
| 新增独立 locale 目录 `sg.yaml` | **965** 键 / 1050 行（内容 = zh 的副本，endonym 不同） |
| 代码侧 `t(...)` 调用点（非测试，累加） | **134** 处 |
| 汉化相关改动点合计（含 locale 键 + 代码调用 + 前端） | **约 1200+**（见 §6/§7 明细） |

> **迁移时最重要的判断**：locale 键结构在 17 个 locale 中**强制对齐**，新增键只在 `en.yaml` 与 `zh.yaml`（及本地新增的 `sg.yaml`）有真实译文；其余 15 个 locale 只是**播撒了英文占位值**以保证 key 集合与 en 一致（parity 测试要求）。0.22.0 若改动了键集合，需要重新对齐 17 个文件。

---

## 1. bundle 总览表

| # | bundle 名 | 目标文件数 | 汉化相关 | 改动性质 |
|---|---|---|---|---|
| 1 | `locale-i18n-zh` | 28 | ✅ 是 | locale 键补丁（17 个 yaml）+ 硬编码英文改走 i18n + 新增 3 个校验脚本 |
| 2 | `gateway-i18n-zh` | 11 | ✅ 是 | 网关/执行审批硬编码英文改走 i18n；含恢复接续策略改动 |
| 3 | `feishu-adapter-local` | 1 | ⚠️ 部分 | 飞书卡片按钮/表头走 i18n；另含 2 处非汉化修复（允许名单 user_id、99992402 线程路由重建） |
| 4 | `_unassigned` | 26 | ✅ 是（主体） | 未归类；网关 slash_commands/whoami/platform/关停通知等改 i18n + 前端 i18n 注册 `sg` |
| 5 | `main-session-notifier` | 6 | ⚠️ 部分 | 主会话提醒路由（功能）；顺带把 `gateway.turn.*` 文案改走 i18n |
| 6 | `full-trust-delegation` | 11 | ❌ 非汉化 | 全托管「一次做完」功能；含中文触发词但非 i18n 键 |
| 7 | `heartbeat-terminal-stamp` | 2 | ❌ 非汉化 | 心跳消息追加终态标记 |
| 8 | `camofox-tab-recreate` | 2 | ❌ 非汉化 | Camofox tab 410 按 404 语义重建 |
| 9 | `local-relay-fastmode` | 1 | ❌ 非汉化 | sub2api 中继允许 fast-mode |
| 10 | `doctor-vendor-slug-declared-models` | 1 | ❌ 非汉化 | doctor vendor-slug 误报修复 |
| | **合计** | **89** | | |

---

## 2. 汉化相关 bundle 逐文件明细

### 2.1 `locale-i18n-zh`（28 文件）—— 汉化的主体

**性质**：① 把硬编码英文改成走 `agent.i18n.t()`；② 补充/对齐全语言 locale 键；③ 新增中文本地化工具脚本。

#### 2.1.1 locale 目录（17 个 yaml）

每个 patch 的 hunk 头显示：新增 ~894 键行，且对已有键做**空格对齐/缩进规范化**（`choose_long:     ` → `choose_long: `）。

| 文件 | 新增键行 | 说明 |
|---|---|---|
| `locales/en.yaml` | 906 行（含重复） | **source of truth**，新增顶层段 `cron:`、`tips:`、`review:`、`gateway.busy_approval.exec_*` 等 |
| `locales/zh.yaml` | 826 行含 CJK | **真实中文译文**（唯一全量翻译） |
| `locales/zh-hant.yaml` | 894 行 | 键对齐；繁中译文部分真实 |
| `locales/de/ja/af/ar/es/fr/ga/hu/it/ko/pt/ru/tr/uk.yaml`（14 个） | 各 ~894 行 | **仅补键 + 英文占位值**（保证 parity），非译文 |

**关键新增键（en.yaml，中文见 zh.yaml）**：

- `approval.exec_*`（exec 审批卡共用词，共 ~20 键）：
  `exec_header: Hermes wants to run a command that needs your OK` / `exec_reason_label: Why it was flagged` / `exec_deadline: If you don't answer within {window} it will NOT run.` / `exec_timed_out` / `exec_window_count: '{count} {unit}'` / `exec_window_unit_second|minute|hour`（含复数变体 `exec_window_units_*`）/ `exec_smart_deny_label: Smart DENY` / `exec_smart_deny_tail` / `exec_fallback_once|session|always|deny|join|last_join` / `action_once|session|always|deny`
  > zh 译文示例：`exec_header: 需要你的批准才能运行命令`、`exec_reason_label: 被标记的原因`、`exec_deadline: 如果 {window} 内没有回应，该命令将不会执行。`、`action_once: 允许一次`
- `gateway.busy.*`：`behavior_queue_card/confirm`、`behavior_steer_card/confirm`、`behavior_interrupt_card/confirm`
- `gateway.session.*`：`codex_compact_nothing`、`codex_compact_done`、`codex_compact_failed`、`retry_unsafe`、`retry_failed`
- `gateway.heartbeat.*`：`usage`、`interval_too_small`、`prompt_required`、`set`、`agent_running`、`nothing_to_pause`、`nothing_to_refine`、`reviewing`
- `gateway.skills.*` / `gateway.whoami.*`：`tier_unrestricted`、`tier_admin`、`tier_user`
- `gateway.platform.*`：`usage`、`not_enabled`、`already_paused`、`paused`、`not_in_queue`、`already_retrying`、`resumed`
- `gateway.history_unreadable.notice`、`gateway.draining`、`gateway.goal_cleared`、`gateway.no_active_goal`
- `gateway.context_overflow.*`、`gateway.hygiene.*`、`gateway.provider.*`、`gateway.session_storage.*`、`gateway.turn.*`、`gateway.shutdown_notice.*`、`gateway.cron_interrupt.*`、`gateway.busy_ack.*`、`gateway.common.*`、`gateway.provider_wait.*`、`gateway.onboarding.*`
- 新顶层段 `cron:`：`response_header: "Cronjob Response: {name}"`、`job_id_line`、`manage_hint`、`mirror_prefix`、`bot_chat_name`、`undeliverable`、`undeliverable_profile`
- 新顶层段 `tips:`：`label: '✦ Tip: '` + `tip_000..tip_NNN`（对 `hermes_cli/tips.py` 的 TIPS 列表逐条 id 化）
- 新顶层段 `review:`：`summary_prefix: "💾 Self-improvement review: "`、`skill_verb.*`、`skill_action_line`、`memory_action_line`、`verbose_patch_line`、`verbose_create_line`、`verbose_plain_line`、`memory_op.*`、`memory_op_line`、`fallback_create`

#### 2.1.2 Python 代码（硬编码英文 → `t()`）

| 文件 | 关键改动 |
|---|---|
| `cron/scheduler_delivery.py` | 新增 `CRON_RESPONSE_PREFIX = "Cronjob Response: "` 与 `CRON_RESPONSE_DIVIDER`（注释标明"机器可读契约串，禁止本地化"，被 3 处消费者解析）；`_cron_display_name` 保持英文；`"Bot Chat ({profile})"` → `t("cron.bot_chat_name", profile=...)`；两处 `Hermes could not deliver this result to Bot Chat...` → `t("cron.undeliverable")` / `t("cron.undeliverable_profile", profile=...)`；`_deliver_result` 中 cron 响应头/尾 → `CRON_RESPONSE_PREFIX` + `t("cron.job_id_line")` + `CRON_RESPONSE_DIVIDER` + `t("cron.manage_hint", name=...)` |
| `gateway/platforms/yuanbao.py` | `strip_cron_wrapper` 重写：头部前缀/分隔符视为字节稳定契约；因注释 `(job_id: ...)` 行与页脚已本地化，改为**按结构**定位（头部 2 行、页脚取最后一个空行段落），不再 grep 英文词 |
| `hermes_cli/tips.py` | 新增 `TIP_IDS`（`tip_000..`）、`_TIPS_BY_ID`、`_localized(key, fallback)`、`tip_label()`；`get_random_tip()` / `get_random_composer_placeholder()` 改为按 id 取译文，catalog miss 回退英文原文（新增 `PLACEHOLDER_IDS`） |
| `hermes_cli/cli_info_mixin.py` | `✦ Tip: {_tip}` → `{tip_label()}{_tip}`（走 `t("tips.label")`） |
| `agent/background_review.py` | `_MEMORY_OP_FORMATS` 的 glyph 从字面 emoji 改为动作名（`add/replace/remove`）供 `review.memory_op.*` 取；`_memory_op_line` / `_verbose_skill_line` / `_action_lines` / `_publish_review_summary` 改走 `t("review.*")`；`label`（"Skill"/"Memory"/"User profile"）**刻意保持英文**（被 discord/adapter 解析） |

#### 2.1.3 新增脚本与测试（locale-i18n-zh）

- `scripts/check_locale_dup_keys.py`（新文件）：重复键检查器——pyyaml 静默保留最后一个重复键，此 loader 改为报错。
- `scripts/gen_tips_catalog.py`（新文件）：从 `tips.py` 的 TIPS/COMPOSER_PLACEHOLDERS 生成 `tips:` 段落，键用稳定 id。
- `scripts/sync_locale_section.py`（新文件）：把一个顶层段从 en 复制到其他 catalog 作英文占位（parity 要求）。
- `tests/cron/test_cron_wrapper_i18n.py`、`tests/hermes_cli/test_tips_i18n.py`、`tests/agent/test_review_summary_i18n.py`（新增 i18n 测试）。

---

### 2.2 `gateway-i18n-zh`（11 文件）—— 网关/执行审批中文化

| 文件 | 改动性质 | 关键改动点 |
|---|---|---|
| `agent/chat_completion_wait_notice.py` | 硬编码英文 → i18n | 删除 `_PHASE_TEXT` 英文表；`wait_notice_text(..., *, lang=)` 新增；lead 走 `t("gateway.provider_wait.lead_near"/"lead_waiting")`；phase 走 `t(f"gateway.provider_wait.{phase}")`；watchdog label 映射表 `wall-clock stale/TTFB/stream idle` → `watchdog_*` 键；后缀走 `t("gateway.provider_wait.watchdog_suffix")` |
| `agent/onboarding.py` | 硬编码英文 → i18n | 删除 4 个 `_BUSY_INPUT_HINTS_*` 英文 dict 与 2 个默认串；新增 `_BUSY_MODE_SUFFIX` 与 `_onboarding_text(key, mode, *, gateway)`，zh/sg 取译文、其余取 `lang="en"`；`busy_input_hint_gateway/cli`、`tool_progress_hint_gateway/cli` 改走 `gateway.onboarding.*` / `gateway.cli_onboarding.*` |
| `gateway/platforms/base.py` | 适配层（保 markup，只换词） | 新增 `_is_cjk()`；新增 `_EA_PHRASE_KEYS`（英文短语→`approval.*` 键映射）；新增 `_ea_localized()`（模板内逐短语 replace）、`_ea_localize_label()`（CJK 时把标签后第一个 ASCII `:` 换成全角 `：`）、`_ea_localize_smart_deny_line()`；`_format_exec_approval` 与 `_exec_approval_actions` 走本地化 |
| `gateway/platforms/base_exec_approval.py` | 硬编码英文 → i18n | 新增 `ea_header_text()` / `ea_reason_label_text()` / `ea_action_label(choice)`；新增 `format_approval_window_localized()` + `_window_parts()`；`format_approval_deadline_line()` / `format_approval_timed_out_notice()` 新增 `lang=` 参数并走 `t("approval.exec_deadline"/"exec_timed_out")`；英文常量 `EA_HEADER_TEXT`/`EA_REASON_LABEL_TEXT` 保留作 import 期兜底 |
| `gateway/run.py` | 硬编码英文 → i18n + 恢复策略改动 | hygiene 超时消息 → `t("gateway.hygiene.timeout"/"timeout_doctor_hint")`；`_format_exec_approval_fallback` 文本回退 → `t("approval.exec_smart_deny"/"exec_header"/"exec_fallback_*"/"exec_reason_label")`；`_PROVIDER_ERROR_REPLIES` 从模块级常量**改为函数**（避免 import 期冻结语言），6 个模式 → `t("gateway.provider.rate_limited"/"auth_failed"/"provider_policy"/"connection_interrupted"/"endpoint_unreachable"/"connection_error")`；`_gateway_provider_error_reply` 兜底 → `t("gateway.provider.kept_failing")`；`_rate_limit_reply` → `t("gateway.provider.usage_limit_reset")`；context overflow → `t("gateway.context_overflow.overflow_reply")`；**`build_resume_recovery_note` 重写**：非交互平台不再区分 interactive，空恢复一律 CONTINUE 原任务到完成（保留 plan mode / 审批边界），真实新消息优先 |
| `gateway/run_busy.py` | 硬编码英文 → i18n | 引入 `get_language()`/`localized` 判定；`status_parts` 走 `t("gateway.common.minutes_elapsed")`/`t("gateway.busy_ack.iteration")`/`t("gateway.busy_ack.running_tool")`；分隔符 zh 用 `，`、括号用 `（）`；head/tail 合并为 `t(f"gateway.busy_ack.{key}")`（key ∈ steer_subagents/steer/redirect/queue_subagent/queue_compression/queue/interrupt） |
| `tests/gateway/test_busy_session_ack.py` | 测试适配 | 断言新增中文分支（`正在中断`、`已插入当前运行`） |
| `tests/gateway/test_exec_approval_i18n.py` | **新增测试**（315 行） | 钉住英文逐字节不变 + zh/zh-CN 渲染 + card markup 在翻译后仍存活 + CJK 全角冒号 |
| `tests/gateway/test_restart_resume_pending.py` | 测试适配 | `interactive=False` 与 `True` 现在产出相同 note（断言由 `!=` 改 `==`） |
| `tests/gateway/test_restart_continuation_contract.py` / `tests/gateway/test_restart_continuation_two_sessions.py` | **新增测试** | 钉住"每个平台空恢复都 CONTINUE 原任务"契约 + 双会话离线续跑证据 |

---

### 2.3 `feishu-adapter-local`（1 文件）—— ⚠️ 混装

文件：`plugins/platforms/feishu/adapter.py.patch`。**含汉化相关 + 非汉化修复两类改动**：

**汉化相关：**
- `_EA_REASON_LABEL` 从 `f"**{EA_REASON_LABEL_TEXT}:** "` 改为字面 `"**Why it was flagged:** "`（因该值会被 import 期求值，故改为英文常量，实际渲染走 `_ea_localize_label()`）
- import 从 `EA_HEADER_TEXT, EA_REASON_LABEL_TEXT` 改为 `ea_header_text`（去掉未用 import）
- 新增 `_exec_approval_actions()` 覆写：飞书按钮标签短（`✅ Session` vs `Allow Session`），无法按短语替换；保留 emoji 前缀，`get_language() != "en"` 时用 `ea_action_label(choice)` 取译文
- 卡片头 `f"⚠️ {EA_HEADER_TEXT}"` → `f"⚠️ {ea_header_text()}"`

**非汉化修复（同文件，迁移照搬）：**
- 新增 `_FEISHU_THREAD_ROUTING_ERROR_CODE = 99992402`；`_feishu_send_with_retry` 中新增 99992402 线程路由恢复（回复线程末条 → 退回纯 chat_id 发送），把原先仅音频的兜底**推广到所有消息类型**（text/post/clarify）
- `_is_interactive_operator_authorized(open_id, user_id="")`：允许名单存 user_id，但回调按 open_id 标识操作者——两者都接受，避免 user_id 白名单点不动卡片
- `_validate_card_action` 返回值从 3 元组扩为 4 元组（新增 user_id），并贯穿 `_resolve_approval`/`_resolve_update_prompt`/`_pop_validated_prompt_state`

---

### 2.4 `_unassigned`（26 文件，未归类）—— 全部汉化相关

> meta 标注 `DESCRIPTION=未归类本地改动（待人工归组到正式 bundle）`，`SNAPSHOT_AT=2026-10-13T07:35:40Z`。**这 26 个文件理应并入 `locale-i18n-zh` / `gateway-i18n-zh`。**

**网关 Python（硬编码英文 → i18n）：**

| 文件 | 关键改动 |
|---|---|
| `agent/i18n.py` | `SUPPORTED_LANGUAGES` 新增 `"sg"`；`_LANGUAGE_ALIASES` 新增 `sg/zh-sg→sg`（原 `zh-sg→zh` 改指向 `sg`）、`zh-sg-cn→sg` |
| `gateway/run_shutdown.py` | 抽 `_build_notice_messages()`（`gateway.shutdown_notice.shutting_down/restarting`）与 `_build_cron_interrupt_notice(job_name, restarting)`（`gateway.cron_interrupt.restart/shutdown`）；`_notify_active_sessions_of_shutdown` / `_notify_cron_jobs_of_interrupt` 改走 `t()` |
| `gateway/slash_commands.py` | `_BUSY_MODE_BEHAVIOR` 常量 dict → `_busy_mode_behavior(mode)` 函数（走 `gateway.busy.behavior_*`）；新增 `_busy_modes()`；`_PLATFORM_USAGE` 常量 → `_platform_usage()`（`gateway.platform.usage`）；whoami 三态 → `t("gateway.whoami.tier_unrestricted/tier_admin/tier_user")`；`/platform pause|resume` 5 处 → `t("gateway.platform.*", name=...)`；`HISTORY_UNREADABLE` import 改为 `_history_unreadable` |
| `gateway/slash_commands_goals.py` | `/goal gate add` 授权提示 → `t("gateway.goal.requires_admin")`；`/heartbeat` usage/interval/prompt/set → `t("gateway.heartbeat.*")`；`Agent is running…`/`Nothing to {verb} yet` → `t("gateway.heartbeat.agent_running/nothing_to_pause", verb=)`；`/refine` 空对话 → `t("gateway.heartbeat.nothing_to_refine")`；`No active goal…`/`/subgoal remove` 索引错/`Loops unavailable` → `t("gateway.goal.*")` |
| `gateway/slash_commands_model.py` | stale override 错误 → `t("gateway.model.stale_override", error=)`；模型切换取消 → `t("gateway.model.switch_cancelled", model=)`；文本回退 → `t("gateway.model.switch_confirm_fallback", prefix=)`；config 载入失败 → `t("gateway.model.config_load_failed", error=)` |
| `gateway/slash_commands_session.py` | `HISTORY_UNREADABLE` 常量→ `_history_unreadable()` 5 处；`Cannot retry that message safely`/`Retry failed; transcript was not changed.` → `t("gateway.session.retry_unsafe/retry_failed")`；Codex app-server 压缩 3 条 → `t("gateway.session.codex_compact_nothing/done/failed")` |
| `gateway/slash_commands_status.py` | `HISTORY_UNREADABLE` 模块常量 → `_history_unreadable()` 函数（注释：模块常量会在 import 期冻结语言），4 处调用点更新 |

**前端 i18n 注册（新增 `sg` locale）：**

| 文件 | 关键改动 |
|---|---|
| `apps/shared/src/i18n.ts` | `LOCALE_ENDONYMS` 新增 `sg: '简体'` |
| `apps/shared/src/i18n.test.ts` | 新增断言 `LOCALE_ENDONYMS.sg === '简体'` |
| `web/src/i18n/context.tsx` | import `sg`，`TRANSLATIONS` 注册 `sg` |
| `web/src/i18n/types.ts` | `Locale` 联合类型新增 `"sg"` |
| `web/src/i18n/sg.ts` | **新文件**：`export const sg = zh`（副本，endonym 不同） |
| `web/src/i18n/context.test.ts` | **新文件**：注册/endonym/zh 等价断言 |
| `apps/desktop/src/i18n/catalog.ts` | import + `TRANSLATIONS` 注册 `sg` |
| `apps/desktop/src/i18n/languages.ts` | `LOCALE_OPTIONS` 新增 `{id:'sg', name:LOCALE_ENDONYMS.sg, englishName:'Simplified Chinese', configValue:'sg'}`；`LOCALE_ALIASES` 新增 `sg/zh-sg/zh_sg→sg` |
| `apps/desktop/src/i18n/types.ts` | `Locale` 类型新增 `'sg'` |
| `apps/desktop/src/i18n/sg.ts` | **新文件**：`export const sg = zh` |
| `apps/desktop/src/i18n/sg.test.ts` | **新文件**：sg 注册测试 |
| `locales/sg.yaml` | **新文件**（1050 行 / 965 键）：内容为 zh 的副本，注释标为 "zh-Hans (SG region tag)" |

**i18n 测试（新增）：**
`tests/gateway/test_local_model_connection_reply.py`、`tests/gateway/test_transcript_read_failure.py`（适配 `_PROVIDER_ERROR_REPLIES()`/`_history_unreadable`）、`tests/gateway/test_cron_interrupt_i18n.py`、`tests/gateway/test_history_unreadable_i18n.py`、`tests/gateway/test_run_i18n.py`（207 行）、`tests/gateway/test_shutdown_notice_i18n.py`、`tests/gateway/test_slash_commands_i18n.py`（均为新文件）

---

### 2.5 `main-session-notifier`（6 文件）—— ⚠️ 功能为主，附带 i18n

**功能（非汉化，迁移照搬）**：跨会话"主会话唯一提醒路由"——已完成 / 需要决策 / 需要人工确认三类提醒；托管模式下仅完成与危险动作打扰。
新增文件 `gateway/main_notifier.py`（`is_main_session` + `classify` 纯函数）、`gateway/run_main_notifier.py`；改动 `gateway/run_turn.py`、`gateway/run_turn_runner.py`、`tools/approval_gateway_wait.py`。

**汉化相关（顺带把 turn 文案改走 i18n，11 处 `t()`）**：`gateway.turn.agent_inactive`、`gateway.turn.auto_reset_context`、`gateway.turn.hint_rate_limited`、`gateway.turn.hint_rejected`、`gateway.turn.hint_usage_limit`、`gateway.turn.hint_usage_limit_reset`、`gateway.turn.history_unavailable`、`gateway.turn.unexpected_silence`（这些键在 `locales/*.yaml` 的 `gateway.turn:` 段）。

---

## 3. 非汉化 bundle（一句话用途 + 迁移照旧搬运）

| bundle | 用途 | 迁移 |
|---|---|---|
| `full-trust-delegation` | 全托管「一次做完」：触发词托管、审批/澄清自决、自行定序、可回退（新增 `agent/autonomy_policy.py`，含中文触发词「一次做完/一次做到底/做完之后叫我」等 20+ 个，非 i18n 键） | **照旧搬运** |
| `heartbeat-terminal-stamp` | 工作结束心跳消息追加终态标记（已完成/正在等待用户回复/已中断）；`gateway/turn_context.py` 新增 `_heartbeat_holder`/`_heartbeat_last_text`/`_heartbeat_terminal` 三个字段 | **照旧搬运** |
| `camofox-tab-recreate` | Camofox 过期 tab 返回 410 时按 404 语义重建（`404` → `in (404, 410)`） | **照旧搬运** |
| `local-relay-fastmode` | sub2api 中继（`sub2api.riu.edu.kg`）的自定义 provider 允许 fast-mode 路由（`hermes_cli/models.py::_fast_mode_route_supported` 新增 host 判定 + 6 个 provider 名白名单） | **照旧搬运**（注意 0.22.0 若重写了该函数需重新对齐） |
| `doctor-vendor-slug-declared-models` | doctor vendor-slug 检查：provider 自声明 `models:` 列表中的 id 视为合法（本地聚合代理如 magpie 的 `group/...` id 误报修复） | **照旧搬运** |

---

## 4. 汉化相关改动点逐条统计表

| 层面 | 改动点数（可核验） |
|---|---|
| locale 键（en.yaml 新增行） | **906** 行（去重 848 个键 token） |
| zh.yaml 真实译文（含 CJK 的新增行） | **826** 行 |
| sg.yaml 新 locale（=zh 副本） | **965** 键 / 1050 行 |
| 其余 15 个 locale 的新增键占位 | 各 ~894 行（纯 parity） |
| Python 代码 `t(...)` 调用点（非测试） | **134** 处 |
| 前端 i18n 文件改动 | **12** 个文件（含 3 个新增 `.ts`） |
| 新增汉化相关测试文件 | **10** 个 |
| 新增汉化工具脚本 | **3** 个 |

**按 bundle 的 `t()` 调用点（非测试）分布**：`gateway-i18n-zh` 52、`_unassigned` 49、`locale-i18n-zh` 22、`main-session-notifier` 11（其余 6 个 bundle 为 0）。

---

## 5. 不确定项 / 迁移注意事项

1. **`_unassigned` 尚未归组**：local-patches 清单不含它，meta 明确标 "待人工归组"。这 26 个文件是汉化工作的一部分，**迁移前建议先并入 `locale-i18n-zh` / `gateway-i18n-zh`**，否则 0.22.0 重装基线后不会自动重应用。
2. **`sg` locale 的语义**：`sg` 内容与 `zh` 完全相同（前端 `sg.ts` 就是 `export const sg = zh`），仅 endonym（"简体"）与 config 值不同。上游 0.22.0 若不认识 `sg`，需要保留本地 `agent/i18n.py` 的 alias 与前端注册改动。
3. **机器可读契约串禁止本地化**：`CRON_RESPONSE_PREFIX`、`CRON_RESPONSE_DIVIDER`、`memory` 分类 label（"Skill"/"Memory"/"User profile"）在代码里被**刻意保持英文**（有 3 处外部消费者解析）。0.22.0 若改了这些串，反解析会静默失效。
4. **`locale-i18n-zh` 的 28 文件 vs 28 patch 并非一一映射**：3 个 patch 是新增文件（scripts/tests），17 个 locale 中只有 17 个 yaml 有 patch——已核验 declared locales 全部有对应 patch，无遗漏。
5. **parity 测试约束**：`tests/agent/test_i18n.py` 要求所有非 en catalog 与 en 键集一致。0.22.0 若新增/删除键，必须同步 17 个 yaml，否则该测试挂。
6. **`gateway/run.py` 的恢复策略改动不只是汉化**：`build_resume_recovery_note` 让"空恢复在所有平台都 CONTINUE 原任务"，这是行为改动（原上游对 non-interactive 才有此行为）。迁移时需确认 0.22.0 是否已采纳，避免覆盖。
7. **`feishu-adapter-local` 混装**：`_FEISHU_THREAD_ROUTING_ERROR_CODE=99992402` 恢复逻辑与 user_id 允许名单修复是非汉化改动，与汉化同文件，迁移时不能只挑汉化部分。
8. **未读取 runtime 工作树的实际文件内容**（任务要求只读 patches），因此"改动性质"分类基于 patch 内容的 `+/-` 行；如需确认某改动是否已在 0.22.0 上游合入，需另跑 `git log`/diff 对比。

---

*本文件由只读盘点生成，未修改任何现有文件、未重启服务、未 ssh 其他主机。所有结论均可回溯到上述 patch 文件与 runtime-local-patches.list 的具体行。*
