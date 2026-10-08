// 自举式浏览器访问探针 (重启自愈, 不依赖外部 Xvfb / 环境变量)
//
// 用法: node probe-site.mjs <url> [url2 ...]
//
// 设计要点 (本机特有, 缺一不可):
//   1. 自己确保 DISPLAY 存在: 先探测目标 Xvfb, 不在就自己拉一个 (flock 保护, 不重复起)
//      —— 否则重启后报 "cannot open display: :92"
//   2. 若环境要求代理, 必须显式传入 (EGRESS_PROXY), 环境变量对 Firefox 无效
//      —— 环境变量对 curl 生效但对 Firefox 不生效, 不写就全网超时
//   3. profile 必须已导入 egress CA (trust=CT,C,C), 否则全部 HTTPS 失败
//   4. 不要用 Chromium —— 本机 Chrome 经该代理一律 net::ERR_EMPTY_RESPONSE
//      (完整诊断见 docs/CHROME-PATH-FINDINGS.md)
//   5. 依赖 camofox-browser 的 node_modules: 必须 cd 到 camofox-browser
//      再执行, 否则 playwright-core / camoufox-js 解析不到 (ERR_MODULE_NOT_FOUND)
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';

// 保障模块解析 (必须在 import 业务包之前): 若不在 camofox-browser 目录,
// 用它的 node_modules 重新执行自己, 否则 playwright-core/camoufox-js 解析不到
const APP = process.env.CAMOFOX_APP_DIR || (process.env.HOME + '/camofox-browser');
if (process.cwd() !== APP) {
  const { spawnSync } = await import('node:child_process');
  const r = spawnSync(process.execPath, [import.meta.filename, ...process.argv.slice(2)], {
    cwd: APP, stdio: 'inherit', env: process.env,
  });
  process.exit(r.status ?? 1);
}
const { firefox } = await import('playwright-core');
const { launchOptions } = await import('camoufox-js');

const DISPLAY_NUM = process.env.BROWSE_DISPLAY || '92';
const DISPLAY = ':' + DISPLAY_NUM;
const PROFILE = process.env.BROWSE_PROFILE || (process.env.HOME + '/.cache/browse-stack/probe-profile');
const SHOTS = (process.env.BROWSE_STACK_ROOT || (process.env.HOME + '/.cache/browse-stack')) + '/shots';
const PROXY = process.env.EGRESS_PROXY || '';   // 空=直连
const LOG = (process.env.BROWSE_STACK_ROOT || (process.env.HOME + '/.cache/browse-stack')) + '/logs';
mkdirSync(SHOTS, { recursive: true });
mkdirSync(LOG, { recursive: true });

const sh = (cmd) => execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();

// --- 1. 确保 Xvfb 在 (自举) ---
function displayAlive() {
  try {
    const out = sh(`DISPLAY=${DISPLAY} xdpyinfo -display ${DISPLAY} 2>/dev/null | head -1 || true`);
    return out.length > 0;
  } catch {
    return false;
  }
}
if (!displayAlive()) {
  // **不要把带 `&` 的命令交给 execSync** —— `&` 会绑到整个 AND-list,
  // 子 shell 留在前台等 daemon, execSync 永久阻塞 (实测 timeout 124, 零输出,
  // 自愈的冒烟测试就是这样被挂死成 "ERROR smoke test failed: 空")。
  // 改用显式 detached spawn, 并关掉所有继承 FD, 避免 daemon 反手持有上游的锁。
  const { spawn } = await import('node:child_process');
  const child = spawn('setsid', [
    'Xvfb', DISPLAY, '-screen', '0', '1600x950x24', '-ac', '-nolisten', 'tcp',
  ], {
    detached: true,
    stdio: ['ignore', 'ignore', 'ignore'],
    env: process.env,
  });
  child.unref();
  for (let i = 0; i < 40 && !displayAlive(); i++) {
    execSync('sleep 0.5', { stdio: 'ignore' });
  }
  if (!displayAlive()) {
    console.error(JSON.stringify({ fatal: `Xvfb ${DISPLAY} unavailable` }));
    process.exit(1);
  }
}
process.env.DISPLAY = DISPLAY;

// --- 2. 启动 Camoufox (显式代理) ---
const opts = await launchOptions({
  executable_path: process.env.CAMOUFOX_BIN || ((process.env.XDG_CACHE_HOME || (process.env.HOME + '/.cache')) + '/camoufox/camoufox-bin'),
  headless: false,
  virtual_display: DISPLAY,
  exclude_addons: ['UBO'],
  enable_cache: true,
  locale: 'zh-CN',
  os: 'linux',
  humanize: true,
  proxy: { server: PROXY, bypass: '127.0.0.1,localhost' },
  // 证书不弱化: 靠 profile 里的 egress CA 信任
});
opts.env = { ...opts.env, DISPLAY, http_proxy: PROXY, https_proxy: PROXY };
opts.viewport = null;
if (!existsSync(PROFILE + '/cert9.db')) {
  console.error(JSON.stringify({ fatal: 'profile missing NSSDB; run: certutil -A -n hatch-egress -t CT,C,C -i ' + (process.env.EGRESS_CA || (process.env.HOME + '/.camofox/egress-ca.pem')) + ' -d sql:' + PROFILE }));
  process.exit(1);
}

const context = await firefox.launchPersistentContext(PROFILE, opts);
const page = context.pages()[0] || await context.newPage();

const results = [];
for (const url of process.argv.slice(2)) {
  const t0 = Date.now();
  let item = { url, startedAt: new Date().toISOString(), display: DISPLAY, proxy: PROXY };
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    item.status = resp?.status();
    await page.waitForTimeout(2500);
    item.finalUrl = page.url();
    item.title = await page.title();
    const dims = await page.evaluate(() => ({
      captcha: /captcha|验证码|recaptcha|hCaptcha|turnstile|challenge|安全验证/i.test(document.body?.innerText?.slice(0, 4000) || ''),
      bodyLen: document.body?.innerText?.length || 0,
      text: (document.body?.innerText || '').slice(0, 600),
      iframes: [...document.querySelectorAll('iframe')].map(f => f.src).slice(0, 10),
    }));
    item = { ...item, ...dims };
    const shot = `${SHOTS}/${url.replace(/[^a-zA-Z0-9]/g, '_').slice(0, 80)}_${Date.now()}.png`;
    await page.screenshot({ path: shot });
    item.shot = shot;
  } catch (e) {
    item.error = String(e.message).slice(0, 200);
  }
  item.ms = Date.now() - t0;
  results.push(item);
  console.log(JSON.stringify(item));
}
await context.close();
