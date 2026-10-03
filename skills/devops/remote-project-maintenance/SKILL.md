---
name: remote-project-maintenance
description: Use when editing code or services on a remote SSH host.
version: 1.0.0
author: hermes-agent
license: MIT
metadata:
  hermes:
    tags: [ssh, remote, systemd, patch-loop, venv]
    related_skills: [web-ui-rebuild, camofox-selfheal-deploy]
---

# Remote project maintenance

## When to Use

Any task that edits code, databases, configs, or services on a host reachable only via an SSH alias — including read-only surveys, patch passes, test runs, and service restarts.

For projects that live on a host reached only through an SSH alias (e.g. `ssh krvps`), where local file tools cannot see the paths.

## Always-on rules

- **默认本地优先，禁止直接编辑线上 docroot。** 先将项目拉到 `/home/hatch` 下的持久工作副本；`read_file`、`write_file`、`patch` 只操作本地副本，依赖安装、构建、测试与 agent 全在沙箱运行。VPS 只做有界只读调查、接收产物、备份、切换链接、重启指定应用和健康检查；不得在生产机运行构建或测试套件。
- **发布必须通过项目的 deploy.sh。** 禁止手动 scp 零散代码上线；使用配置驱动的 releases/current/shared 布局，传输前创建时间戳备份，保留最近五份，失败自动恢复并复查 HTTP 状态码与关键词。krvps 生产发布须获该次授权；不得碰 104 反向隧道及巡检。实现与验证细节见 `references/local-first-atomic-release.md`。
- **Snapshot before a risky pass:** `cp -a` the files you will touch into a dated backup dir, and make a baseline git commit when the repo has none — every later diff must be revertable.
- **Never restart a worker service inside its active work window.** Check state + recent logs first, tell the user what the restart interrupts, restart between windows.
- **Every step ends with a command whose expected output is pre-written.** Verify with real output (exit code + log lines + test count), never with narration.
- **Credentials in configs are context only.** Never echo values into chat, plans, or commits; redact before quoting a config dump.
- **Plan-mode deliverables go in the local active workspace at `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md`; when the project itself is remote, also scp the plan into the remote project dir so whoever implements on that host has it.**
- **本地 patch 后核对唯一性。** 用 `search_files` 检查新增符号及调用点，避免部分成功后重复应用留下重复定义；重做时先保存本地差异，再修正唯一 anchor，不用覆盖式 Git 恢复丢弃未提交修改。
- **Async client libraries must be constructed inside a running event loop.** `pyrogram.Client.__init__` calls the deprecated `asyncio.get_event_loop()`, which raises "There is no current event loop" in a waitress/gunicorn worker thread on Python 3.12 — build the client inside a coroutine and `asyncio.run` that, never the constructor directly. See `references/telegram-pyrogram-pitfalls.md` for the rest of this class.
- **Run the formatter/linter only on files you changed.** Formatting the whole remote tree rewrites pre-existing unformatted files and buries your diff in noise: `gofmt -l <changed files>` (or the language equivalent) and fix only your own.
- **Check whether a global ignore pattern eats your evidence before promising it as a deliverable.** A repo-level `*.log` (or `*.sqlite`, `*.bak`) ignore silently converts “evidence committed” into “evidence only on disk”; decide up front whether evidence is force-added, given a non-matching extension, or lives in `README.md` / a reports dir — and state which in the final report.
- **Re-check `git log` / `git status` immediately before every commit on a shared remote.** Another executor or reviewer may have committed your slice, left a half-applied file, or edited a sibling source file; committing blind either duplicates work or ships someone else's in-flight state. Confirm the file you are about to commit is the one on disk and that no one else has already landed it.

## 本地修改与受控发布

1. 用 `terminal` 做有界只读 SSH 调查，记录线上版本、目录、服务与 shared 数据；凭据不进入输出。
2. 有可信 Git 上游时优先本地 clone，否则 rsync 拉取代码，排除依赖、上传、日志和凭据。已有非空工作副本拒绝覆盖，拉取与发布使用不同 checkpoint。
3. 在持久本地副本使用 `read_file`、`patch`、`write_file` 修改；以下 anchor 示例仅在本地运行，不上传 patcher 修改线上文件。
4. 在本地验证快照执行构建和完整测试，记录真实退出码、日志、源码及产物指纹。
5. 审核差异和应用重启范围，获得发布授权后通过 deploy.sh 上线；失败必须区分自动恢复成功、恢复失败与状态未知。

Patcher shape — exact-bytes anchor, idempotent, never silently no-ops:

```python
#!/usr/bin/env python3
import pathlib, sys
p = pathlib.Path("/root/code/<project>/file.py")
src = p.read_text(encoding="utf-8")
ANCHOR = "exact bytes from disk"
NEW = "replacement"
if NEW in src:
    print("SKIPPED"); sys.exit(0)
if ANCHOR not in src:
    print("ANCHOR NOT FOUND"); sys.exit(1)
p.write_text(src.replace(ANCHOR, NEW, 1), encoding="utf-8")
print("PATCHED")
```

**Guard on the exact marker the patch adds.** A guard like `if "MyComponent" in src` is satisfied by the *import* line an earlier patcher added, so the wiring patch prints SKIPPED and silently does nothing. Guard on the text this patch actually inserts (the call site, the new function body) and make the guard stricter the more often the same file is edited.

**Anchor mismatch:** when a replace no-ops or the script reports the anchor missing, the on-disk bytes differ from the eyeballed text (CRLF, trailing whitespace, smart quotes). Dump the real bytes over ssh (`sed -n 'a,bp' file | cat -A`, or `od -An -tx1` for a short span) and anchor on those. Two mangled guesses in a row means read the bytes first, not retry.

## Survey before planning (read-only, in order)

1. `ssh <alias> "systemctl --user list-units --type=service | grep <proj>"` — what is actually running
2. `wc -l` the large files; `du -sh` the project — a huge log/archive file is usually the first win
3. `git log --oneline | head; git status --short` — 0 commits + everything untracked means build hygiene before features
4. 拉取后在本地副本运行基线测试，记录测试数和失败原因；不在生产 VPS 跑测试套件
5. Grep for the real defect patterns (`except Exception`, `setInterval`, per-request subprocess forks, polling) before theorising about fixes
6. Sample the real data — row counts, biggest payload bytes, status distribution. Size any UI/API plan by measured numbers, never by screenshots of the old UI.

## Tests on a project venv

Project venvs are often minimal (no pytest, ruff, or pip). Run:

```
terminal(command="./.venv/bin/python -m unittest discover -s tests -p 'test_*.py'", workdir="<本地项目目录>")
```

An error like `async def functions are not natively supported` means the venv lacks pytest-asyncio — convert those tests to plain `unittest`; do not try to install packages into it.

## Restart discipline (systemd --user)

发布时由 deploy.sh 执行配置中的单应用重启与健康检查，禁止手动重启绕过发布事务。以下命令只用于用户明确授权的独立服务运维，不适用于代码上线：

```
ssh <alias> "systemctl --user restart <unit> && sleep 10 && systemctl --user is-active <unit> && journalctl --user -u <unit> --no-pager --since '-2min' | tail -20"
```

Expected: `active`, then log lines showing the service's real startup steps (login → warm-up → control loop) and **zero ERROR lines**. Add a health-endpoint check when the service exposes one. Restart the read-only/web tier before the worker tier so the console stays reachable while the worker recycles.

## Proving a change end-to-end without waiting for production

在本地隔离实例驱动修改后的函数，断言可观察副作用（fixture 数据、mock 调用、日志），不要在生产机运行功能测试。部署后仅进行有界、非破坏的服务与 HTTP 健康检查；本地功能测试与线上健康检查分别报告，不能相互替代。

**When the changed path is an HTTP endpoint, drive it with real HTTP against the bound port, not a Flask `test_client`** — a test client running under an outer event loop cannot host `asyncio.run()` inside a handler, and the failure looks like an app bug. Authenticate by minting a session cookie with the app's own serializer — `app.session_interface.get_signing_serializer(app).dumps(dict(session))` inside `app.test_request_context()` — never a hand-rolled itsdangerous dump with a guessed salt (rejected silently, you just see a 302 to login). A 405 on a GET probe is what proves a POST-only route exists; a 200 that is really login HTML proves nothing.
