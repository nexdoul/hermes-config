---
name: web-ui-rebuild
description: Use when rebuilding or replacing an existing web UI.
version: 1.0.0
author: hermes-agent
license: MIT
metadata:
  hermes:
    tags: [ui, frontend, redesign, flask, ux]
    related_skills: [remote-project-maintenance]
---

# Web UI rebuild

## When to Use

The user asks for a new/rebuilt web console or dashboard for an existing project — whether it sits beside the old UI on its own route or is meant to replace it. Load before surveying endpoints or proposing layouts.

For "make me a new web UI for X" — either a new page beside the old one or a full replacement.

## The user's UI rules (always-on)

- **Light theme unless explicitly asked otherwise.** Never default to a dark theme, and never ship a dark/light toggle that defaults to dark. A dark palette requires an explicit request.
- **Low-frequency operations hide behind one entry.** A rarely-used form goes into a modal opened by a single button (top-right `+`), not a permanently visible panel.
- **Exception — replacement scope:** if the new UI is meant to *replace* the old one, it must be functionally complete: keep every write capability, but still tuck the rare ones behind the button.
- **Settle the retirement question early.** "Does the old UI survive?" changes the whole scope: a dashboard beside the old UI can be read-only; a replacement needs all actions. If in doubt, build functional parity.
- **Every visible element earns its place.** Show what the user decides with; bury diagnostics (logs) in a collapsible that defaults to collapsed.
- **The most time-critical fact is the visual centre of the first screen.** For a scheduled batch job that is "are we in a run window, and when is the next one" — not a log feed, not a settings panel.
- **Legibility beats aesthetics.** Keep secondary text at ≥4.5:1 contrast; no dim grey-on-white body copy.
- **Coexist, then retire.** Ship the new page at its own path (`/new`), keep the old one working, and only after confirmation retire it with a one-line redirect. Put the retire step in the plan so it is not forgotten.
- **A mutation the user asks for ships as a permanent product capability.** "做成固定的功能" — land it as a per-item button on the card that opens a modal, not as a one-off data edit, a manual runbook, or a documented workaround. A capability demonstrated once must work for every item, from the console, without the agent.
- **Per-item writes live on the item.** Each card/row gets its own action buttons; a low-frequency mutation opens a modal from that card rather than a permanent form or a second page. Sibling variants (change source vs change target) go behind a radio/selector in that one modal, and on the backend prefer one generalized endpoint with a selector over parallel near-duplicate routes.
- **A save that mutates state must re-render the item locally and flash what happened** — "已切换源频道。", not a silent refresh.

## Workflow: contract first

1. **Dump the real API before designing.** Fetch each endpoint, record the exact JSON keys, real sample values, and payload byte sizes. Design from the live contract, never from the old UI's markup.
2. **Reuse the existing endpoints for every action.** If the old UI already posts JSON to `/api/x/preflight` / `/api/x/test-start`, the new UI posts the same shapes — never invent a parallel backend or change field semantics.
3. **New page = self-contained assets, no build, no CDN.** `templates/<new>.html` + `static/<new>/<new>.css` + `static/<new>/<new>.js` (vanilla), served by the framework's default static dir. Rollback is deleting 3 files + 1 route.
4. **The web server usually needs no change.** Check with `curl -s -o /dev/null -w '%{http_code}' https://host/new`: `404` means the app must own the route; a `200/30x` through a proxy means nothing to do. Do not touch nginx speculatively.
5. **Auth inherits.** The new route goes behind the same login decorator/existing session as the old ones; no second auth path.
6. **Lazy-load big payloads.** A full payload can be hundreds of KB per record. Use the API's since/incremental parameters, keep poll intervals slow (8–10s), and pause polling entirely on hidden tabs.
7. **Server-side caching for polled data.** If the old console forked a subprocess per poll, add a small TTL cache in the app before adding poll volume.
8. **Pin the contract in tests.** A test asserting `client.get(...)` returns 200 for every endpoint the UI calls, so endpoint drift fails loudly instead of silently breaking the new UI. When a full payload is large, also assert the incremental call returns the small response — that stops anyone reintroducing full polling.
9. **Verify new interactions in a local harness against a real captured API snapshot.** Serve the page with `fetch` mocked from actual endpoint payloads (Jinja placeholders resolved to literal paths), and drive the flows from inside the page. A mock that answers a POST must look at `options.body` — fetch sends a URL-encoded form string unless the app sets JSON headers, and a `JSON.parse` error there is the mock's fault, not the app's.
10. **Have the page report its own results.** Write the harness outcome into the DOM (`#selftest-result[data-json]`, populated after the flows finish) and read that element back — the devtools/console read can return a stale or bfcache-restored snapshot and report phantom zero-calls, which sends you chasing a product bug that does not exist.

## What the plan must contain

Survey facts (URLs, ports, auth mechanism, endpoint contract table with sample values and sizes), the route/file list, a per-screen content table with a "why this content" column, the full CSS variable block for the chosen light theme, copy-pasteable JS for the two riskiest interactions (first load; the hidden form's submit), and TDD tasks with exact commands plus expected output. An implementer with zero context must not have to guess.
