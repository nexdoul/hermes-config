# 旧版中文键 → 0.22.0 命运分析

> 由 `i18n/scripts/key_fate.py` 生成（可复跑）。输入：`baseline/{old_en,new_en,upstream_zh}.json`。
> 判据分类：SURVIVES / MOVED-TO-UPSTREAM / RENAMED / GONE。

## 结果（共 905 个旧 zh 键）

| 分类 | 数量 | 占比 | 含义 |
|---|---|---|---|
| **MOVED-TO-UPSTREAM** | **809** | **89.4%** | 新版同名路径存在**且上游 zh.yaml 已是中文** —— 上游自己收编了 |
| GONE | 48 | 5.3% | 新版确无对应物（功能删除或改成非文案） |
| RENAMED | 48 | 5.3% | 新版换了键名/分段，语义等价（含 3 条低置信待复核） |
| SURVIVES | 0 | 0% | （0 条：凡同路径存在的，上游都已译成中文，故归入 MOVED-TO-UPSTREAM） |

## 结论

**这是本次迁移最重要的一个数字**：我们旧版 905 个汉化键中，**89.4% 上游 0.22.0 已经自己翻译好了**。
只有 10.6%（48 GONE + 48 RENAMED）需要我们处理 —— 其中 48 条 GONE 是上游删掉的功能，
真正需要人工重新挂钩的只有 **48 条 RENAMED**（3 条低置信需复核）。

这解释了主节点 agent 报的"汉化文本对不上"：旧补丁按**旧键名**（如 `status.free_tier`、`platform.tier_admin`、
`review.memory_op.*`、`cron.manage_hint`）注入，而这些键在新版要么被上游换名、要么整个子树重组
（`review.*` → `display.review.*`、`platform.*` → `gateway.whoami.*`），于是译文落到了没人读的键上。

## RENAMED 明细（48 条，需重新挂钩）

完整列表见 `key-fate.csv`（`fate=RENAMED`）。主要搬迁模式：

| 旧命名空间 | 新命名空间 | 说明 |
|---|---|---|
| `review.*` | `display.review.*` | 自我改进回顾的渲染整体下移 |
| `platform.tier_*` | `gateway.whoami.tier_*` | 层级查询并入 whoami |
| `gateway.session.retry_*` | `gateway.retry.*` | session 子树并入 retry |
| `gateway.busy_ack.*` | `gateway.busy.*` | 忙态回执换命名空间 |
| `provider.*` | `gateway.errors.*` | provider 错误并入 gateway.errors |
| `cron_interrupt.*` | `gateway.shutdown.cron_interrupted` | 两条合并为一条 |

## 低置信条目（3 条，人工复核）

`evidence` 字段含 `conf=value-weak` 的 3 条 —— 按键名同尾但英文值有差异，判定为 RENAMED 属推测。
复跑命令：`python3 i18n/scripts/key_fate.py`，然后
`grep value-weak i18n/migration/key-fate.csv`。
