"""i18n coverage for HISTORY_UNREADABLE and the slash-command reply copy.

``HISTORY_UNREADABLE`` was a module-level English constant, which froze the
language at import time. It must resolve per call through ``agent.i18n.t``.
"""
from __future__ import annotations

import pytest

from agent import i18n


@pytest.fixture
def chinese(monkeypatch):
    monkeypatch.setattr(i18n, "get_language", lambda: "zh")
    return "zh"


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setattr(i18n, "get_language", lambda: "en")
    return "en"


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_history_unreadable_is_not_frozen_at_import_time():
    """A module-level constant renders identically in every language."""
    from gateway import slash_commands_status

    i18n.reset_language_cache()
    original = i18n.get_language
    try:
        i18n.get_language = lambda: "en"
        en_value = slash_commands_status._history_unreadable()
        i18n.get_language = lambda: "zh"
        zh_value = slash_commands_status._history_unreadable()
    finally:
        i18n.get_language = original
        i18n.reset_language_cache()

    assert en_value != zh_value, "language switch had no effect — value is frozen"
    assert not _has_cjk(en_value)
    assert _has_cjk(zh_value)


def test_history_unreadable_english_keeps_operator_pointers(english):
    """The English copy must keep naming /new and `hermes doctor --fix`."""
    from gateway import slash_commands_status

    value = slash_commands_status._history_unreadable()
    assert "/new" in value
    assert "hermes doctor --fix" in value


def test_history_unreadable_key_resolves_in_all_locales():
    """Every shipped locale must carry the key (parity guard)."""
    from agent.i18n import SUPPORTED_LANGUAGES

    for lang in SUPPORTED_LANGUAGES:
        value = i18n.t("gateway.history_unreadable.notice", lang=lang)
        assert value != "gateway.history_unreadable.notice", f"{lang} fell back to bare key"
