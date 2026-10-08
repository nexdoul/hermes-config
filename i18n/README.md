# Hermes 汉化方案

本目录备份这台沙箱的 Hermes 界面中文化改动。**这些是完整产物，不依赖任何自愈体系也能恢复。**

## 目标 commit

```
f97608f178d1ffeca59860195ab7da295f7c8e5f
```

窗口路径（沙箱内）：

```text
/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent
```

下文称 `<HERMES>`。补丁一律在 `<HERMES>` 内执行。

## 内容

| 文件 | 说明 |
|---|---|
| `locales/*.yaml` | 17 个语言文件的**汉化后完整副本**。`zh.yaml` 是全量简体中文；其余语言补齐了缺失键（此前缺键时界面会回落到英文） |
| `locales-all.patch` | `git diff -- locales/`，相对上游基线的完整改动 |
| `gateway-i18n-zh.patch` | Gateway 与 agent 侧 6 个 Python 文件的汉化改动（运行时语言重读、CJK 分隔符、等待提示、onboarding） |
| `zh-yaml.patch` | 只含 `zh.yaml` 的改动，便于单独核对简体中文 |
| `tests/` | 两个新增回归测试的完整副本 |

`gateway-i18n-zh.patch` 与 `locales-all.patch` **内容互补**：前者动 Python（运行时如何取文案），后者动 YAML（文案本身）。两者都要应用。

## 恢复步骤

在 `<HERMES>` 目录内执行：

```bash
git apply --check i18n/gateway-i18n-zh.patch && git apply i18n/gateway-i18n-zh.patch
git apply --check i18n/locales-all.patch      && git apply i18n/locales-all.patch
cp i18n/tests/test_exec_approval_i18n.py  tests/gateway/
cp i18n/tests/test_i18n_chinese_regression.py tests/agent/
```

然后确认 `display.language: zh` 已在 `config.yaml` 生效，运行回归测试：

```bash
python -m pytest tests/agent/test_i18n_chinese_regression.py tests/gateway/test_exec_approval_i18n.py -q
```

## 设计要点

- **文案全部走 locale 文件，不硬编码。** Gateway 的设计是 adapter 只负责 markup（加粗、HTML、代码围栏），具体文字从 `gateway.platforms.base_exec_approval` 读取，保证各端说法一致。
- **Python 侧改动只解决"何时取哪套文案"**：渲染路径每次提示都重读当前语言，`display.language` 才能按用户即时生效；另有 `_is_cjk()` 让中文串后的 `:` 分隔符改用全角，避免中英混排难看。
- **非中文语言也补键**：`en.yaml` 等同样有改动。这是必要的——若只有 `zh.yaml` 补齐而其他语言缺键，切到英文时界面会混排中文。
- 若日后把汉化改动接回自愈模块，`TARGET_COMMIT` 必须与当前 runtime HEAD 匹配，否则应用会被静默跳过。

Hermes 升级后若上游改动冲突，`git apply` 会失败。此时应手动比对冲突段，更新本目录的补丁，再重新应用。
