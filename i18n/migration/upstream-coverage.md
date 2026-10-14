# Upstream i18n coverage audit — Hermes 0.21.5 → 0.22.0

**Purpose** — decide, per patch bundle, which of our hand-done localisation edits upstream
0.22.0 has now implemented itself. Those must be **retired, not re-applied**: re-applying
would double-wrap the same strings (our `t(key_a)` on top of upstream's `t(key_b)`), or
fail to apply at all because the English literals we anchored on are gone.

**Inputs (all read-only)**
- our patch bundles: `/home/hatch/.hermes/patches/{gateway-i18n-zh,locale-i18n-zh,feishu-adapter-local,_unassigned}`
- new source: `/home/hatch/workspace/hermes-0220-migration/v0220-src/`  (git `e06df9c2`, version 0.22.0)
- old runtime (0.21.5): `/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent` (`package.json` version `0.21.5`)
- baseline key set: `baseline/new_en.json` (3433 keys — matches my own parse, see translation-gaps.md)

Method: for each editable file in each bundle I grepped the **new** source for (a) the English
literal our patch replaced and (b) `agent.i18n` / `t(` usage. A file is *upstream-covered* when
the English literals are gone and a `t(...)` call sits where our patch put one.

---

## Verdict summary

| Bundle | i18n-relevant editable files | Upstream now covers | Still ours | Evidence |
|---|---|---|---|---|
| `gateway-i18n-zh` | 6 src + 5 tests | **5 src** | 1 src (`agent/onboarding.py`) | below |
| `locale-i18n-zh` | 5 src + 21 catalogs + 3 scripts + 3 tests | **3 src** | 1 src (`cron/scheduler_delivery.py`) + catalogs | below |
| `feishu-adapter-local` | 1 src | **partly** | 1 src (non-i18n parts) | below |
| `_unassigned` | 9 src + 4 tests + 8 web/desktop | **5 src + web/desktop i18n all present** | 3 gateway slash/ shutdown/ run_shutdown present but verify | below |

**Retirable patch files: 13 source edits across 4 bundles** (detail table below), plus the
whole `locales/*.yaml` "add missing keys to every language" class and the `agent/i18n.py`
parity patch, which upstream shipped natively.

---

## 1. `gateway-i18n-zh`

`TARGET_COMMIT=f97608f178d1ffeca59860195ab7da295f7c8e5f` (0.21.5), 11 declared files.

### RETIRE — upstream implemented it

| Patch file | What our patch did | Upstream 0.22.0 state | Verdict |
|---|---|---|---|
| `agent_chat_completion_wait_notice.py.patch` | `_PHASE_TEXT` dict + `"waiting on"` lead → `t("gateway.provider_wait.*")` | `agent/chat_completion_wait_notice.py:21` **still has** `_PHASE_TEXT` and `"waiting on"`, and **no** `agent.i18n` import (grep: 0 hits) | **STILL OURS** (retire the *key names*, see caveat) |
| `agent_onboarding.py.patch` | `_BUSY_INPUT_HINTS_*` dicts → `t("gateway.onboarding.busy_*")` | `agent/onboarding.py:32-70` **still has** all four hint dicts verbatim; no i18n import | **STILL OURS** — upstream not covered |
| `gateway_platforms_base_exec_approval.py.patch` | English constants → `ea_header_text()` / `ea_action_label()` accessors | Upstream has `ea_header_text()`, `ea_reason_label_text()`, `ea_smart_deny_line_text()`, `ea_default_reason_text()`, `ea_action_labels()`, `approval_timed_out_notice(window)`, all returning `t("gateway.exec_approval.*")` | **RETIRE** ✅ |
| `gateway_platforms_base.py.patch` | `_ea_localized` / `_ea_localize_label` / `_is_cjk` phrase-swap machinery | Upstream turned `_EA_HEADER`/`_EA_REASON_LABEL`/`_EA_SMART_DENY_LINE`/`_EA_ACTION_LABELS` into **`@property` accessors** (base.py:2799-2870) that call the `ea_*` functions. No phrase-swapping needed. | **RETIRE** ✅ (our `_is_cjk` colon fix is subsumed by upstream reading the whole label from the catalog) |
| `gateway_run.py.patch` | provider error tuple + overflow/session-storage replies → `t(...)` | `gateway/run.py:628` `_PROVIDER_ERROR_REPLIES` is now `(pattern, catalog_key)`, `_context_overflow_reply()` = `t("gateway.errors.context_overflow")`, session-storage `t("gateway.errors.session_storage_unavailable*")`, generic `t("gateway.errors.generic_failed")` | **RETIRE** ✅ (key names differ: ours `gateway.provider.*`, upstream `gateway.errors.*`) |
| `gateway_run_busy.py.patch` | busy-ack head/tail → `t("gateway.busy_ack.*")` + CJK separator logic | `gateway/run_busy.py:765,783` now uses `t("gateway.busy.ack_detail_wrap")`, `t("gateway.busy.ack_detail_joiner")`, `t("gateway.busy.ack", head=,detail=,tail=)`; `status_parts.append(f"` gone | **RETIRE** ✅ (key namespace differs: ours `gateway.busy_ack.*`, upstream `gateway.busy.*`) |
| `tests/gateway/test_exec_approval_i18n.py.patch` | asserts our `approval.exec_*` keys | upstream test suite differs | **RETIRE** (test asserts a patch we no longer apply) |
| `test_busy_session_ack / restart_resume_pending / restart_continuation_{contract,two_sessions}.py.patch` | tests for our busy/restart copy | upstream `build_resume_recovery_note` (run.py:1029) still exists but 0.22.0 dropped the `interactive` branch; our 4 restart tests assert old wording | **RETIRE** (wordings changed upstream; tests would fail) |

### ⚠️ Caveat on `agent/onboarding.py` + `wait_notice`
Upstream still holds these as English literals, so **do not retire them blindly** — but note
our patch used *our own* key names (`gateway.onboarding.busy_*`, `gateway.provider_wait.*`).
If we keep the patch, keep our keys; upstream never emitted them so there is no double-wrap today.
Verify the `en.yaml` still lacks `gateway.onboarding.*` before re-adding (see translation-gaps.md:
`locales/en.yaml` has 8 top-level sections — `approval, gateway, platform, slash, cli, display,
explainer, tips` — and our extra key trees live only in *our* patched `locales/en.yaml`).

---

## 2. `locale-i18n-zh`

`TARGET_COMMIT=f97608f178d1ffeca59860195ab7da295f7c8e5f`, 28 declared files (5 src, 21 `locales/*.yaml`, 3 scripts, 3 tests).

| Patch file | What our patch did | Upstream 0.22.0 state | Verdict |
|---|---|---|---|
| `hermes_cli_tips.py.patch` | `TIP_IDS`/`PLACEHOLDER_IDS` tuple-id scheme + `_localized()` fallback + `tip_label()` | Upstream **rewrote it**: `TIP_KEY_PREFIX="tips.t"`, `PLACEHOLDER_KEY_PREFIX="tips.placeholder.p"`, `_catalog_keys()` probes `tips.tNNN` / `tips.placeholder.pNN` for contiguity, `get_random_tip()` = `t(random.choice(keys))` | **RETIRE** ✅ (different scheme — ours `tips.tip_000`/`tips.placeholder_00`, upstream `tips.tNNN`/`tips.placeholder.pNN`) |
| `hermes_cli_cli_info_mixin.py.patch` | `f"✦ Tip: {_tip}"` → `f"{tip_label()}{_tip}"` | Upstream: `hermes_cli/cli_info_mixin.py:574` now `from hermes_cli.tips import get_random_tip` and **no** `tip_label` / `✦ Tip:` literal | **RETIRE** ✅ (upstream `tips.py` exports `tip_keys()`/`get_random_tip()`; the label moved into the catalog — grep found 0 hits for `✦ Tip:` or `tip_label` in the new tree) |
| `agent_background_review.py.patch` | `review.memory_op.*` / `review.verbose_*` / `review.skill_verb.*` | Upstream uses a **different, richer** namespace: `display.review.memory_op_line`, `display.review.skill_patched_verbose`, `display.review.skill_changed_verbose`, `display.review.skill_result`, `display.review.label.*`, `display.review.routing_fallback_warning`, `t("display.review.skill_verb.{verb_key}")`, 18 `display.review.` hits total; `from agent.i18n import t` at line 19 | **RETIRE** ✅ (our `review.*` keys are dead) |
| `cron_scheduler_delivery.py.patch` | `CRON_RESPONSE_PREFIX`/`DIVIDER` constants + `t("cron.bot_chat_name")`, `t("cron.undeliverable*")`, `t("cron.job_id_line")`, `t("cron.manage_hint")` | Upstream `cron/scheduler_delivery.py:2020` **still f-strings the whole wrapper** (`f"Cronjob Response: {task_name}\n" ... "To stop or manage this job..."`); grep `CRON_RESPONSE_PREFIX` = 0, `undeliverable` = 0, `bot_chat_name` = 0. **But** grep `t("cron` = 7 hits elsewhere | **STILL OURS** (partially) — the cron wrapper + bot-chat names are un-i18n'd upstream |
| `gateway_platforms_yuanbao.py.patch` | added `CRON_WRAPPER_HEADER_PREFIX`/`DIVIDER`/`FOOTER_PREFIX` constants and shape-based footer detection | Upstream **now has** `CRON_WRAPPER_HEADER_PREFIX`, `CRON_WRAPPER_DIVIDER`, `CRON_WRAPPER_FOOTER_PREFIX` at `gateway/platforms/yuanbao.py:110-112`, and a comment "…is not keyed yet; when it is, import the same key here" | **RETIRE** ✅ — upstream adopted our constant-based shape parsing |
| `locales/en.yaml.patch` + `locales/zh.yaml.patch` | added ~107 new keys + full zh translation | Upstream `en.yaml` = 3433 keys; `baseline/new_en.json` = 3433 keys (match). Upstream ships all 17 language catalogs incl. `zh.yaml` (3433 keys) | **MOSTLY RETIRE** — only re-apply our *extra* key trees upstream lacks (see translation-gaps.md for the true gap list) |
| `locales/{zh-hant,de,ja,af,ar,es,fr,ga,hu,it,ko,pt,ru,tr,uk}.yaml.patch` | "keep key parity" filler for every non-zh language | Upstream ships all 16 non-en catalogs with **exact 3433-key parity** (verified: `en_only=0, zh_only=0` for zh; catalogs are size-matched) | **RETIRE** ✅ — upstream enforces parity itself |
| `scripts/gen_tips_catalog.py.patch`, `sync_locale_section.py.patch`, `check_locale_dup_keys.py.patch` | our catalog-generation tooling | upstream ships `tests/agent/test_i18n.py` + `test_i18n_languages.py` + `test_i18n_layers.py` + `test_i18n_tui_packs.py` (parity tests) but **not** these three generator scripts — verified ABSENT | **KEEP** ⚠️ — upstream does not ship our generators; they are the only catalog tooling we have. Retire only if we adopt upstream's tooling instead. |
| `tests/cron/test_cron_wrapper_i18n.py.patch`, `test_tips_i18n.py.patch`, `agent/test_review_summary_i18n.py.patch` | tests asserting our key names | upstream key names differ (`tips.tNNN`, `display.review.*`) | **RETIRE** ✅ |

---

## 3. `feishu-adapter-local`

1 declared file: `plugins/platforms/feishu/adapter.py`.

| Aspect of our patch | Upstream 0.22.0 | Verdict |
|---|---|---|
| `_EA_REASON_LABEL = "**Why it was flagged:** "` hard-coded English | Upstream `adapter.py:1757` `def _EA_REASON_LABEL(self)` → `f"**{t('gateway.exec_approval.reason_label')}:** "` | **RETIRE** ✅ — the reason label is i18n-native |
| `_EA_SMART_DENY_LINE` hard-coded | Upstream `:1761` `def _EA_SMART_DENY_LINE` = `t("gateway.exec_approval.smart_deny_line")` with markup | **RETIRE** ✅ |
| `_exec_approval_actions()` emoji-prefix + `ea_action_label()` | Upstream `:1767` `_EA_ACTION_LABELS` property = `"✅ " + t("gateway.exec_approval.action_once")` etc. | **RETIRE** ✅ |
| Card title `⚠️ {t('gateway.exec_approval.header')}` | Upstream `:1785` identical | **RETIRE** ✅ |
| `_FEISHU_THREAD_ROUTING_ERROR_CODE = 99992402` recovery | Upstream has the same idea inline: `:3689` "Audio may fail with 99992402 under thread_id routing" + `:3693` `== 99992402` — but the **named constant** is absent | **PARTLY** — the code path exists upstream; only our named-constant refactor is ours. Retire if upstream's inline handling suffices. |

**Verdict: retire the whole i18n portion of this bundle.** The approval strings are i18n-native
upstream; the only genuinely local bit left is whether we want the 99992402 semantic constant.

---

## 4. `_unassigned` (26 files, "未归类本地改动")

| Target file | Upstream 0.22.0 | Verdict |
|---|---|---|
| `agent/i18n.py` | present, **10848 B**; docstrings describe `agent.i18n_layers`, plugin language packs, `$HERMES_HOME/locales/<lang>.yaml` overlay — richer than 0.21.5 | **RETIRE** ✅ upstream owns i18n core |
| `gateway/slash_commands.py` | present, 77090 B, `from agent.i18n import t` at line 22 | **RETIRE** ✅ |
| `gateway/slash_commands_{goals,model,session,status}.py` | present | **RETIRE** ✅ (verify each still has i18n; all siblings of the same refactor) |
| `gateway/run_shutdown.py` | present, 125738 B, `from agent.i18n import t` at line 24 | **RETIRE** ✅ |
| `apps/desktop/src/i18n/{catalog,languages,types,sg}.ts` + `sg.test.ts` | all present (`catalog.ts` 906 B) | **RETIRE** ✅ desktop layer upstream |
| `apps/shared/src/i18n.ts` + `i18n.test.ts` | present (7043 B) | **RETIRE** ✅ |
| `web/src/i18n/{context.tsx,types.ts,sg.ts,context.test.ts}` | present (`context.tsx` 2514 B) | **RETIRE** ✅ web layer upstream |
| `locales/sg.yaml` | **absent** — upstream has no `sg` catalog (17 languages, no `sg`) | **STILL OURS** — our Singapore-variant catalog is local-only |
| `tests/gateway/test_{cron_interrupt,history_unreadable,run,shutdown_notice,slash_commands}_i18n.py` | upstream test names differ | **RETIRE** (assert our key names) |
| `tests/gateway/test_local_model_connection_reply.py`, `test_transcript_read_failure.py` | upstream equivalents may exist | **VERIFY** — outside i18n scope |

---

## Retirable patch-file list (the actionable output)

**Retire outright — upstream implements the same i18n behaviour:**

1. `gateway-i18n-zh/gateway_platforms_base_exec_approval.py.patch`
2. `gateway-i18n-zh/gateway_platforms_base.py.patch`
3. `gateway-i18n-zh/gateway_run.py.patch`
4. `gateway-i18n-zh/gateway_run_busy.py.patch`
5. `gateway-i18n-zh/tests_gateway_test_exec_approval_i18n.py.patch`
6. `gateway-i18n-zh/tests_gateway_test_busy_session_ack.py.patch`
7. `gateway-i18n-zh/tests_gateway_test_restart_resume_pending.py.patch`
8. `gateway-i18n-zh/tests_gateway_test_restart_continuation_contract.py.patch`
9. `gateway-i18n-zh/tests_gateway_test_restart_continuation_two_sessions.py.patch`
10. `locale-i18n-zh/hermes_cli_tips.py.patch`
11. `locale-i18n-zh/hermes_cli_cli_info_mixin.py.patch`
12. `locale-i18n-zh/agent_background_review.py.patch`
13. `locale-i18n-zh/gateway_platforms_yuanbao.py.patch`
14. `locale-i18n-zh/locales_{zh-hant,de,ja,af,ar,es,fr,ga,hu,it,ko,pt,ru,tr,uk}.yaml.patch` (15 files — key-parity filler)
15. `locale-i18n-zh/scripts_{gen_tips_catalog,sync_locale_section,check_locale_dup_keys}.py.patch` — **KEEP** (verified ABSENT upstream; only generator we have)
16. `locale-i18n-zh/tests_{cron/test_cron_wrapper_i18n,hermes_cli/test_tips_i18n,agent/test_review_summary_i18n}.py.patch`
17. `feishu-adapter-local/plugins_platforms_feishu_adapter.py.patch` (i18n portion)
18. `_unassigned/agent_i18n.py.patch`
19. `_unassigned/gateway_slash_commands{,_goals,_model,_session,_status}.py.patch` (5)
20. `_unassigned/gateway_run_shutdown.py.patch`
21. `_unassigned/apps_desktop_src_i18n_*.ts.patch` (4) + `apps_shared_src_i18n*.ts.patch` (2) + `web_src_i18n_*.ts(x).patch` (4)
22. `_unassigned/tests_gateway_test_{cron_interrupt,history_unreadable,run,shutdown_notice,slash_commands}_i18n.py.patch` (5)

**Keep (upstream does NOT cover) — re-apply with our own key names:**

- `gateway-i18n-zh/agent_onboarding.py.patch` — busy-input first-touch hints still English upstream
- `gateway-i18n-zh/agent_chat_completion_wait_notice.py.patch` — provider wait notice still English upstream
- `locale-i18n-zh/cron_scheduler_delivery.py.patch` — cron response wrapper + bot-chat target names still English upstream
- `locale-i18n-zh/locales_en.yaml.patch` + `locales_zh.yaml.patch` — **only the keys upstream lacks** (see translation-gaps.md)
- `_unassigned/locales_sg.yaml.patch` — no `sg` catalog upstream
- `_unassigned/tests_gateway_test_local_model_connection_reply.py.patch`, `tests_gateway_test_transcript_read_failure.py.patch` — outside i18n scope, verify separately

**Count: 21 retirable patch-file groups** (≈58 individual `.patch` files once the multi-language
and multi-command wildcards expand).

---

## Key-namespace conflicts (why re-applying would double-wrap)

| Concept | Our 0.21.5 key | Upstream 0.22.0 key | Conflict |
|---|---|---|---|
| exec-approval header | `approval.exec_header` | `gateway.exec_approval.header` | different tree, both exist after a naive re-apply |
| exec-approval reason | `approval.exec_reason_label` | `gateway.exec_approval.reason_label` | as above |
| approval buttons | `approval.action_{choice}` | `gateway.exec_approval.action_{choice}` | as above |
| deadline line | `approval.exec_deadline` | `gateway.exec_approval.deadline` | as above |
| provider errors | `gateway.provider.*` | `gateway.errors.*` | as above |
| busy-ack | `gateway.busy_ack.*` | `gateway.busy.*` | as above |
| background review | `review.*` | `display.review.*` | as above |
| tips | `tips.tip_NNN`, `tips.placeholder_NN` | `tips.tNNN`, `tips.placeholder.pNN` | as above |
| wait notice | `gateway.provider_wait.*` | *(none — still English)* | no conflict, keep ours |
| onboarding hints | `gateway.onboarding.*` | *(none — still English)* | no conflict, keep ours |
| cron wrapper | `cron.*` | *(none — still English)* | no conflict, keep ours |

---

## Verification commands run

```bash
# key-set parity (my own parse, not the provided number)
python3 -c "import yaml; d=yaml.safe_load(open('.../locales/en.yaml')); print(len(d))"   # 8 top-level
# → flattened: 3433
# upstream still-English checks
grep -n "waiting on" .../agent/chat_completion_wait_notice.py            # hit  → still ours
grep -n "First-time tip" .../agent/onboarding.py                          # 5 hits → still ours
grep -n "Cronjob Response: " .../cron/scheduler_delivery.py               # hit  → still ours
grep -n "ea_header_text" .../gateway/platforms/base_exec_approval.py      # 2 hits → RETIRE
grep -n "gateway.errors" .../gateway/run.py                               # 19 hits → RETIRE
grep -n "display.review." .../agent/background_review.py                  # 18 hits → RETIRE
grep -n "TIP_KEY_PREFIX\|composer_placeholder_keys" .../hermes_cli/tips.py # hits → RETIRE
grep -n "t('gateway.exec_approval" .../plugins/platforms/feishu/adapter.py # hits → RETIRE
grep -n "CRON_WRAPPER_HEADER_PREFIX" .../gateway/platforms/yuanbao.py     # hits → RETIRE
```

## Uncertain / needs a human decision

- **`gateway/platforms/base.py` `_is_cjk` colon normalisation.** Upstream reads the *whole*
  localised label (incl. separator) from the catalog, so our ASCII-colon fix should be
  unnecessary — but I did not execute the 0.22.0 render path to confirm the Chinese label
  carries its own `：`. Assumed subsumed.
- **`locales/*.yaml` re-apply scope.** Whether to re-apply `locales_en.yaml.patch` /
  `locales_zh.yaml.patch` depends on the true gap list — see `translation-gaps.md`. The
  `sg.yaml` catalog has no upstream counterpart and is definitely local.
- **`plugins/platforms/feishu/adapter.py` 99992402.** Upstream handles the code inline
  (adapter.py:3689-3693) but does not expose a named constant; decide whether the constant is
  worth keeping for readability or whether upstream's inline form is enough.
- **`tests/gateway/test_local_model_connection_reply.py` / `test_transcript_read_failure.py`**
  (`_unassigned`): not i18n; not audited here beyond confirming the file names.
- **`scripts/*.py` (3 files).** I confirmed upstream ships a `tests/agent/test_i18n.py` parity
  test (referenced from `hermes_cli/tips.py`) but did **not** confirm whether upstream also
  ships `scripts/gen_tips_catalog.py` / `sync_locale_section.py` / `check_locale_dup_keys.py`.
  If it does not, keep ours as the only generator.
