---
name: hermes-gateway-localization
description: Use when localizing Hermes gateway, Feishu, and CLI strings.
---

# Hermes conversation-side localization

Runtime repo: `~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent`. Default scope = the conversation side (gateway prompts, Feishu cards, provider wait notices, busy acknowledgements). The desktop UI is a separate effort — confirm scope with the user before starting.

## Always-on rules
- The English path must render unchanged after your change (`Why it was flagged:`, `it will NOT run`, `Allow Once`, and the other originals). Pin it with a test that runs the en language, not just zh.
- Localize WORDS only. Markup (`**`, `<b>`, emoji prefixes, code fences) stays in adapter class attributes; locale values never carry markup, and a CJK label switches ASCII `:` to `：`.
- Wire contracts never localize: Feishu `hermes_action` callback values (`once`/`session`/`always`/`deny`), choice keys, style ids like `primary`/`danger`.
- Every non-`en` catalog must contain the key or `t()` silently falls back to English. Parity = key-set equality + `{placeholder}` equality against `en.yaml`.
- Module-level English constants freeze the language at import time. Move them to call-time helpers that resolve `t()` per invocation (e.g. `ea_header_text()` instead of an imported `EA_HEADER_TEXT`), so a running process always renders the active language.

## Procedure (order matters)
1. Baseline the local `locales/zh.yaml` against any fork or upstream reference before importing anything: a fork with fewer keys, an older version, and tens of thousands of divergent lines in `gateway/run.py` is not an improvement source.
2. Map each surface's words to where they live (see `references/approval-and-surface-map.md`); confirm with a `t(` grep plus an English-literal grep of `gateway/`, `plugins/platforms/`, and `agent/`.
3. RED first: for every surface assert BOTH the target-language string AND the unchanged English string, plus a markup-survival assertion per adapter.
4. Add keys to `locales/en.yaml` (current English verbatim), then the target locale, then insert parity blocks into every other catalog by script (safer than hand-editing a dozen files).
5. Run with the repo venv: `./venv/bin/python -m pytest -q -o addopts='' <tests>`. Report failures that are exactly `async def functions are not natively supported` as unrunnable-async cases — count them and never present them as damage from your change.
6. Verify in the real link (a Feishu card actually rendering and accepting clicks). Unit tests prove rendering only.

## "Is my code live?" — check before claiming a restart is needed
Compare the running gateway's start time with the changed files' mtimes: `ps -o pid,lstart,cmd -p <gateway-pid>` vs `ls -l --time-style=full-iso <changed files>`. A process that started after your edits already runs them. Config changes are hot-reloaded (mtime/size cache signature) and need no restart; Python source changes do. Restarting the gateway is NOT restarting the container — hand host restarts to the container-side agent; the standing restart rules live in `/home/hatch/AGENTS.md`.

## Pitfalls (`export PATH=<repo>/venv/bin:$PATH`). Replacing PATH breaks every coreutil for the rest of the session; if it happens, restore with `export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`.
- Bulk locale edits produce duplicate nested blocks; run a duplicate-key YAML check after every bulk edit.
- Rebuilding a locale from scratch silently drops existing translations — restore from the diff instead of regenerating.
- The live log file is whatever `/proc/<gateway-pid>/fd/1` points at; other `.log` files under `~/.hermes/logs/` can be stale relative to the running process.

## Where the exec-approval words live
`gateway/platforms/base_exec_approval.py` owns the shared WORDS; adapters wrap them in their own markup. `gateway/platforms/base.py` renders through phrase-key substitution (a CJK label switches `:` to `：`), `gateway/run.py` owns the plain-text `/approve` fallback, and Feishu overrides `_exec_approval_actions()` because its button labels are shorter than the English phrases and cannot be replaced word-for-word. Details and the full test list in `references/approval-and-surface-map.md`.
