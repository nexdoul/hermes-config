# hermes-config

本仓库备份这台沙箱上的 Hermes 配置、skills 与自愈补丁。**私有仓库，不含任何凭据。**

## 收录范围

| 目录 / 文件 | 内容 |
|---|---|
| `policies/default-parallel-delegation.md` | 默认并行委派候选、真实行为证据与限制；当前生产未启用，不是稳定性保证 |
| `tests/run_live_delegation.py` | 隔离真实 AIAgent/子 Agent 行为复现，附脱敏结果 |
| `config.yaml` | 主配置：providers、模型别名、审批策略、平台、浏览器、toolsets。密钥只以 `key_env` 形式引用环境变量名，无明文 |
| `AGENTS.md` | 本机工作约定与踩坑记录 |
| `SOUL.md` | 说话风格 |
| `VERSIONS` / `venv-extra-packages.txt` / `env.sh` | 版本与运行环境说明 |
| `i18n/` | **界面中文化成果**（locales 全文 + 补丁 + 回归测试），见 `i18n/README.md` |
| `skills/` | 自定义 skills（含自建的 `remote-dev`）。**不含**官方 bundled skills（随 Hermes 安装自带） |
| `cron/jobs.json` | hermes cron 任务定义。**不含** `executions.db` 等运行态数据 |
| `scripts/` | 运维脚本。`browser/` 已参数化可移植，网关重启与 javdb 链为本机策略原样保留，详见 `scripts/README.md` |
| `gateway-starts.log` | 网关启动记录（用于排查崩溃时间线） |

### 关于自愈

本仓库**不含 runtime 本地补丁自愈体系**。旧版本曾收录 `patches/`（6 个 bundle 的 `.patch` + `files` + `meta`）与 `runtime-local-patches.list`，现已迁出，本仓库不再分发、也不再声明依赖它。`patches/` 与 `runtime-local-patches.list` 的全部内容由独立的 hermes 自愈模块维护，在恢复时手动接回。

普通使用者拿到本仓库时，缺失自愈模块**不影响汉化功能**——`i18n/` 下的汉化成果是自足的，直接应用即可；只是 runtime 被基线重装后不会自动打回，需要重跑一次 `i18n/README.md` 里的恢复步骤。

## 不收录（有意排除）

- `.env`、`auth.json`、token、密钥、`.git-credentials` —— 凭据一律不进仓库
- `state.db`、`sessions/`、`cache/`、`checkpoints/`、`logs/`、`npm/`、`lsp/` —— 大体积或运行态
- `whatsapp/`、`feishu_seen_message_ids.json` —— 平台运行态
- `cron/` 下的 `.lock`、`.tmp`、`executions.db`、`notepad.db`、`ticker_*` —— 调度器状态
- `skills/.locks/`、`.usage.json`、`.curator_*`、`.hub/`、`.bundled_manifest` —— skills 运行态
- `config.yaml.bak-*` —— 历史备份，由 `config.yaml` 的 git 历史取代

## 恢复方式

**只恢复汉化（最小路径，不需要自愈模块）**

1. 安装 Hermes，把本仓库内容放回 `~/.hermes/`。
2. 确认 `display.language: zh` 已在 `config.yaml` 生效。
3. 在 `<HERMES>`（runtime git 仓库）内按 `i18n/README.md` 的应用步骤打补丁、拷测试、跑回归。
4. 重启网关使新文案生效。
5. 补回凭据：`~/.hermes/.env`（API keys）、`~/.config/github/token.env`（GitHub token）、`~/.ssh/`（VPS 密钥）。

**完整恢复（含自愈）**：除上述外，还需另行部署独立的 hermes 自愈模块（维护 `runtime-local-patches.list` 与 `patches/`），

由它负责 runtime 被基线重装后自动打回本地补丁。

## 安全约定

- 提交前跑凭据扫描：`python3 /home/hatch/workspace/remote-dev-config-scan.py`（需按当前仓库路径调整）。
- `.gitignore` 不是安全扫描；上传前仍须人工检查生产 `.env`、证书、上传数据。
- 本仓库是配置备份，不等于可直接运行的环境；恢复后必须重新验证网关、cron 与各 VPS 连通性。
