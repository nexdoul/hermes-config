---
name: browser-signup-automation
version: 1.0.0
description: "Use when automating site registration in the local browser."
---

# Browser Signup / Registration Automation

Use when driving the local Camoufox browser through a multi-step **account creation** flow (register → email OTP → profile form → post-account gate). Distinct from search/page collection: the steps are stateful, the site is hostile, and the blocker is usually the exit IP rather than the script.

Complements `blocked-page-recovery` (fetch-level walls) and `stealth-search-collect` (launch + CA mechanics). If those are not curator-managed on this host, treat this file as the self-contained copy.

## Always-on rules for this user

1. **Never auto-fill sensitive fields** — OTP codes, passwords, card numbers, CVV. Fill everything else, screenshot, and stop the run so the human types the rest. A flow that reaches a card/OTP step is a hand-off point, not a bug to route around.
2. **Non-persistent means non-persistent.** When the user asks for a fresh browser per attempt, create the profile per run with `mktemp -d /tmp/<prefix>-XXXXXX`, launch into it, and `context.close()` at the end. Never reuse a profile dir for throwaway identity runs — reuse ties attempts together.
3. **Gate every proxy-routed run on an in-browser exit-IP assertion** before touching the target site (below). Discovering the wrong exit after registering is unrecoverable work.
4. **Report the step where it stopped, not a narration of the trail.** A compact status table (reached / blocked / needs-your-decision) with the screenshot path beats a retelling.

## Procedure

1. **Pick and verify the exit proxy from the target site's requirements**, not from habit. Verify with `curl -x <proxy> https://ipinfo.io/json` and record the IP. If the site is geo-gated, the *exit country* is the decision criteria — ask the user rather than guessing, and do not switch nodes silently.
2. **Launch with the proxy passed explicitly** (`launchOptions({ proxy: { server, bypass: 'localhost,127.0.0.1' } })`). See the CA rule below for what this changes.
3. **Assert the exit from inside the browser** — navigate to an IP-echo page and read it from the page context:
   ```js
   await page.goto('https://api.ipify.org', { waitUntil: 'domcontentloaded', timeout: 45000 });
   const exitIp = await page.evaluate(() => document.body.innerText.trim());
   if (exitIp !== EXPECT_IP) throw new Error(`exit ${exitIp} != ${EXPECT_IP}`);
   ```
   Abort before any form is touched. A curl-verified proxy proves the curl path only.
4. **Drive the flow, snapshotting each transition** (URL + visible buttons + body text + full-page screenshot). Transitions are where the diagnosis lives later.
5. **Poll the mailbox for the OTP** with a curl subprocess (see `references/disposable-mail-api.md` for the mail-service specifics).
6. **Fill the OTP with the native value setter**, then submit with a DOM `click()` (below).
7. **After the account is created, look at the landing page before declaring success.** Account creation and *access* are separate gates: a waitlist / "not available in your region" page means the account exists but the exit is ineligible.

## React SPA inputs (the main technical cost)

Playwright's input helpers fail against modern React forms in two distinct ways:

- **Pointer interception.** An input styled `sr-only` (or covered by any parent) is "visible, enabled and stable" yet a parent intercepts pointer events, so `click`/`type` time out with `intercepts pointer events`. Read the element's computed style — `position: absolute; clip-path: inset(50%); width:1px; height:1px` — to confirm before trying.
- **`fill` does not trigger React's `onChange`.** The value lands in the DOM and the submit button stays disabled, because React tracks its own virtual value.

The reliable path for both:

```js
await page.evaluate((code) => {
  const inp = document.querySelector('input[autocomplete="one-time-code"], input[maxlength="6"]');
  if (!inp) return 'no-input';
  inp.focus();
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(inp, code);
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new Event('change', { bubbles: true }));
}, code);
```

Verify the write took effect by reading back the **submit button's** `disabled` property, not `input.value` — React can hold a value that it never committed to its own state. Then submit the same way:

```js
await page.evaluate(() => {
  const b = [...document.querySelectorAll('button')].find(x => /^Confirm$/.test(x.innerText.trim()));
  if (b.disabled) return 'disabled';
  b.click();
});
```

Never `locator.click()` a pointer-intercepted element and never `press('Enter')` on it — both wait for a hit-test that can never succeed.

For **native text inputs** (plain name/date fields), `locator.click()` + `keyboard.type()` does work; the native-setter trick is only needed for the React-controlled OTP-style field. `<select>` fields are driven normally with `selectOption(value)`.

## Proxy and TLS

- **Firefox never reads `http_proxy` / `https_proxy`.** A proxy not passed explicitly in `launchOptions` is not in use at all, whatever the environment says.
- **When a proxy IS passed, skip the MITM CA work entirely.** The sandbox egress CA is a host-side MITM; routing through an explicit proxy bypasses it, so `certutil -A` on the profile and `SSL_CERT_FILE`/`SSL_CERT_DIR` env injection are both no-ops there. Conversely, `SEC_ERROR_UNKNOWN` on a proxied run points at the proxy's own TLS, not at the sandbox CA.
- `curl --proxy <url>` reporting `remote_ip` as a `198.19.x` host-local address is the host transparent proxy intercepting; confirm the real exit through an IP-echo service instead of the connection metadata.

## Exit-IP reputation is a per-step gate, not a global one

An identical script can clear email verification on exit A and be refused at account creation on exit B with **no code change** — the refusal surfaces as a generic "You aren't able to create an account based on the information you provided" modal. So:

- When a flow that previously worked stops working and the only variable that changed is the exit IP, change the exit before touching the script.
- Treat a generic refusal modal as an IP/quality signal to report, not a parsing failure to fix.
- A geo-gated landing page ("Muse isn't available in your country or region yet", waitlist screen) is the *exit being ineligible*, not a script error — surface it as an exit-selection decision for the user.

## Pitfalls

- **Node's global `fetch` silently drops `Authorization` through a proxy.** The same request via `curl` subprocess succeeds while `fetch` gets `403 Invalid ... credential`. Any 403 on a URL curl can read is a dropped header, not a rejected credential — put authenticated API calls in a `curl` subprocess, never in `fetch`.
- **Don't infer the mail API from the backend's docs page.** Frontend JS bundles (`/assets/index-*.js`) enumerate the real routes; grep the bundle for `"/api/..."` string literals and test with `curl` rather than guessing endpoint names.
- **Two disposable-mail domains can look identical but behave differently.** A wildcard/random address on one domain receives mail fine while another assigned domain silently drops it. Confirm delivery on the exact address you will register with before running the full flow.
- **Screenshot every transition, and keep the run's `state.json`.** The post-mortem for a signup flow is mostly "which page was I on and what did the buttons say" — reconstructing that later from memory is not possible.
- **ESM resolution is script-directory relative.** A script that imports `playwright-core`/`camoufox-js` must sit in (or symlink `node_modules` from) a directory that has them, or it dies with `ERR_MODULE_NOT_FOUND` — symlink `node_modules` rather than reinstalling.
- **A short wait after submit is not enough.** Meta-class backends take tens of seconds to materialize an account; poll the page text in a loop until it leaves the "Creating account…" state (bounded, e.g. 120–150s) instead of sleeping a fixed 8s and concluding failure.
