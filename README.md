# hermes-config

本仓库备份这台沙箱上的 Hermes 配置、skills 与自愈补丁。**私有仓库，不含任何凭据。**

## 收录范围

| 目录 / 文件 | 内容 |
|---|---|
| `config.yaml` | 主配置：providers、模型别名、审批策略、平台、浏览器、toolsets。密钥只以 `key_env` 形式引用环境变量名，无明文 |
| `AGENTS.md` | 本机工作约定与踩坑记录 |
| `SOUL.md` | 说话风格 |
| `VERSIONS` / `venv-extra-packages.txt` / `env.sh` | 版本与运行环境说明 |
| `runtime-local-patches.list` | 9 个 runtime 本地补丁的自愈清单 |
| `patches/` | 上述补丁的 `.patch` 文件、`files` 清单与 `meta`（记 `TARGET_COMMIT`） |
| `skills/` | 自定义 skills（含自建的 `remote-dev`）。**不含**官方 bundled skills（随 Hermes 安装自带） |
| `cron/jobs.json` | hermes cron 任务定义。**不含** `executions.db` 等运行态数据 |
| `scripts/` | 自愈与运维脚本 |
| `gateway-starts.log` | 网关启动记录（用于排查崩溃时间线） |

## 不收录（有意排除）

- `.env`、`auth.json`、token、密钥、`.git-credentials` —— 凭据一律不进仓库
- `state.db`、`sessions/`、`cache/`、`checkpoints/`、`logs/`、`npm/`、`lsp/` —— 大体积或运行态
- `whatsapp/`、`feishu_seen_message_ids.json` —— 平台运行态
- `cron/` 下的 `.lock`、`.tmp`、`executions.db`、`notepad.db`、`ticker_*` —— 调度器状态
- `skills/.locks/`、`.usage.json`、`.curator_*`、`.hub/`、`.bundled_manifest` —— skills 运行态
- `config.yaml.bak-*` —— 历史备份，由 `config.yaml` 的 git 历史取代

## 恢复方式

1. 安装 Hermes（版本见 `VERSIONS`），把本仓库内容放回 `~/.hermes/`。
2. `~/.hermes/scripts/runtime-patch-snapshot.sh` 重新生成补丁基线。
3. `bash ~/bin/hermes-start`：入口会自动按 `runtime-local-patches.list` 重应用全部本地补丁，并由 `hermes-selfheal` cron 每 5 分钟兜底。
4. 补回凭据：`~/.hermes/.env`（API keys）、`~/.config/github/token.env`（GitHub token）、`~/.ssh/`（VPS 密钥）。
5. `hermes cron` 从 `cron/jobs.json` 恢复任务定义。

## 安全约定

- 提交前跑凭据扫描：`python3 /home/hatch/workspace/remote-dev-config-scan.py`（需按当前仓库路径调整）。
- `.gitignore` 不是安全扫描；上传前仍须人工检查生产 `.env`、证书、上传数据。
- 本仓库是配置备份，不等于可直接运行的环境；恢复后必须重新验证网关、cron 与各 VPS 连通性。
