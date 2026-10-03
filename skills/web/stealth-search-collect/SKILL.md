---
name: stealth-search-collect
description: "Use when collecting search results from Google/Bing or driving the local anti-detection browser. Covers Camoufox launch, sandbox CA trust, and empty-shell Bing fixes."
version: 1.0.0
---

# Stealth Browser Search Collection

Proven workflow on htch-runtime (2026-09-27) for crawling Google/Bing with the local Camoufox anti-detection browser. Covers launching Camoufox directly, trust for the sandbox MITM CA, and the Bing empty-shell symptom.

## Launch (correct incantation)

```js
import { firefox } from 'playwright-core';
import { launchOptions } from 'camoufox-js';

const opts = await launchOptions({
  executable_path: '/home/hatch/.cache/camoufox/camoufox-bin',
  headless: false,
  virtual_display: process.env.DISPLAY,   // e.g. ':92'
  exclude_addons: ['UBO'],
  enable_cache: true,
  locale: 'zh-CN', os: 'linux', humanize: true,
});
opts.env = { ...opts.env, DISPLAY: process.env.DISPLAY };
opts.viewport = null;
const context = await firefox.launchPersistentContext(profileDir, opts);
```

- Run the script from `/home/hatch/camofox-browser` (needs its `node_modules`), or imports fail with `ERR_MODULE_NOT_FOUND`.
- Env: `CAMOFOX_DISABLE_DEFAULT_ADDONS=1` (UBO addon download fails on this host and aborts launch).
- One dedicated Xvfb per task (`Xvfb :92 -screen 0 1600x950x24 -ac -nolisten tcp -noreset`); never reuse `:91`.

## Sandbox CA must be re-trusted in every NEW profile

A fresh `launchPersistentContext` profile ships the egress CA with trust flags `,,` → **every HTTPS page fails with `SEC_ERROR_UNKNOWN`**, even though `/home/hatch/.cache/camoufox/distribution/policies.json` lists `Certificates.Install`. Fix once per new profile, before the first navigation:

```bash
certutil -A -n 'Hatch Sandbox Egress CA - Hatch' -t 'CT,C,C' \
  -i /home/hatch/.camofox/egress-ca.pem -d sql:<profileDir>
```

Verify with `certutil -L -d sql:<profileDir>` → must show `CT,C,C` (not `,,`). A profile that already ran under a live browser carries the right flags; a jailed cert only bites brand-new profiles. If a page still fails with `SEC_ERROR_UNKNOWN` after this, check no stale camoufox process still holds the profile open.

## Bing empty-shell (not a captcha)

`www.bing.com/search?...` can return HTTP 200 with a title that looks fine but an almost empty body (`bodyLen ~33-105`, no `li.b_algo`). Symptoms: framework renders (logo, search box, tabs) but zero results, no loading state, no captcha.

- **Not a captcha — it is a shell.** Do not report it as blocked.
- Workaround that works: retry navigation (the first goto often shells), or re-run the same query — subsequent loads return real `li.b_algo` results. Adding `setlang=en&mkt=en-US` keeps the page in international mode; without them a Chinese-market shell with 国内版/国际版 appears.
- Parse with `li.b_algo` → `h2` (title), `h2 a` (href), `.b_caption p` (snippet).

## Google

Works directly with this setup: `https://www.google.com/search?q=...&hl=en&num=20` returns real SERPs including AI Overview. A regex captcha check over the first 3000 chars can false-positive on pages that merely *mention* captcha — confirm with a screenshot before reporting a block.
- Parse: `a:has(h3)` for results, `[data-attrid="wa:/description"]` for AI Overview.
- Google wraps result links in `/goto?url=` redirects; Bing in `ck/a?...&u=a1<base64url>` — decode Bing's with base64url before treating it as the real URL.

## Connectivity facts on this host

- All egress is a MITM proxy (`hatch-egress-proxy`, IPv6 `[fd8b:4f84:7d32:99::1]:3128`, IPv4 `198.19.0.1:3128`); `GET https://muse.ai/` with a `Cookie:` header hangs indefinitely, without it answers instantly — an odd host quirk, not a browser bug.
- Curl check for reachability: a HEAD/GET without cookies. A 404/302 is still a *successful* connectivity probe.
- `zhuanlan.zhihu.com` returns 200; `www.zhihu.com` redirects (302) to login; `weibo.com` redirects to visitor passport; `m.weibo.cn` times out. Login walls are site policy, not captcha.
