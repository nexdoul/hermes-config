---
name: camofox-selfheal-deploy
description: "Use when deploying Camofox or a watchdog-managed service."
version: 1.0.0
---

# Camofox Self-Heal Deployment Pattern

Use when deploying any long-running local service (browser server, API daemon) on an ephemeral container host where only /home/hatch persists and the machine restarts unpredictably. Proven end-to-end with Camofox on htch-runtime (2026-09-27).

## Launcher pattern

1. Install everything under `/home/hatch` (repo, node_modules, binaries, data, logs). Nothing outside /home/hatch survives restarts.
2. Download big binaries via **multi-part ranged curl** (8 blocks, `curl -r start-end`, cat parts, verify zip CRC with python's zipfile.testzip). Single-stream GitHub release downloads hang through this egress proxy.
3. Write a launcher script (`/home/hatch/bin/<svc>-start`) that: flock-serializes → health-checks the port (exit 0 silently if healthy → safe for cron) → runs pre-flight checks → `nohup` + `disown` the server → poll until the real page is ready → touch `.last_healthy` marker in the service's log dir. Close the flock FD in the daemon launch (`nohup node ... 9>&- ... &`); otherwise the daemon inherits the lock, subsequent cron launches block and fail.
4. Register a hermes cronjob: `no_agent=true` + `script=<filename>` (relative to `/home/hatch/.hermes/scripts/`). Failure alerts fire only when the script exits non-zero; empty stdout sends nothing. Keep an identical copy of the launcher in `/home/hatch/.hermes/scripts/`.
5. Log health via mtime of `.last_healthy`, never via absence of errors in the log (silent-healthy convention, same as reverse-ssh-134 watchdog).
6. Save all setup notes to a persistent file (e.g. `~/.hermes/cache/scratch/<svc>-setup-notes.md`) AND a short entry in the workspace AGENTS.md — scratch is pruned per-task, AGENTS.md persists.

## Camofox specifics

- Repo: github.com/jo-inc/camofox-browser, runs with `node server.js` (port 9377) after `npm install`; no Docker needed (containers cannot run on this host — runc/setns blocked).
- Camoufox binary (~633MB zip → 1.2GB unpacked) lives in `~/.cache/camoufox` (camoufox-js default INSTALL_DIR). Version file must be `{"release":"beta.N","version":"152.0.x"}` — release carries the beta.N suffix.
- `CAMOFOX_DISABLE_DEFAULT_ADDONS=1` required on this host: default UBO addon download (addons.mozilla.org) fails at runtime, launching aborts with "manifest.json is missing".
- GeoIP: manually place GeoLite2-City.mmdb in the camoufox dir (P3TERX/GeoLite.mmdb release) or launch logs "GeoIP setup timed out".
- Hermes integration: `CAMOFOX_URL=http://localhost:9377` in `~/.hermes/.env` + `browser.cloud_provider: camofox` in config.yaml (hermes config set warns "unrecognized key" but writes it correctly in the browser section; runtime reads it via tool_backend_helpers.read_selection). Enable `"browser"` in toolsets.
- Verify: `curl :9377/health` → browserConnected:true, then `hermes chat -q "use browser_navigate…"`. bot.sannysoft.com fingerprint suite: expect only Chrome(New) to fail on a Firefox engine.
- hermes-start (the desktop launcher's own self-heal) may reinstall runtime (npm + git tag) on version drift — takes 5-10min while the old gateway process keeps serving; don't panic-kill it.
- For shared GUI browser: Camofox VNC plugin uses Xvfb + x11vnc + websockify/noVNC, all loopback-only. Browser API must be loopback-only (`CAMOFOX_BIND_HOST=127.0.0.1`) and Bearer-authenticated; 9377 must never be proxied publicly. Hermes uses fixed `browser.camofox.user_id`, `session_key`, and `adopt_existing_tab=true` to pick up the human's tab; browser's persistent storage plugin checkpoints cookies/localStorage/IndexedDB to `/home/hatch/.camofox/profiles` on shutdown and storage export.
- On this ephemeral machine, VNC apt packages in /usr disappear after reset. Stage every `.deb` and dependencies under `/home/hatch/camofox-browser/.vnc-stack/debs/`; launcher must `dpkg -i` them before starting Camofox. Its watcher owns noVNC and attaches to the dynamically assigned Xvfb screen. Set `SESSION_TIMEOUT_MS=0`, `BROWSER_IDLE_TIMEOUT_MS=0`, and `TAB_INACTIVITY_MS=0` to keep a visible tab alive. Caveat: stock `lib/config.js` parses tab timeout with `parseInt(...) || 300000`, so zero silently becomes 5 minutes; `server.js` reaper then closes the last visible tab (VNC shows a black 1600x900 Xvfb screen although /health, /vnc/status and WSS are healthy). Patch config to preserve zero as for session/browser idle and guard the tab reaper with `TAB_INACTIVITY_MS > 0`; test config RED→GREEN. Verify by X11 capture with ffmpeg/Pillow and tab listing, not merely the VNC handshake. Ensure one shared tab is open after cold start (Camofox prewarm creates a 10x10 off-screen window, thus no visible page until POST /tabs). Cookies persist via the storage-state plugin, not a true persistent Firefox profile.
- A dedicated persistent Muse browser needed an explicit `hatch-egress-proxy:3128` Playwright proxy on this host; direct navigation timed out and literal IPv6 proxy URL yielded `NS_ERROR_UNKNOWN_HOST`. The hostname worked. A `muse.ai` HTTP 307 can lead to `auth.muse.ai` and Facebook; test full browser rendering, not only the first redirect. Distinguish document-start userscript initialization and `el.click()` log from server-side approval confirmation. A true persistent Firefox profile under `/home/hatch` can retain Muse cookies through dedicated process restarts; check authenticated workspace DOM after hydration, not just page title or cookie presence. Do not treat `SEC_ERROR_UNKNOWN` as a successful page load; screenshot and inspect the real page.
- Hermes cron treats a script with no `.sh`/`.bash` extension as Python even with a shell shebang. Name the cron copy `camofox-start.sh` and point cron's `script` to that exact filename; test with `hermes cron run <id>` and inspect `hermes cron runs <id>`.
- A Camofox restart returns HTTP 410 (not 404) for stale UUID tab IDs. Hermes `tools/browser_camofox.py::_navigate_tab` must recreate on either 404 or 410; keep regression test. That local runtime patch is registered as bundle `camofox-tab-recreate` under the runtime-patch self-heal (skill `hermes-runtime-local-patches`), so a reinstall re-applies it automatically — verify after any reinstall rather than assuming it is lost.
- For remote GUI, VPS 134's existing reverse SSH `:2222` and operator key let VPS systemd run a loopback `ssh -L 127.0.0.1:13081:127.0.0.1:6080 -p 2222 root@127.0.0.1`; Nginx TLS + Basic Auth may reverse-proxy only `:13081`, with WebSocket Upgrade headers. Keep auth secret in `/home/hatch/.camofox/browser-access.txt`, not in docs/chat. Verify the public WSS handshake and RFB mouse/keyboard action, then read `/tabs?userId=...` to prove AI/human share the same tab.
