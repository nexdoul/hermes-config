# 译文取舍复核记录

用户策略：**以上游 `zh.yaml` 为基底，仅在我们旧译文明显更贴切处替换。**

按此策略逐条复核后的结论：**全部保留上游，无一条需要替换。**

## 复核依据

我们 0.21.5 的 zh 共有 **836 条真中文**，在新版中的归宿：

| 情形 | 数量 | 处理 |
|---|---|---|
| 上游已汉化且**与我们逐字节相同** | 303 | 保留上游（无差异） |
| 上游已汉化且**是更完整版本（超集）** | 13 | **保留上游** —— 上游在旧句后补了新增内容 |
| 我们译过、上游 0.22.0 已删该功能（GONE） | 27 | 丢弃 |
| 我们译过、上游换了键名但**上游译文已覆盖** | 2 | 保留上游 |
| 其余（上游在 0.21.5 就已有此译，未变） | 491 | 保留上游 |

## 13 条"差异"逐条判定

全部属于以下两类，**均以上游为准**：

**(a) 上游是超集**（译文=我们的措辞 + 新增内容），取上游才不会丢新版信息：

| 键 | 说明 |
|---|---|
| `gateway.heartbeat.set` | 上游多出"仅在网关运行期间有效——持久化调度请用 hermes cron" |
| `gateway.platform.usage` | 上游多出 3 行子命令说明 |
| `gateway.whoami.tier_admin` / `tier_user` / `tier_unrestricted` | 上游多出"斜杠命令"说明行 |

**(b) 措辞微调，两者等价**，按"改动最小"取上游：

| 键 | 我们的 | 上游的 |
|---|---|---|
| `gateway.heartbeat.interval_too_small` | 间隔太小——最小为… | 间隔太短——最小为… |
| `gateway.model.switch_cancelled` | 模型切换已取消 | 已取消切换模型 |
| `gateway.platform.already_paused` | 已经暂停了 | 已处于暂停状态 |
| `gateway.platform.already_retrying` | 已经在重试了 | 已在重试中 |
| `gateway.platform.resumed` | 下次巡检时重试 | 将在下一次监视器轮询时重试 |
| `gateway.retry.unsafe` | 无法安全重试该消息 | 无法安全地重试该消息 |
| `gateway.fast.picker_title` / `gateway.reasoning.picker_title` | — | 差异仅转义符层数（`\\n` vs `\n`），上游为正确渲染形式 |

## 8 条"真缺口"复核结论：**均无需翻译**

| 键 | 实际内容 | 判定 |
|---|---|---|
| `gateway.topic.setup_image_caption` | `"BotFather → Bot Settings → Threads Settings"` | Telegram 后台菜单路径，须与界面原文一致 |
| `platform.discord.approval.by_user` | `"{user} {label}"` | **纯占位符**，无文案 |
| `platform.telegram.approval.resolved_by_user`（同键） | `"{user} {label}"` | 同上 |
| `platform.telegram.gmail_triage.appended_by` | `"— {user} {label}"` | 纯占位符 + 破折号 |
| `hubs.agents.detail.tokens` / `hubs.agents.diff.tokens` | `"token"` | 技术单位标签 |
| `slashCmd.debug.mem.arrayBuffers` | `"array buffers"` | 调试面板字段名 |
| `slashCmd.debug.mem.rss` | `"rss"` | 调试面板字段名 |

→ 这 8 条要么不含可译文案（纯占位符），要么是**技术标识**（翻成中文反而有害）。
子会话把它们列为"缺口"是基于"值为 ASCII"的机械判据，逐条人工复核后**判定为不应翻译**。

## 结论

0.22.0 的简体中文**直接采用上游 `locales/zh.yaml` 与 `zh.tui.yaml` 原样**即可，
不需要注入我们旧版的任何一条译文 —— 上游 89.4% 已自行汉化，且质量不低于我们。
