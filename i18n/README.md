# Hermes 汉化方案

本目录备份这台沙箱的 Hermes 界面中文化改动。**这些是完整产物，不依赖任何自愈体系也能恢复。**

> ## ⚠️ 升级到 0.22.0：先读迁移报告
>
> 上游 0.22.0 已**自带完整简体中文**（`locales/zh.yaml` 3433 键、`zh.tui.yaml` 1301 键、desktop 层全套）。
> 我们旧版 905 个汉化键中 **89.4% 上游已自行汉化**，13 个源补丁上游已自行实现，**应当撤除而非重打**。
>
> - 完整迁移报告：[`MIGRATION-0.21.5-to-0.22.0.md`](MIGRATION-0.21.5-to-0.22.0.md)
> - 适配策略与逐 bundle 处置：[`migration/ADAPTATION-PLAN.md`](migration/ADAPTATION-PLAN.md)
> - 旧版改动全盘清单：[`migration/legacy-changes.md`](migration/legacy-changes.md)
> - 旧键命运（含可复跑脚本）：[`migration/key-fate-summary.md`](migration/key-fate-summary.md) / `migration/key_fate.py`
> - 上游覆盖度审计（哪些补丁该撤）：[`migration/upstream-coverage.md`](migration/upstream-coverage.md)
> - 未汉化缺口统计：[`migration/translation-gaps.md`](migration/translation-gaps.md)
>
> **下面这一节描述的是 0.21.5 的做法，仅供迁移时对照与回滚参考。**

## 目标 commit（0.21.5 基线）

```
f97608f178d1ffeca59860195ab7da295f7c8e5f
```

沙箱内 runtime 路径（换成你自己的 HERMES_HOME）：

```text
$HERMES_HOME/npm/node_modules/hermes-agent/runtime/hermes-agent
```

下文称 `<HERMES>`。补丁一律在 `<HERMES>` 内执行。

## 内容

| 文件 | 说明 |
|---|---|
| `locales/*.yaml` | 18 个语言文件的**汉化后完整副本**。`zh.yaml` 是全量简体中文；`sg.yaml` 内容与 `zh.yaml` 完全一致（见下方「`sg` 语言码」）；其余语言补齐了缺失键（此前缺键时界面会回落到英文） |
| `locales-all.patch` | `git diff -- locales/`，相对上游基线的完整改动 |
| `gateway-i18n-zh.patch` | Gateway 与 agent 侧 6 个 Python 文件的汉化改动（运行时语言重读、CJK 分隔符、等待提示、onboarding） |
| `locale-i18n-src.patch` | cron 投递包装 / CLI tips / 自改进摘要三处英文串的 Python 侧改动（`t()` 接入 + 英文自回落） |
| `sg-language-alias.patch` | 新增 `sg` 语言码（见下方「`sg` 语言码」） |
| `scripts/` | locales 维护工具：目录生成、段落同步、重复键检查 |
| `tests/` | 4 个新增回归测试的完整副本 |

五个补丁**内容互补，全部都要应用**：`gateway-i18n-zh.patch` 与 `locale-i18n-src.patch`
动 Python（运行时如何取文案），`locales-all.patch` 动 YAML（文案本身）。
`feishu-adapter-zh.patch` 单独修飞书审批卡片——它把标题/按钮从硬编码英文常量改成
走 `t()` 的函数调用，**漏了它卡片就还是英文**。
`sg-language-alias.patch` 只加语言码，不影响上述任何一个。

## `sg` 语言码

需求是让界面显示中文，但**配置里不出现 `zh` 这个属性名**（避开第三方工具按语言码
识别地域特征）。做法是把 `sg` 注册成一个独立语言码，`locales/sg.yaml` 的内容与
`zh.yaml` 完全相同，所以用户选 `sg` 看到的也是完整中文界面。

```yaml
# config.yaml
display:
  language: sg      # 等价于 zh，但配置里不含 zh 字样
```

补丁做三件事：

1. `agent/i18n.py` 的 `SUPPORTED_LANGUAGES` 加入 `sg`。
   **这一步不能省**：`_normalize_lang()` 对不在表里的码会静默回落到 `en`，
   表现为「配了 sg 但界面全英文」。
2. `_LANGUAGE_ALIASES` 把 `zh-sg` / `zh-sg-cn` / `sg` 指向 `sg`。
   注意上游原本把 `zh-sg` 映射到 `zh`，这里改了指向。
3. 修两处硬编码 `startswith("zh")` 判断（`agent/onboarding.py`、
   `gateway/run_busy.py`）。**这是最容易漏的一处**：它们按前缀判断是否中文，
   `sg` 不匹配就会掉回英文，且测试套件测不出来（测试只覆盖 `zh`）。

`locales/sg.yaml` 的头部注释同样不含「中文 / 简体」字样，避免扫文件内容被识别。

## 恢复步骤

先设好两个变量，后续命令都用它们，不写死相对层级：

```bash
# 按你的实际路径改这两行
HERMES_CFG=/home/hatch/workspace/repo-hermes-config
HERMES_RT=$HERMES_HOME/npm/node_modules/hermes-agent/runtime/hermes-agent   # 默认 HERMES_HOME=~/.hermes

cd "$HERMES_RT" || exit 1

# ① 打五个补丁（已应用过的会被 --check 挡住，不会重复打）
for p in gateway-i18n-zh locale-i18n-src feishu-adapter-zh sg-language-alias locales-all; do
  git apply --check "$HERMES_CFG/i18n/$p.patch" && git apply "$HERMES_CFG/i18n/$p.patch"
done

# ② 放工具脚本与回归测试
cp "$HERMES_CFG"/i18n/scripts/*.py scripts/
mkdir -p tests/cron tests/hermes_cli tests/agent
cp "$HERMES_CFG"/i18n/tests/test_exec_approval_i18n.py   tests/
cp "$HERMES_CFG"/i18n/tests/test_review_summary_i18n.py tests/agent/
cp "$HERMES_CFG"/i18n/tests/test_cron_wrapper_i18n.py   tests/cron/
cp "$HERMES_CFG"/i18n/tests/test_tips_i18n.py           tests/hermes_cli/
```

然后确认 `display.language: zh` 已在 `config.yaml` 生效，运行回归测试：

```bash
cd "$HERMES_RT"
python -m pytest tests/cron/test_cron_wrapper_i18n.py \
                 tests/hermes_cli/test_tips_i18n.py \
                 tests/agent/test_review_summary_i18n.py \
                 tests/agent/test_i18n.py -q -o addopts=''
```

期望全绿（本机实测 183 passed / 0 failed）。最后重启网关，新文案才生效。

## 修复过的三处（本轮）

| 用户可见的英文原句 | 位置 | 处理 |
|---|---|---|
| `Cronjob Response: <name>` / `job_id: <id>` / `To stop or manage this job...` | `cron/scheduler_delivery.py` | 三段走 `cron.*` locale 键；**前缀 `Cronjob Response:` 与 `job_id: ` 保持英文**，因为 `strip_cron_wrapper`（`gateway/platforms/yuanbao.py`）、context compressor 与桌面端 TS 都按字面量解析它 |
| `✦ Tip: agent.api_max_retries (default 3) controls...` | `hermes_cli/tips.py` 101 条 TIPS + 11 个占位符 | 建 `TIP_IDS` / `PLACEHOLDER_IDS` 索引表 + `tip_label()`；字典由 `scripts/gen_tips_catalog.py` 生成，共 392 条 zh 译文 |
| `💾 Self-improvement review: Skill 'x' patched` | `agent/background_review.py` | 前缀与动词走 `review.*` 键；**分类标签 `Skill`/`Memory`/`User profile` 保持英文**，因为 `_classify_review_result()` 靠 `startswith` 分类 |

## 设计要点

- **文案全部走 locale 文件，不硬编码。** Gateway 的设计是 adapter 只负责 markup（加粗、HTML、代码围栏），具体文字从 `gateway.platforms.base_exec_approval` 读取，保证各端说法一致。
- **`t()` 没有 fallback 参数**，所以 tips 的查表函数自己做英文自回落（`_localized()`）；切到未翻译语言时界面不会变空。
- **契约串不许本地化。** 凡是别处按字面量解析的字符串（cron 包装头、review 分类标签），只本地化它周围的措辞。判断方法：先 `grep` 出所有消费者，再决定哪些字节能动。
- **Python 侧改动只解决"何时取哪套文案"**：渲染路径每次提示都重读当前语言，`display.language` 才能按用户即时生效；另有 `_is_cjk()` 让中文串后的 `:` 分隔符改用全角，避免中英混排难看。
- **非中文语言也补键**：`en.yaml` 等同样有改动。这是必要的——若只有 `zh.yaml` 补齐而其他语言缺键，切到英文时界面会混排中文。三段（cron/tips/review）必须 17 个 catalog 同步，用 `scripts/sync_locale_section.py` 做，并跑 `scripts/check_locale_dup_keys.py` 防重复键。
- 若日后把汉化改动接回自愈模块，`TARGET_COMMIT` 必须与当前 runtime HEAD 匹配，否则应用会被静默跳过。

## 与 hermes-selfheal 的关系

本目录不含任何自愈内容。若 runtime 被基线重装，上述补丁需重新应用；
若想让「重装后自动打回」，另行部署独立仓库 `hermes-selfheal`。两者互不依赖。

Hermes 升级后若上游改动冲突，`git apply` 会失败。此时应手动比对冲突段，更新本目录的补丁，再重新应用。
