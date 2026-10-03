---
name: web-ui-localization
description: "Use when a deployed web app's UI needs translating."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [i18n, localization, spa, react, docker, deploy, zh]
    related_skills: [hermes-gateway-localization, vps-egress-routing, camofox-selfheal-deploy]
---

# Web UI localization (self-hosted third-party apps)

Use when the user points at a deployed web app — usually one they self-host on a VPS — and
says the UI is entirely English, then asks for the Chinese setting or a Chinese version.
Covers auditing what is actually wired, wiring the translation layer, rebuilding and
redeploying the container, and verifying in the real link.

Do not use for Hermes runtime strings (`hermes-gateway-localization`).

## When to Use

- The user points at a deployed app (their own VPS, or any self-hosted service) and reports the
  UI is entirely English, or asks where the Chinese setting is.
- A UI change — new feature, fork, or redeploy — made the interface single-language and you
  must restore the other languages.
- An asset name of the form `index-<hash>.js` under `/assets/` must change to prove the rebuilt
  bundle is the one being served.
- You need to decide whether a "translated" app is actually translated, or only ships the data.

## Always-on rules

- **A full locale catalog is not a translated UI.** Upstream routinely ships complete
  `zh`/`en`/`id` key tables while the components never call the translator. Use key-set
  parity as evidence about *data* only; prove wiring with a per-component grep for the
  translator (`t(`, `useLanguage`, `i18n.t`) before believing any key count.
- **Check the provider before the catalog.** A `LanguageContext` hard-coded to one locale
  makes the switcher a no-op, and a `LanguageSwitcher` that exists but is mounted nowhere is
  the same bug from the other side. Trace context value → provider wrap → hook → render.
- **Treat a target-language ternary as a lie until read.**
  `language === 'zh' ? 'English copy' : 'English copy'` ships often — the zh arm is a
  copy-paste of the en arm. Diff the arms of every locale ternary in a file before concluding
  a translation is missing.
- **Landing/marketing surfaces are what i18n excludes.** App chrome (nav, dashboard, forms)
  is usually wired upstream; hero sections, stats strips, terminal demos and footers are
  hard-coded prose. Budget the translation table for those components, not the chrome.
- **A prebuilt image cannot carry your edits.** Build from source in the deployment (a
  `docker-compose.local.yml` that builds `./docker/Dockerfile.frontend`) and redeploy with
  `--force-recreate`; the upstream image always ships the untranslated bundle.
- **Chain the build and the deploy, and prove the bundle changed.**
  `build && up -d --force-recreate` in one command with `&&`; a red build reuses the last good
  tag, so `up` silently deploys the previous bundle and the page looks unchanged. Confirm the
  served asset filename (the hashed bundle under the assets directory) differs from the previous
  deploy.
- **Recreate the edge container only after its upstream dependency is healthy.** A frontend
  whose nginx resolves its backend at cold start crashloops on "host not found in upstream"
  and keeps that failed resolution until recreated.
- **Put translated prose in a dedicated table beside the existing catalogs**
  (`i18n/landing-<locale>.ts`) exposing a lookup `(section, key, fallback)`, and give each
  component a `z(key, fallback)` helper bound to the context language. Do not add keys to the
  upstream catalog that no component queries.
- **Key names must match the lookup exactly.** An entry keyed by its full English sentence
  while the component looks up a short id returns the English fallback — that one line stays
  English while everything around it is translated. Grep every `z('`/`t('` literal against the
  table's keys after patching.
- **Never replace shared JSX text with unconditional target-language literals.** Bind translated labels to the language context; smoke-test zh → en → zh and verify labels in each state to catch Chinese leaking into English mode. Read DOM textContent for exact-case assertions because CSS uppercase alters innerText.
- **Split keys must follow the DOM split.** A headline broken across two spans or around a
  `<br />` needs one key per fragment; reusing one key for both fragments prints the text twice.
- **Scope the translation boundary in one line with the user:** translate prose; leave demo
  numbers, tickers, CLI samples, exchange and brand names in their original form.
- **Keep a requested quick regression sweep narrow.** Fix clear regressions from the localization diff and misleading financial labels; leave harmless residual English, formatting, and unrelated refactors alone. Do not trigger trades or paid market-data calls just to test translated UI.
- **State verification boundaries explicitly.** A healthy container, homepage 200, and configuration API 200 do not validate authenticated strategy/dashboard routes; report which routes were exercised and which required an account or paid upstream.

## Procedure

1. Establish the topology first — reverse proxy chain, which container serves which port,
   which artifact the public URL actually returns. Every later verification depends on it.
2. Audit i18n in this order:
   (a) does a catalog exist and does each language have key parity?
   (b) which components call the translator?
   (c) what does the language provider actually resolve at runtime?
   (d) which locale ternaries have an identical target arm?
3. Build the string inventory from (b) and (d) only — components already calling `t()` need
   nothing.
4. Wire the language layer: restore the provider (read the persisted preference, default to
   the app's base language), mount the switcher, then add the prose table for the excluded
   surfaces and a `z()` helper per component.
5. Build from source (`&&`-chained), deploy with `--force-recreate` once the backend is
   healthy, and confirm the served asset filename changed.
6. Verify in the real link **after a fresh navigation**. The DOM read before the reload is the
   old bundle; read a post-render marker (or the asset name) as the proof. Test target → base → target language switching, persistence after navigation/reload, login form rendering, and navigation overflow. Read each changed label in the actual rendered locale, not merely in the bundle.
7. When a route displays a generic server error, correlate its exact API requests with backend logs before blaming localization. Compare working list/config requests with failing data-provider requests and inspect the HTTP client's error mapping; a frontend that replaces every 5xx with one message conceals the upstream cause. Do not claim an unresolved payment/provider failure has been repaired by changing its displayed message.

```bash
# on the host, as one chained command
cd /root/code/<app> && \
  docker compose -f docker-compose.local.yml build <frontend> && \
  docker compose -f docker-compose.local.yml up -d --force-recreate <frontend>
B=$(curl -s http://127.0.0.1:<port>/ | grep -o '/assets/[^"]*\.js' | head -1)  # must differ
curl -s "http://127.0.0.1:<port>$B" | grep -c 'Portfolio PnL'                      # compiled?
curl -s "http://127.0.0.1:<port>$B" | grep -c 'Portofolio'                        # other locale
```

## Pitfalls

- **The rendered language and the stored preference can disagree for three separate reasons —
  separate them before editing source:** (a) the served bundle is stale (asset name
  unchanged), (b) the context value the component received is not what you assume, or (c) the
  target-language branch is genuinely empty. Diagnose (a) and (b) first — compare the served
  asset name across deploys, and inject a temporary DOM probe that mirrors the live context
  value onto an element attribute. A stale bundle and a wrong runtime value both present
  exactly like an untranslated branch, and editing source for (c) fixes nothing.
- **A locale catalog's key parity is evidence about data, never about wiring.** Prove the wiring
  per component with a grep for the translator (`t(`, `useLanguage`, `i18n.t`) and read the
  provider's resolved value at runtime; a catalog that is perfectly in sync tells you nothing
  about what renders.
- **The bundle containing both language branches proves nothing at runtime.** Grep the built
  asset for the strings to confirm they compiled; only the rendered DOM says which branch ran.
- **`patch`/`write_file` cannot reach remote paths.** Edit through a locally written script
  scp'd to the host and executed there (see `vps-egress-routing` for carrying files over).
  Remote python also avoids the local scanner redacting long content.
- **`noUnusedLocals` (TS6133) fails the build on an injected import the component never
  uses.** Inject the import and its use in the same patch, or drop the import.
- **Wrong relative import depth breaks typing after a directory move.** A component under
  `components/landing/core/` is one level deeper than `components/common/` and needs one more
  `../` to reach `contexts/` and `i18n/`.
- **A hermetic python heredoc over SSH loses its quotes.** Put the patch script on disk
  locally, scp it, then run it — never inline multi-line python with nested quotes through
  the remote shell.
- **Do not rehearse a host wipe destructively** (e.g. moving `/root/.ssh` aside to prove a
  rebuild script works). The approval layer blocks writes to system state and the prompt
  times out, stalling the session; verify self-heal by running the idempotent script and
  checking static resolution plus a real login.

## See also

`vps-egress-routing` — SSH reachability to the user-owned VPS fleet, and the reconcile-script
pattern that keeps aliases alive across host reboots.

`camofox-selfheal-deploy` — the self-heal/cron/launcher conventions for long-running local
services, useful when the deployed app is a daemon rather than a web frontend.
