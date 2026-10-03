"""Exec-approval wording must be localizable without touching the markup.

The shared approval words (header, reason label, deadline line, timeout notice)
live in ``gateway/platforms/base_exec_approval.py`` so one edit changes every
surface.  That made them hard-coded English while the catalogs already carry
the CLI approval wording; the gateway surfaces now read the same catalog keys.

Pinned here:

* English output stays byte-identical to the old constants, so the adapter
  markup and every existing template/button test keep passing.
* ``display.language=zh`` (or ``HERMES_LANGUAGE=zh``) yields Chinese text.
* The label word and the choice it maps to stay separate: adapters keep their
  own emoji/markup prefix, the choice set never changes.
"""

from __future__ import annotations

import pytest

from agent import i18n
from gateway.platforms import base_exec_approval as bea


# ---------------------------------------------------------------------------
# English must stay byte-identical -- the adapter markup composes with these
# ---------------------------------------------------------------------------

_ENGLISH_HEADER = "Hermes wants to run a command that needs your OK"
_ENGLISH_REASON_LABEL = "Why it was flagged"


@pytest.fixture
def _english(monkeypatch):
    """Force English resolution independent of the host's display.language."""
    monkeypatch.delenv("HERMES_LANGUAGE", raising=False)
    monkeypatch.setenv("HERMES_LANGUAGE", "en")
    i18n.reset_language_cache()
    yield
    i18n.reset_language_cache()


@pytest.fixture
def _chinese(monkeypatch):
    """Force Chinese resolution incl. the zh-CN alias, as a user would get."""
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    i18n.reset_language_cache()
    yield
    i18n.reset_language_cache()


def test_header_is_english_when_language_is_english(_english):
    assert bea.ea_header_text(lang="en") == _ENGLISH_HEADER


def test_reason_label_is_english_when_language_is_english(_english):
    assert bea.ea_reason_label_text(lang="en") == _ENGLISH_REASON_LABEL


def test_deadline_line_is_english_when_language_is_english(_english):
    """test_interactive_prompt_base.TestFormatExecApproval pins these substrings."""
    line = bea.format_approval_deadline_line(90, lang="en")
    assert line == "If you don't answer within 90 seconds it will NOT run."
    assert "NOT run" in bea.format_approval_deadline_line(7200, lang="en")


def test_timed_out_notice_is_english_when_language_is_english(_english):
    """tests/tools/test_approval_user_summary.py pins this via the shared formatter."""
    notice = bea.format_approval_timed_out_notice(90, lang="en")
    assert "90 seconds" in notice
    assert "NOT run" in notice


def test_english_module_constants_still_exist_for_direct_importers():
    """Adapters format ``EA_HEADER_TEXT`` at class-definition time; keep the name valid
    (English is the fallback for every surface, and adapters wrap markup around it)."""
    assert bea.EA_HEADER_TEXT == _ENGLISH_HEADER
    assert bea.EA_REASON_LABEL_TEXT == _ENGLISH_REASON_LABEL


# ---------------------------------------------------------------------------
# Chinese rendering follows display.language
# ---------------------------------------------------------------------------


def test_header_translates(_chinese):
    header = bea.ea_header_text()
    assert header != _ENGLISH_HEADER
    assert "OK" not in header


def test_reason_label_translates(_chinese):
    assert bea.ea_reason_label_text() != _ENGLISH_REASON_LABEL


def test_deadline_line_translates_and_keeps_the_localized_window(_chinese):
    line = bea.format_approval_deadline_line(300)
    assert "NOT run" not in line
    assert "minutes" not in line
    # window wording still comes from the one shared formatter, localized
    assert bea.format_approval_window_localized(300, lang="zh") in line
    assert bea.format_approval_window_localized(300, lang="zh") == "5 分钟"
    # 90s / 2h also render in Chinese units
    assert bea.format_approval_window_localized(90, lang="zh") == "90 秒"
    assert bea.format_approval_window_localized(7200, lang="zh") == "2 小时"


def test_timed_out_notice_translates(_chinese):
    notice = bea.format_approval_timed_out_notice(300)
    assert "NOT run" not in notice and "minutes" not in notice


def test_zh_alias_resolves_like_zh(_chinese):
    assert bea.ea_header_text(lang="zh-CN") == bea.ea_header_text(lang="zh")


# ---------------------------------------------------------------------------
# The label word is separate from the choice it maps to -- adapters keep their
# own prefix/emoji, and the choice set never changes.
# ---------------------------------------------------------------------------


def test_action_label_texts_are_localizable_and_keep_choices(_chinese):
    from gateway.platforms.base import BasePlatformAdapter

    for choice in ("once", "session", "always", "deny"):
        zh = bea.ea_action_label(choice, lang="zh")
        en = bea.ea_action_label(choice, lang="en")
        assert zh and en and zh != en, f"choice={choice}"


def test_english_module_label_map_is_unchanged():
    """The adapter-overridable dict keeps its English defaults."""
    from gateway.platforms.base import BasePlatformAdapter

    assert BasePlatformAdapter._EA_ACTION_LABELS == {
        "once": "Allow Once", "session": "Allow Session",
        "always": "Always Allow", "deny": "Deny"}


# ---------------------------------------------------------------------------
# Adapter markup must survive translation -- this is the invariant that keeps
# every platform's card rendering intact while the words change.
# ---------------------------------------------------------------------------


def _adapter(lang: str):
    from gateway.config import Platform, PlatformConfig
    from gateway.platforms.base import BasePlatformAdapter

    class _D(BasePlatformAdapter):
        def __init__(self):
            super().__init__(PlatformConfig(enabled=True), Platform.TELEGRAM)

        async def connect(self, *, is_reconnect: bool = False) -> bool:
            return True

        async def disconnect(self) -> None:
            return None

        async def send(self, *a, **k):
            from gateway.platforms.base import SendResult
            return SendResult(success=True)

        async def get_chat_info(self, chat_id: str):
            return {}

    adapter = _D()
    return adapter


@pytest.mark.parametrize("lang,markup", [
    ("zh", "⚠️ "), ("zh", "```"), ("ja", "⚠️ "), ("de", "⚠️ "), ("fr", "⚠️ "),
])
def test_card_markup_survives_translation(monkeypatch, lang, markup):
    monkeypatch.setenv("HERMES_LANGUAGE", lang)
    i18n.reset_language_cache()
    try:
        text = _adapter(lang)._format_exec_approval("rm -rf /tmp/x", "cleanup")
        assert markup in text, f"{markup!r} was lost in the {lang} card"
        assert "rm -rf /tmp/x" in text  # the user's command is never translated
        assert "cleanup" in text       # nor the description
    finally:
        i18n.reset_language_cache()


def test_reason_label_uses_fullwidth_colon_for_cjk(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    i18n.reset_language_cache()
    try:
        assert _adapter("zh")._ea_localize_label() == "被标记的原因： "
        assert _adapter("zh")._ea_localize_label().index("：") > 0
    finally:
        i18n.reset_language_cache()


def test_reason_label_keeps_ascii_colon_for_english(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "en")
    i18n.reset_language_cache()
    try:
        assert _adapter("en")._ea_localize_label() == "Why it was flagged: "
    finally:
        i18n.reset_language_cache()


def test_smart_deny_line_is_localized_and_still_appended(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    i18n.reset_language_cache()
    try:
        text = _adapter("zh")._format_exec_approval("rm -rf /tmp/x", "cleanup", smart_denied=True)
        assert "Smart DENY" not in text
        assert "owner override" not in text
        assert "智能拒绝" in text
        # The base adapter's "\n\n" separator before the line survives
        assert text.endswith("。")
    finally:
        i18n.reset_language_cache()


# ---------------------------------------------------------------------------
# The Feishu card is the surface the user actually sees -- drive the real
# adapter so the title, body and button row are all pinned together.
# ---------------------------------------------------------------------------


def _feishu_card(**kwargs):
    """Render a real Feishu approval card and return (title, body, buttons)."""
    import asyncio

    from gateway.config import PlatformConfig
    import plugins.platforms.feishu.adapter as feishu

    adapter = feishu.FeishuAdapter(PlatformConfig(enabled=True))
    adapter._client = object()  # non-None so the prompt renders
    captured = {}

    async def _fake_send_card(chat_id, card, meta=None, label="x", **kw):
        captured["card"] = card
        return feishu.SendResult(success=True, message_id="m1")

    adapter._send_interactive_card = _fake_send_card
    asyncio.run(adapter.send_exec_approval("oc_1", "rm -rf /tmp/x", "sess", description="cleanup", **kwargs))
    card = captured["card"]
    title = card["header"]["title"]["content"]
    body = next((el.get("content", "") for el in card["elements"] if el.get("tag") == "markdown"), "")
    buttons = [b["text"]["content"]
               for el in card["elements"] for b in el.get("actions", []) if "text" in b]
    values = [b["value"]["hermes_action"]
              for el in card["elements"] for b in el.get("actions", []) if "value" in b]
    return title, body, buttons, values


def test_feishu_card_title_body_and_buttons_are_chinese(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    i18n.reset_language_cache()
    try:
        title, body, buttons, values = _feishu_card()
        assert "Hermes wants to run" not in title
        assert "你的批准" in title
        assert "Why it was flagged" not in body
        assert "被标记的原因：" in body  # full-width colon inside the **...** markup
        assert "该命令将不会执行" in body
        assert buttons == ["✅ 允许一次", "✅ 本次会话允许", "✅ 永久允许", "❌ 拒绝"]
        # The click routing is untouched -- this is what the callback keys on.
        assert values == ["approve_once", "approve_session", "approve_always", "deny"]
        # The user's command and description never get translated
        assert "rm -rf /tmp/x" in body and "cleanup" in body
    finally:
        i18n.reset_language_cache()


def test_feishu_card_stays_english_when_language_is_english(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "en")
    i18n.reset_language_cache()
    try:
        title, body, buttons, values = _feishu_card()
        assert title == "⚠️ Hermes wants to run a command that needs your OK"
        assert body.startswith("```\nrm -rf /tmp/x\n```\n**Why it was flagged:** ")
        # The adapter keeps its own emoji prefix and short wording for en.
        assert buttons == ["✅ Allow Once", "✅ Session", "✅ Always", "❌ Deny"]
        assert values == ["approve_once", "approve_session", "approve_always", "deny"]
    finally:
        i18n.reset_language_cache()


def test_feishu_button_choice_set_never_changes(monkeypatch):
    """Only the label text moves with the language; the offered choices do not."""
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    i18n.reset_language_cache()
    try:
        _, _, _, zh_values = _feishu_card()
        _, _, _, en_values = _feishu_card()
    finally:
        i18n.reset_language_cache()
    assert zh_values == en_values


def test_feishu_smart_deny_offers_only_two_buttons(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    i18n.reset_language_cache()
    try:
        _, _, _, values = _feishu_card(allow_session=False, smart_denied=True)
        assert values == ["approve_once", "deny"]
    finally:
        i18n.reset_language_cache()


def test_fallback_text_choices_are_localizable(_chinese):
    """``/approve`` guidance lines a button-less surface sends."""
    from gateway.run import _format_exec_approval_fallback

    text = _format_exec_approval_fallback("rm -rf /tmp/x", "cleanup", "/")
    assert "Reply" not in text
    assert "to run it once" not in text
    assert "to cancel" not in text
