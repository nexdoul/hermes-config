---
name: remote-dev
description: "用于 VPS 项目的本地优先开发、安全发布、健康检查和自动回滚."
version: 0.2.0
author: 用户与 Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [ssh, 本地开发, 安全发布, 断点恢复]
---

# 本地优先的远程开发

Agent、编辑器、依赖安装、构建与测试全部留在沙箱；VPS 仅接收发布物、保存备份、切换链接、重启指定服务和做有界健康检查。本 skill 不提供远端开发模式，不安装远端 agent，不接管 SSH 基础设施。

## 适用场景

- 在 krvps、usvps、hkvps、cnvps 上维护网站或服务，先在沙箱修改验证，再发布。
- 上次开发被沙箱重启打断，需要从持久目录和 checkpoint 恢复。
- 发布失败需要自动恢复，或显式回滚到已知版本。
- 不适用：数据库迁移、线上数据修补、系统升级、首次生产目录迁移；这些必须单独审查。

## 不可违反的纪律

1. **线上 docroot 禁止直接编辑。** `patch`、`write_file`、编辑器只指向本地工作副本；禁止通过 SSH 拼接写入在线代码，禁止手动 `scp` 零散文件上线。
2. **所有发布必须经过本 skill 的 `scripts/deploy.sh`。** 不绕过本地构建、测试、备份、校验、健康检查或失败回滚。
3. **远端禁止重活：** 不执行 npm build、docker build、依赖安装、编译、测试套件、AI agent。依赖、二进制与容器镜像在本地按目标架构构建；上线只加载兼容的产物/启动已有镜像。
4. **krvps 稳定性优先。** 发布前说明改动、影响的唯一服务和恢复路径；得到该次生产发布授权后才运行 deploy。只重启配置指定的应用服务，不重启主机、网关、SSH 或其他服务。
5. **不得触碰 104 通道。** `~/.reverse-ssh-104`、`~/ssh-infra` 及其别名、符号链接、巡检任务均属于另一条生产链路；本 skill 不读写它们，不修改 SSH 配置。
6. **持久化目录必须在 `/home/hatch` 下。** 不在临时目录保存工作副本、配置、checkpoint、构建产物和任务日志。
7. **配置和脚本不含任何密码、私钥、token。** 仅使用既有 SSH 别名；生产 `.env` 留在远端 shared，不下载、不提交、不进入发布物。
8. 配置中的重启命令属于受信任代码，必须使用 `read_file` 逐项审核；配置/工作目录只允许 ASCII 路径组件，项目名可用英文短名。命令阻断规则只是防误操作，不是隔离恶意 shell 的安全边界。

## 前置条件与布局

本地：Linux、Bash、Python 3 + PyYAML、Git、GitHub CLI（gh）及有效 GitHub 认证、rsync、OpenSSH。远端：Bash、rsync、curl、flock 和 GNU 基础工具；无须远端 Python/Node 开发环境。

每个项目一份 YAML，小配置从 `templates/projects/项目名.yaml` 复制到持久项目配置目录，例如 `/home/hatch/workspace/remote-dev/projects/网站名.yaml`；编辑真实路径、命令和健康检查，不能直接运行占位模板。

推荐远端结构：

```text
项目根目录/
  releases/版本号/     # 独立发布目录，已激活版本不再修改
  current -> releases/版本号
  shared/             # .env、uploads、日志等可变数据
  backups/时间戳/      # 上线前保存的可恢复代码快照，最近 5 份
```

当前实现要求 `shared/uploads`、`shared/logs`、`shared/.env` 预先存在，并为每个 release 建立指向 shared 的软链接；不需要的共享项可在独立初始化时创建空目录/空文件。Web 服务 docroot/应用工作目录必须指向 `current`。如果现有 docroot 是普通目录，脚本应拒绝上线：先出具独立迁移方案与备份，确认维护窗口；**本 skill 不自动搬迁或覆盖现有生产目录**。数据库、用户上传等 shared 数据不是发布备份的覆盖范围。

## Hermes 原子操作分层

- 决策层：确定项目与授权范围，审查 diff、依赖兼容性和健康判据。
- 本地原子层：`search_files`、`read_file`、`write_file`、`patch`；`terminal` 执行本地 Git/构建/测试与脚本。
- 传输层：由脚本封装 SSH、rsync，不把本地终端全局重定向到 VPS。
- 发布安全层：受限路径、持久状态、并发互斥、时间戳备份、原子切换、健康检查、失败恢复。

本 skill 优先于旧的“远端 patch 循环”：不要将旧 skill 的远端编辑/测试操作带入这里。

## 调用方式

`terminal` 中使用加载 skill 后展开的 `${HERMES_SKILL_DIR}`；以下 `CONFIG` 为已审核 YAML 的绝对路径，checkpoint 每次操作使用独立持久目录，不能放在项目内或包含项目。

```text
bash ${HERMES_SKILL_DIR}/scripts/sync.sh --config CONFIG --checkpoint /home/hatch/workspace/remote-dev/state/pull-001
bash ${HERMES_SKILL_DIR}/scripts/sync.sh --config CONFIG --checkpoint /home/hatch/workspace/remote-dev/state/pull-001 --resume
bash ${HERMES_SKILL_DIR}/scripts/deploy.sh --config CONFIG --checkpoint /home/hatch/workspace/remote-dev/state/deploy-001 --check
bash ${HERMES_SKILL_DIR}/scripts/deploy.sh --config CONFIG --checkpoint /home/hatch/workspace/remote-dev/state/deploy-001
bash ${HERMES_SKILL_DIR}/scripts/deploy.sh --config CONFIG --checkpoint /home/hatch/workspace/remote-dev/state/deploy-001 --status
bash ${HERMES_SKILL_DIR}/scripts/deploy.sh --config CONFIG --checkpoint /home/hatch/workspace/remote-dev/state/deploy-001 --resume
bash ${HERMES_SKILL_DIR}/scripts/rollback.sh --config CONFIG --checkpoint /home/hatch/workspace/remote-dev/state/rollback-001 --release 已知版本ID
```

`--check` 仅做本地检查，不代表构建/测试或生产连接已通过。`--status` 查询可能建立只读 SSH。每次新发布必须用新 checkpoint；`--resume` 只恢复原批次且配置必须完全一致。

配置字段必需：`github_repo`、`host`、`remote_path`、`local_path`、`build_command`、`test_command`、`restart_command`、`health_url`、`health_keyword`。可选 `git_url`、`excludes`（仅安全单组件名称，无路径/glob）、健康重试次数/间隔、命令/事务超时，具体见模板。SSH host 只允许四个既有别名。`restart_command` 只接受单一 `systemctl [--user] restart 服务` 或 `docker/podman restart 容器`；shell 链与构建命令被拒绝。

发布快照不继承 node_modules：构建命令应先在本地快照中安装锁定依赖，再构建。已完成的构建/测试结果只有快照和源码指纹一致时才可复用。默认排除 `.git`、`node_modules`、`__pycache__`、`.pytest_cache`、`.remote-dev`、`.venv`、`venv`、`uploads`、`logs`、`.env`。用 `excludes` 扩展拉取/本地快照/上传排除；线上代码备份仍保留旧 release 的完整目录（不遍历 shared 软链接），所以首次迁移时必须先把大数据移入 shared，不能让生产 release 包含大数据。

## 默认 GitHub 私有版本管理（强制）

每个项目默认使用独立 GitHub **私有**仓库，源码的持久版本以 GitHub 为准；VPS 只保留发布物。本次修改 skill 不代表创建任何具体仓库。

1. 配置必须写 `github_repo: OWNER/REPO`。用 `gh repo view OWNER/REPO --json nameWithOwner,isPrivate` 核验名称和私有性；公开仓库拒绝，不能擅自修改其可见性。
2. 已有私有仓库配置匹配的无凭据 `git_url`，由 sync clone。仅 VPS 有源码时先 rsync 导入本地、建立 `.gitignore`，审核秘密与大数据，再初始化 Git、创建私有仓库、提交/push 基线。
3. 首次项目确定仓库名并审查上传范围后，通过 `terminal` 调用 `gh repo create OWNER/REPO --private`。创建后读回私有性；已有仓库只核验，不重建。权限不足或命名冲突停止，不降级公开或静默换账号。
4. 本地使用 `work/<task>` 分支，明确文件列表暂存，审查 staged diff 与凭据风险，再 commit/push；禁止盲目 `git add .` 和 force push。审查既有 GitHub Actions，不能让 push 触发自动生产部署绕过 deploy.sh。
5. **上线门槛：** local_path 是 Git 根、工作树干净、origin 与配置对应、GitHub 仓库真实为 private、当前分支已 push 且远端 SHA 等于 HEAD。上传源码必须被 Git 跟踪，不能让未跟踪的 ignored 文件混入发布快照。脚本在任何 VPS 写入前检查，不自动替用户 commit/push。
6. checkpoint 保存仓库、分支、commit SHA 与 release ID；本地构建产物属于该 commit 的结果，不要求写回源码仓库。构建后核对源码与 SHA 一致。
7. 成功上线后推送 `deploy/<host>/<release-id>` tag，指向 checkpoint 记录的 SHA，读回远端 tag 验证。tag 失败不回滚健康线上：报告“线上成功，版本归档待补”，同 checkpoint `--resume` 只补 tag，不重部署。失败发布不创建成功 tag，冲突 tag 不强行覆盖。
8. 紧急回滚仍用 rollback.sh，不在 VPS git checkout/git pull；GitHub 认证/网络故障不得阻断恢复旧 release。

### 认证与秘密

先加载 `github` skill。本环境已由用户在另一会话实测：GitHub 账号 `nexdoul`，凭据环境文件 `/home/hatch/.config/github/token.env`，权限 600；API 私有仓库创建及读回、管理/推送/读取权限均已确认。不要重复创建测试仓库或重新要求 token。后续 `terminal` 中先 `set -a; source /home/hatch/.config/github/token.env; set +a` 再调用 gh 或本 skill 的 shell 入口，确保变量导出给子进程；不要使用 `set -x`，不要读取/输出文件内容。Git HTTPS 命令用既有安全 helper（引擎按命令调用 `gh auth git-credential`），API 权限通过不等于每个仓库的 Git 操作都无需验收；首次实际项目仍核对该仓库读写和私有性。已保留测试仓库 `nexdoul/hermes-private-api-test-20261002-145328`，不自动删除。

使用既有 gh/安全凭据 helper；不得把 token 放入命令、URL、origin、YAML、日志或提交，不输出 secret，不使用 credential store 明文保存方案。VPS 不接收 GitHub token。

`.gitignore` 不是安全扫描：提交前必须检查生产 `.env`、证书/私钥、上传数据与自定义秘密文件。脚本已知秘密模式只能抓部分问题，私有仓库也不能存储真实凭据。

## 工作流及验收

1. **只读调查。** 用 `terminal` 做有界 SSH 查询，确认实际路径、current 链接、服务、磁盘余量和目标架构。不输出凭据。存在 Git 上游时核对上游与当前线上版本；不能把上游 HEAD 当作线上事实。完成条件：路径、服务、基线版本及 shared 内容已记录。
2. **拉取。** 调用 `scripts/sync.sh`。配置有可信 Git 仓库则优先在本地 clone；否则 rsync 远端代码至本地，排除 node_modules、uploads、日志、凭据和其他大目录。不能覆盖已有本地修改；续传只恢复未完成的拉取。完成条件：完整本地副本与基线/校验记录已落盘。
3. **本地开发。** 仅在 `local_path` 下编辑，按上文私有仓库纪律分支开发、审查、commit/push 并读回 SHA。建立构建和测试命令；本地无真实生产凭据时用隔离 fixture，不能伪造通过结果。完成条件：干净 commit 已推送至核验为私有的仓库，diff 可审核，构建测试实际通过。
4. **封装并发布。** 获得当前项目发布授权后用 `terminal` 调用 `scripts/deploy.sh`，它在本地执行配置中的构建与测试，校验将上传的产物；线上备份完成后才传输，上传到新 release 而不是 current。完成条件：脚本退出 0、结果 checkpoint 成功、current 指向该 release，HTTP 状态码与关键词均符合配置。
5. **失败处理。** 健康检查或应用重启失败，脚本恢复旧版本、重启并再次检查；非零退出、持久日志和 stderr 告警必须报告。回滚后不健康属于严重事故，不得说“已恢复”。完成条件：准确区分发布成功、自动回滚成功、恢复失败、状态未知。
6. **重启后恢复。** 先读 checkpoint 和日志，再调用脚本的恢复/状态入口，核对远端事务结果；不得因 SSH 断开就推断失败或重复切换。完成条件：恢复使用同一版本/事务，已完成构建阶段只有在指纹一致时才复用。

## 长任务纪律

通过 `terminal(background=true, notify=true)` 在本地跑有界构建/发布任务；日志和 checkpoint 写入持久目录。后台进程能抵御会话断线，**不能抵御容器重启**；重启后靠 checkpoint 重新执行命令，未完成的单次构建可能需重做。不要声称所有编译器都能从指令级续跑。

远端切换—重启—检查—恢复应作为有锁、有结果文件的独立轻量事务运行，避免沙箱死亡把线上留在一半。容器重启后的自动启动需要用户已有调度器或另行授权配置；本 skill 不修改任何现有 cron、网关或自愈链。

## 锁与恢复边界

上传中断保留远端 owner 锁，只允许原 checkpoint 恢复；不要开启新批次或手动抢锁。若配置变化、源码改变或远端基线冲突使原批次不可恢复，先只读审计 owner、current 和事务结果，再单独审批解除该项目锁。脚本不提供强制抢锁。远端事务在 SSH 断线后独立运行，但 VPS 自身重启或 SIGKILL 可能留下 `running` 状态，此时必须人工核对，不自动推断成功。

自动恢复优先切回未被修改的旧 release（和部署前备份对应）；备份另保留完整代码快照供灾难恢复。正常回滚用 `rollback.sh --release ID`；若旧 release 被人为破坏，不能把切回旧链接说成恢复成功。

## 限制与核验

- 软链接切换不是零停机保证；单进程服务重启仍可能短暂不可用。
- 代码备份不能回滚数据库、订单和上传内容；不把数据迁移塞进重启命令。
- 远端复制代码备份仍有 I/O 成本；排除 shared 大目录，事先核对余量，不能承诺“零开销”。
- 按目标架构/libc/runtime 制作发布物。不能在本地缺依赖时改为在生产机安装依赖。
- 成功必须由脚本结果和实际健康检查支持，不是“rsync 返回 0”。告警默认 stderr + 持久记录，不等于已推送飞书；Hermes 收到结果后在本聊天报告，失联窗口由既有监控负责。
- 隔离测试：`terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/test_remote_dev.py", timeout=180)`。测试不得连接真实 VPS、操作生产服务或修改系统配置。

## 参考思路

- [ssh-remote-dev](https://github.com/ana52070/claude-code-setup/blob/HEAD/skills/ssh-remote-dev/SKILL.md)：分层与 SSH 原子传输；**不采纳其远端编译、直接远端修改和 scp 降级**。
- [shunt](https://github.com/fever-wits/shunt)：checkout → 本地修改 → 带基线校验写回、持久任务结果；不安装其 Claude hooks，不全局路由 Bash。
- Capistrano / Deployer：releases + current 原子链接切换与可恢复发布。
