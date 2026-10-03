path '/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/gateway/platforms/base_exec_approval.py'

Owns the shared approval WORDS. English constants remain exported for tests
(`EA_HEADER_TEXT`, `EA_REASON_LABEL_TEXT`), but all rendering calls
`ea_header_text()`, `ea_reason_label_text()`, `ea_action_label()`, so the language
resolves per call, not per import. Also owns
`format_approval_deadline_line(timeout_s, *, lang=None)` and
`format_approval_timed_out_notice(...)`. Timeout units get their own pluralized
keys per unit+language (300 -> `5 分钟`, never `5 minutes` leaking into zh).

# path '/home/hatch/.home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/gateway/platforms/base.py'

`_format_exec_approval` renders the prompt. Localization is a phrase-key swap:
find the English phrase, replace with the localized one, keep the surrounding
markup exactly. Long Feishu labels are not replaced by the generic path — see the
Feishu adapter. `_is_cjk()` decides `:` vs `：`.

# path '/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/gateway/run.py'

`_format_exec_approval_fallback(...)` renders the plain-text `/approve` prompt for
surfaces without interactive cards. Same locale wording as the gateway path.

# path '/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/plugins/platforms/feishu/adapter.py'

Card title is `⚠️ {ea_header_text()}` — a call, not an imported constant.
`_EA_REASON_LABEL` is reset to the English phrase so the shared phrase-replacement
function can find it. `_exec_approval_actions()` is overridden here because the
Feishu labels (`✅ Session`, `✅ Always`) are shorter than the base English phrases
and word-level replacement cannot match them; the override must keep the emoji
prefixes and the `hermes_action` callback values unchanged.

# locale keys

`approval.exec_*` for the prompt words, `approval.action_*` for button labels,
`exec_window_unit_*` / `exec_window_units_*` for pluralized timeout units per
language, and `exec_smart_deny_label` / `exec_smart_deny_tail` for the
smart-denied notice. After adding keys to en+target, insert parity blocks into
the other catalogs with a script so that no catalog is missing an
`approval.exec.*` key or `{placeholder}`.

# tests that must pass

`tests/gateway/test_exec_approval_i18n.py` (new-feature contract: both languages,
markup survives, choice keys unchanged, Feishu card wiring), plus existing
`tests/gateway/test_exec_approval_template.py`,
`test_exec_approval_timeout_notice.py`,
`tests/tools/test_approval_user_summary.py`,
`test_plaintext_approval_routing.py`,
`test_interactive_prompt_base.py`, `test_feishu_approval_buttons.py`.
Agent side: `tests/agent/test_i18n.py` and a Chinese-regression test asserting the
target strings for each touched key.

# verification surfaces

Surfaces to check per adapter: title/header, reason label, deadline line,
timeout notice, action button labels, resolved-approval card, update prompt
card. On Feishu, a real card that resolves a click (`Feishu button resolved N
approval(s)` with N>0) proves the whole path — unit tests alone do not.
