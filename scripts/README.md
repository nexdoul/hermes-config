# hermes-config scripts（纯净版）

从 `hermes-config` 仓库的 `scripts/` 复制的**剥离版**。原文件未改动，仍在
`hermes-config/scripts/` 下按本机路径运行；本目录是给外部使用的版本。

## 三层分类

按可移植性分三档，**不是所有脚本都通用**：

| 目录 | 内容 | 通用性 |
|---|---|---|
| `browser/` | 反检测浏览器栈的启停、自愈、健康检查（camofox / camoufox / Xvfb / Firefox profile） | **已参数化**，去掉 `/home/hatch` 后结构不变，改环境变量即可在别处跑 |
| 根目录 `*.sh` | 网关重启与看门狗：`gateway-restart-manual.sh`、`gw-relaunch-long.sh`、`scheduled-restart.sh` | **半通用**。Hermes 网关本身是通用的，但重启策略、等待时长、日志路径都是按本机运维习惯定的，需按你的环境改 |
| `common-site/` | javdb → 115 这条业务链的自愈（systemd unit 重建、mihomo 路由、115 隧道、下载硬停） | **本机专属**。绑定 `/home/hatch/code/javdb`、`/etc/systemd` 重建、115driver 二进制与账号。仅作「如何给一条链写自愈」的参考，搬不走 |

## browser/ 的环境约定

所有路径都有默认值并可用环境变量覆盖：

```bash
CAMOFOX_APP_DIR      camoufox-browser 源码目录      默认 ~/camofox-browser
CAMOFOX_STATE_DIR    运行状态目录                    默认 ~/.camofox
CAMOUFOX_BIN         camoufox 可执行文件            默认 $XDG_CACHE_HOME/camoufox/camoufox-bin
EGRESS_CA            出口 CA 证书（PEM）            默认 $CAMOFOX_STATE_DIR/egress-ca.pem
EGRESS_PROXY         出口代理，形如 http://host:3128
BROWSE_STACK_ROOT    Firefox profile / 日志 / 截图  默认 ~/.cache/browse-stack
BROWSE_PROFILE       Firefox profile 目录           默认 $BROWSE_STACK_ROOT/probe-profile
BROWSE_DISPLAY       Xvfb 显示号                    默认 92
```

### 运行前提

这些脚本解决的是**沙箱/容器化环境**下的具体问题，换了环境问题本身可能不存在：

- **`/tmp` 会在重启时清空**，Xvfb 随之消失 → `ensure-display.sh` 负责自举（flock 防重入 + 关闭继承 FD，否则 daemon 会永久持有上游的锁把后续自愈全部卡死）
- **HTTPS 走 MITM 代理** → Firefox 必须把 CA 导入 profile 且 trust 必须是 `CT,C,C`（写成 `C,,` 只信 S/MIME 不信 TLS，是常见错）
- **`http_proxy` 环境变量对 curl 生效但对 Firefox 不生效** → 必须显式传 `proxy.server`
- **不要用 Chromium** → 该配置下 Chromium 一律 `net::ERR_EMPTY_RESPONSE`，只能走 Firefox/camoufox

其中 MITM 代理与 CA 是沙箱特有：如果你的环境直连公网，`EGRESS_PROXY` 留空即可，
`ca-trusted.sh` / `setup-profile.sh` 会因找不到 CA 而失败，属预期。

### 冒烟判据（搬去别处也要守住）

`browse-stack-start.sh` 判健康不只看退出码，要三条同时满足：

1. 脚本 exit=0
2. 日志新增 `smoke test OK`
3. `.stack_healthy` 的 mtime 前进

健康路径**刻意静默**（只 touch marker、不写日志），所以「几小时没新日志」不代表没在跑——
看 mtime。这是自愈链的通用判据，不是浏览器栈专属。

## common-site/ 与根目录脚本

维持原样未参数化。它们要么绑定本机绝对路径，要么承载本机运维策略，
强行参数化只会制造「看起来能跑、实际跑不通」的假象。保留是为了让读代码的人看到：

- 如何给一条链写自愈（javdb 那份是最完整的例子：重建 /etc → 起隧道 → 探端口 → 冒烟真账号）
- 网关重启的正确姿势（先看有没有长任务在跑，否则会撞上 drain 上限）
- 「自愈必须能区分真失败和还没跑完」

## 不含

任何凭据、`.env`、token、密钥。
