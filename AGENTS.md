
## Camofox 浏览器服务 (2026-09-27 部署)
- 本机 Camofox 反检测浏览器跑在 127.0.0.1:9377 (非 Docker, node server.js), 二进制在 ~/.cache/camoufox (152.0.4-beta.31)
- 自愈: /home/hatch/bin/camofox-start (flock→健康检查→拉起), hermes cron `camofox-selfheal` 每 5 分钟巡检, 失败细节看 ~/.camofox/logs/server.log, 健康时刻看同目录 .last_healthy 的 mtime (机制同 reverse-ssh watchdog)
- Hermes 侧: .env 的 CAMOFOX_URL + config browser.cloud_provider=camofox 已配; UBO 插件跳过 (CAMOFOX_DISABLE_DEFAULT_ADDONS=1)
- Camoufox 二进制来源: GitHub release font-bundle-v1 (8线程分块下载), 升级方式: 删 version.json 后跑 npx camoufox-js fetch
- 远程共用 GUI：Camofox VNC 插件 1600x900，noVNC `127.0.0.1:6080`，x11vnc `127.0.0.1:5900`，API `127.0.0.1:9377`（Bearer）。VPS 134 通过已有 `:2222` SSH 接入腿跑 `hermes-browser-forward.service`，本地端 `127.0.0.1:13081` → noVNC，Nginx `hermes-browser-muse.030.qzz.io` HTTPS + Basic Auth；凭据仅见 `/home/hatch/.camofox/browser-access.txt`（不要发群聊），Camofox 服务密钥仅在 `/home/hatch/.camofox/server.env` 与 Hermes `.env`。VPS 证书是 Cloudflare Origin Cert。自愈 cron 的脚本名必须 `camofox-start.sh`，无扩展名会被 Python 误执行；持久安装包在 `/home/hatch/camofox-browser/.vnc-stack/debs/`，启动脚本在重启后用 dpkg 恢复。固定 user_id `hermes-browser-user` / session_key `browser-main`，adopt_existing_tab=true；profile 数据保存在 `/home/hatch/.camofox/profiles/`。Hermes Camofox backend 的本地补丁（过期 tab 410 当 404 重建，`tools/browser_camofox.py`）已登记进 runtime 补丁自愈名单（bundle `camofox-tab-recreate`），重装会自动打回

## 浏览器信息采集栈 (2026-09-28 固化, 重启自愈)
- 位置 `/home/hatch/workspace/enhance/` (在持久盘上): `scripts/` (工具), `probe-profile/` (独立 Firefox profile, 勿与共享 Camoufox 9377 的 profile 混用), `venv/` (ddddocr 1.6.1 + patchright 1.63.0, 不动系统 Python), `data/`+`shots/` (采集产物), `logs/` (含 `.stack_healthy` mtime = 上次健康时刻), `CHROME-PATH-FINDINGS.md` (为什么不能用 Chromium)
- 自愈: hermes cron `browse-stack-selfheal` 每 5 分钟跑 `~/.hermes/scripts/browse-stack-start.sh` (flock→确保 Xvfb :92→修 NSSDB CA 信任→补软链→冒烟测试抓 example.org→touch .stack_healthy)。失败看 `enhance/logs/stack-selfheal.log`
- 人工入口 `bash ~/.hermes/scripts/browse.sh {serp|site|zhihu|weibo|doctor}`; `doctor` 是一键自检 (display/profile/CA/venv/数据面)
- 三个重启后必坏的根因及对策: ① /tmp 清空导致 Xvfb :92 消失 → ensure-display.sh 自举 (flock 防重入); ② NSSDB CA 信任丢失 → setup-profile.sh 重建; ③ ESM 模块解析以脚本所在目录为基准而非 cwd → `scripts/node_modules` 软链到 camofox-browser/node_modules

## 本机 HTTPS/证书/代理的坑 (2026-09-28 实测)
- 沙箱全部 HTTPS 走 MITM, CA 是 `Hatch Sandbox Egress CA` (O=Hatch), SPKI `gj9fWmp9hLUDU6c4P3km93fKceq1JJHx7GvqMav2wU8=`, 文件 `/home/hatch/.camofox/egress-ca.pem`
- egress 代理必须用主机名 `http://hatch-egress-proxy:3128`; 字面 IPv6 `[fd8b:4f84:7d32:99::1]` → `NS_ERROR_UNKNOWN_HOST`; `198.19.0.1:3128` 也可用。**环境变量 http_proxy 对 curl 生效但对 Firefox 不生效**, Playwright/camoufox-js 必须显式传 `proxy:{server,bypass}`
- Firefox profile 只有 import 了该 CA 且 trust=`CT,C,C` 才能开 HTTPS。trust 写成 `C,,` 只信 S/MIME 不信 SSL — 是踩过的坑
- certutil 的三个坑: ① nickname 含空格, 不能 `awk '{print $1}'`, 要从行尾 trust 反推切分; ② `certutil -L -n <nick>` 输出人读文本不是 PEM, 必须加 `-a` 才能喂 openssl; ③ camoufox 会自动导成 `<CN> - Hatch`, 与裸 CN 导入会变成两条, 判据要用指纹匹配而非 nickname 匹配 (见 `scripts/ca-trusted.sh`)
- `~/.pki/nssdb` 与 `/etc/pki/nssdb` 是只读 tmpfs, 改不了; Chromium 因此无法信任本地 CA, 但即便 `--ignore-certificate-errors-spki-list` 也仍一律 `net::ERR_EMPTY_RESPONSE` — Chromium 路线整体不可用, 只用 Camoufox/Firefox
- Chrome 错误页会套用目标站名做 title (example.org 报错页 title 也是 example.org), 判断页面真假必须看 body 不能看 title
- 知乎 `/hot`、`/billboard` 是手机号+短信验证码登录墙 (非图形验证码, ddddocr 不适用); 可用未登录入口 `explore`、`zhuanlan.zhihu.com`、`topic/<id>/hot`; 专栏详情/问题页未登录会 403
- 微博 `s.weibo.com/top/summary` 热搜与 `weibo?q=` 搜索均无验证码可直接抓

## Hermes runtime 本地补丁自愈 (2026-09-28 固化)
- Hermes 的自愈链独立于 guardian（guardian 的 restore-all.sh 刻意跳过 Hermes，会下 official latest 与钉版本冲突）；唯一入口 `/home/hatch/bin/hermes-start`，被 hermes-selfheal cron 每 5 分钟调
- 本地 runtime 改动登记: 清单 `~/.hermes/runtime-local-patches.list` + 补丁包 `~/.hermes/patches/<bundle>/{*.patch,files,meta}` (meta 记 TARGET_COMMIT)；都在 HERMES_HOME 下，重装不丢
- 重新生成补丁: `bash ~/.hermes/scripts/runtime-patch-snapshot.sh`（会把没登记的 dirty 文件自动收进 `_unassigned/` 并 WARN，正确结果是零 WARN）
- hermes-start 的 `apply_runtime_local_patches` 在重装/rebuild 后自动 git apply；幂等靠 `git apply --check`（已应用则 --check 失败跳过）。`TARGET_COMMIT != HEAD` 的 bundle 整体 skipped，需在新 commit 上重新快照；`failed>0` 则 hermes-start 故意 fail
- **2026-09-28 实战验证**: 人为清空 runtime 本地改动后，约 3 分钟内 hermes-selfheal cron 自愈打回全部 33 个补丁，applied=33 failed=0，心跳终态功能 15/15 测试通过
- 已登记 6 个 bundle: heartbeat-terminal-stamp / gateway-i18n-zh / locale-i18n-zh / local-relay-fastmode / camofox-tab-recreate / feishu-adapter-local
- 详细流程见 skill `hermes-runtime-local-patches`；宿主机三层托管图见该 skill 的 `references/self-heal-entry-points.md`
- 改 runtime 源码必须当场登记（否则下次重装静默丢失）；能在 `~/.hermes/config.yaml` 表达的一律用配置（provider/model.aliases/reasoning_effort 天然抗重装）
- **加自愈前先分类**：`bash ~/.hermes/scripts/persistence-triage.sh`（只读，退出码 3=有冗余待清理）。四类判定：`[P]` 已在 `~/` 永久区→绝不接自愈；`[H]` 随沙盒消失→必须接且要指明 owner；`[M]` 在 /tmp 但搬过去就永久→搬家而非自愈（例外：lock 必须留 /tmp，持久的 stale lock 会把自愈永久卡死）；`[R]` 已有自愈但其目标其实不用治→删
- **用户说「自愈分析」= 一把做完**（用户选的宽档，2026-09-28）：跑 triage → 把 [M] 搬掉、[R] 删掉、未登记的补丁登记上 → 重跑 triage 证明退出码 0 才收工；不要只出报告就回来问怎么办
- 当前 `[R]` 待清理 2 项（均已用 md5 判定保留哪份）：`bin/camofox-start` 与 `bin/muse-browser-start.sh` 是 `.hermes/scripts/` 下同名脚本的重复副本，cron 指向 `.sh` 那份，删 bin/ 前先把所有引用它的绝对路径改掉


## 自愈链的锁泄漏坑 (2026-09-28 实测, 最隐蔽的自愈失效原因)
- **症状**: cron 显示 "ok", 日志却是连续十几行 `another selfheal run in progress, exiting`, `.stack_healthy` 的 mtime 停在地久前不动 —— 自愈实际已死, 但表面看不出
- **根因**: daemon 继承上游脚本的 flock FD。本例中 `browse-stack-start.sh` 用 `exec 9>lock` 加锁, 调 `ensure-display.sh` 起 Xvfb 时没关 FD 9, 结果 Xvfb daemon 永久持有 `/tmp/browse-stack-start.lock` (实测 `ls -l /proc/<pid>/fd | grep lock` 看到 fd 8/9 指向两把锁), 之后每次自愈都拿不到锁直接空转
- **修法**: ① 起 daemon 时显式关掉继承 FD —— bash 用 `setsid cmd ... 8>&- 9>&- &`; `flock` 包装用 `-o/--close`; ② 给自愈脚本加活性保底: 拿不到锁时用 `fuser <lock>` 找持有者, 若其 `/proc/<pid>/cmdline` 不含本脚本名就判为泄漏并抢锁继续, 而不是永久退出
- **同类历史**: muse-browser-start.sh 的 flock 泄漏 (2026-09-27) 是同一个 bug 的另一次实例; `flock` 起 daemon 一律显式关 FD, 没有例外
- **诊断口诀**: 自愈"看起来在跑但状态不更新"时, 先 `ls -l /proc/*/fd | grep <lockfile>` 看谁持有锁, 再比对 `.stack_healthy`/`.last_healthy` 的 mtime; 两者时间差越大, 锁泄漏越可能

## 自愈链的第二个锁坑: execSync 里跑带 `&` 的命令 (2026-09-28 实测)
- **症状**: 自愈日志 `ERROR smoke test failed: ` (错误信息为空), 手动跑 probe-site.mjs 零输出且永不返回 (timeout 124)
- **根因**: `execSync("flock -n lock Xvfb :92 ... &")` —— `&` 绑到整个 AND-list, 子 shell 留在前台等 daemon 死等, execSync 永久阻塞。与 AGENTS.md 里 muse 那次是同一个 bash 绑定坑的 Node 版本
- **修法**: Node 里起 daemon 一律用 `spawn(\x27setsid\x27, [...], {detached:true, stdio:[\x27ignore\x27,\x27ignore\x27,\x27ignore\x27]}) + child.unref()`; stdio 全 ignore 顺带关掉继承 FD, 不会再泄漏锁
- **第二个坑**: `fuser <lock>` 输出多个 PID 时空格分隔, 用 `tr -d \x27 \x27` 会把它们粘成一个巨大数字 (`pid=5357353636536375...`), `/proc/<垃圾>` 读不到 -> 误判"泄漏" -> 抢锁时上游正在收尾 -> `ERROR 抢锁失败` 把一次正常并发挡掉。必须 `for h in $holders` 逐 PID 判定, 且抢不到锁时让路 (exit 0) 而不是 ERROR 退出

## 「再次尝试」= 反复重启验证 (2026-09-28 用户语义)
- 用户说"再次尝试"时, 上一轮的"单次通过"不算数 —— 要跑多轮 kill→自愈循环 (实测三轮, 每轮 kill Xvfb :92 + 清 /tmp/.X92-lock, 再跑自愈)
- 每轮必须看两个数: selfheal exit=0 且日志新增一条 `smoke test OK`; 只看 `.stack_healthy` mtime 会漏掉"跑了但实际失败"
- 验证用的 kill 脚本不能内联 pkill -f (会自杀), 也不能把 pattern 写进会被匹配的命令行; 用 `pgrep -x Xvfb` + 读 /proc/PID/cmdline 精确判断

## 自愈有效性判据 + SEC_ERROR_UNKNOWN 已排除项 (2026-09-28 实测)
### 判据: exit=0 不等于成功
- `browse-stack-selfheal` 的健康路径是**刻意静默**的 (只 `touch .stack_healthy`, 不写日志), 所以 `stack-selfheal.log` 几小时无新增**不代表没跑**; 判据是 `.stack_healthy` 的 **mtime** 前进
- 完整判据必须三条同时满足: ① cron/手动跑 exit=0; ② 日志新增一条 `smoke test OK`; ③ `.stack_healthy` mtime 前移到当前时刻。只有 exit=0 会把"跑了但实际失败"误判成健康
- 只有故障/修复事件才写日志, 所以"日志有 ERROR + mtime 停住"= 真死了; "日志干净 + mtime 停住"= 检查一下是不是锁泄漏 (见上面锁坑两节)

### SEC_ERROR_UNKNOWN: 根因未确认, 已排除八项 (2026-09-28 08:45–09:02)
- **现象**: cron `browse-stack-selfheal` 09:02 前连续两次 `ERROR smoke test failed: SEC_ERROR_UNKNOWN`; 同 URL 手动跑 `probe-site.mjs` 同样报错, 09:02 后恢复 200
- **已排除 (不要重做这些实验)**:
  1. CA 文件与 profile 指纹不一致 → 实测 `91:40:C7:DB…` 一致
  2. trust 标志写成 `C,,` → 实测 `CT,C,C` 正确
  3. `ca-trusted.sh` 本身失效 → 实测 exit 0
  4. 出口网络/代理挂 → curl 走 `hatch-egress-proxy:3128` 同时段 200
  5. 共享 Camoufox (9377) 同时段故障 → `~/.camofox/logs/server.log` 该窗口零 error
  6. cron 环境 `HOME=/root` 导致 binary/配置错位 → `env -i HOME=/root` 复现得到的是 *binary missing*, 不是 SEC_ERROR
  7. **profile 内容损坏 → 已证伪**: 被标为 `probe-profile.corrupt-*` 的备份**单独跑同样 200 通**; 即"换 profile 后恢复"是时间变量不是内容变量。**教训: 换掉某物后故障消失, 不等于该物坏了** —— 时间变量极易冒充因果
  8. 另一实例并发锁住 profile → PID 10589 持 `probe-profile` 的 fd 数 = **0**, 没共用
- **当前定性**: 瞬时故障, 根因未定位; 自愈**未**为此新增自动重建 profile 分支 (假设被实验推翻后已整段回退, 不给自愈治不存在的病)
- **下次复现时的固定动作**: SEC_ERROR 出现的**同一分钟**立刻手动跑一次 probe。手动也失败 + curl 通 → 锁定 Firefox 侧; 手动秒过 → 偶发/代理侧, 记时间戳等下次
- **教训**: 定位不确定的瞬时故障不要硬改自愈; 假设被自己的实验推翻就回退, 别留在代码里

## 任务级自愈：task registry（2026-10-01 建立）

**为什么需要**：原有自愈链（javdb-stack / chain-watchdog / camofox / browse-stack）全部是**服务级**巡检——判健康看端口、进程在看不在。一次性有状态的长任务（retitle、ingest、backfill）中断后**没有任何链负责拉起**：`javdb-chain-watchdog.sh` 读完两个 marker 就 `exit 0` 空转，对新任务一无所知。症状是"晚上被打断就静默停摆，每次看日志都是 ok"。

**架构**（三件，全部在 `~/.hermes/scripts/`）：
- `taskctl.sh` — 任务登记表：`create <id> --script <path> [--max-attempts N]` / `list` / `show` / `stop` / `resume` / `reset`
- `task-run.sh <id>` — **唯一**允许的启动方式。payload 是它的子进程，只有它能观察退出码并写标记
- `task-watchdog.sh` — 扫 `~/.hermes/state/tasks/*`，拉起"wrapper 已死且状态非终态"的任务。hermes cron `task-watchdog` 每 15 分钟跑（`no_agent=true`，纯脚本不烧 LLM）

**状态机**：`pending` / `running` / `done` / `stopped` / `exhausted`。`done`=payload 退出码 0（**就是"已完成"标记**）；`stopped`=人工叫停；`exhausted`=attempts 用尽。后三者 watchdog 绝不拉起。

**核心设计**：完成标记**不靠 agent 记性**。忘记写/写一半被杀/没执行到 → 无 `done` → watchdog 判"被打断"重新拉起（安全那一侧）。唯一残留风险是 payload 死了而 wrapper 没死，所以 `done` 的判据只有一条：payload 真跑完且退出码 0。

**用户红线（不可违反）**：不能确保 `已完成` 标记可靠，就不得做永久自动拉起。

**已验证（2026-10-01）**：A 多次失败→exhausted 后拒绝运行；B 成功→done 且拒重跑；C stop 阻止/resume 恢复；D **杀进程组后 watchdog 自动换 PID 拉起、心跳继续**；E done/stopped/exhausted 三者 watchdog 完全不碰。测试抓到 3 个真 bug 后修复才跑绿。

**坑**：`taskctl create` 的 `run.sh` 是**shim**（`exec bash <原路径>`），不是拷贝内容——否则 agent 改原脚本不生效，且 `bash run.sh` 报 126。
