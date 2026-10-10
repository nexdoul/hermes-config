"""i18n coverage for gateway/run.py's provider-error and turn-failure copy.

These replies used to be hardcoded English in module-level constants and
f-strings. Module-level constants freeze the language at import time, so the
fix is call-time resolution through ``agent.i18n.t``.

Both languages are asserted for every surface: the English path must render
unchanged (these are the strings users were reading before), and the Chinese
path must not leak English.
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


def _is_ascii_only(text: str) -> bool:
    """True when the string carries no CJK — used to prove a language switch took effect.

    Emoji and em-dashes are allowed in both languages; only CJK codepoints count.
    """
    return not any(
        "\u3000" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef" or "\u4e00" <= ch <= "\u9fff"
        for ch in text
    )


# --------------------------------------------------------------------------
# Provider error replies (_PROVIDER_ERROR_REPLIES + the two helpers)
# --------------------------------------------------------------------------

def _provider_replies():
    from gateway import run

    return run._PROVIDER_ERROR_REPLIES()


def test_provider_replies_are_english_by_default(english):
    """The table must still resolve to the original English sentences."""
    replies = [reply for _pattern, reply in _provider_replies()]
    assert any("Sign-in to the AI model service failed" in r for r in replies)
    assert any("The AI model service rejected this request" in r for r in replies)
    assert any("isn't reachable right now" in r for r in replies)


def test_provider_replies_are_chinese_when_language_is_chinese(chinese):
    replies = [reply for _pattern, reply in _provider_replies()]
    assert not any("Sign-in to the AI model service failed" in r for r in replies)
    assert any("登录" in r or "签名" in r or "身份" in r for r in replies), (
        "no Chinese found in any provider reply"
    )


def test_provider_replies_are_not_frozen_at_import_time():
    """A module-level constant would render the same in both languages.

    Resolution must happen per call, so flipping the language changes output.
    """
    from agent import i18n
    from gateway import run

    i18n.reset_language_cache()
    original = i18n.get_language
    try:
        i18n.get_language = lambda: "en"
        en_replies = [r for _p, r in run._PROVIDER_ERROR_REPLIES()]
        i18n.get_language = lambda: "zh"
        chinese_replies = [r for _p, r in run._PROVIDER_ERROR_REPLIES()]
    finally:
        i18n.get_language = original
        i18n.reset_language_cache()

    assert en_replies != chinese_replies, "language switch had no effect — value is frozen"
    assert all(_is_ascii_only(r) for r in en_replies)
    assert not any(_is_ascii_only(r) for r in chinese_replies)


def test_provider_reply_table_keeps_its_pattern_pairs(english):
    """The (pattern, reply) shape and ordering must survive the refactor."""
    from gateway import run

    table = run._PROVIDER_ERROR_REPLIES()
    assert len(table) == 6, f"expected 6 pattern/reply pairs, got {len(table)}"
    for pattern, reply in table:
        assert hasattr(pattern, "search"), "first element must stay a compiled regex"
        assert isinstance(reply, str) and reply.strip()


# --------------------------------------------------------------------------
# _rate_limit_reply — the two quota variants
# --------------------------------------------------------------------------

def test_rate_limit_reply_english_short_window(english):
    from gateway.run import _rate_limit_reply

    text = _rate_limit_reply("rate limited, retry after 30s")
    assert "rate-limiting requests" in text


def test_rate_limit_reply_english_long_window_keeps_the_reset_window(english):
    from gateway.run import _rate_limit_reply

    text = _rate_limit_reply("quota exhausted, resets in 4hr")
    assert "usage limit is reached" in text
    assert "4" in text, "the computed reset window must survive translation"


def test_rate_limit_reply_chinese(chinese):
    from gateway.run import _rate_limit_reply

    text = _rate_limit_reply("rate limited, retry after 30s")
    assert "rate-limiting requests" not in text


def test_rate_limit_reply_chinese_long_window(chinese):
    from gateway.run import _rate_limit_reply

    text = _rate_limit_reply("quota exhausted, resets in 4hr")
    assert "usage limit is reached" not in text
    assert "4" in text, "the computed reset window must survive translation"


# --------------------------------------------------------------------------
# _gateway_provider_error_reply — the catch-all
# --------------------------------------------------------------------------

def test_provider_error_catchall_english(english):
    from gateway.run import _gateway_provider_error_reply

    text = _gateway_provider_error_reply("api call failed: something odd")
    assert "kept failing" in text
    assert "/retry" in text


def test_provider_error_catchall_chinese(chinese):
    from gateway.run import _gateway_provider_error_reply

    text = _gateway_provider_error_reply("api call failed: something odd")
    assert "kept failing" not in text
    assert "/retry" in text, "the /retry hint must survive translation"


# --------------------------------------------------------------------------
# _CONTEXT_OVERFLOW_REPLY
# --------------------------------------------------------------------------

def test_context_overflow_reply_english(english):
    from gateway import run

    text = run._context_overflow_reply()
    assert "grown too long" in text
    assert "/compress" in text


def test_context_overflow_reply_chinese(chinese):
    from gateway import run

    text = run._context_overflow_reply()
    assert "grown too long" not in text
    assert "/compress" in text


# --------------------------------------------------------------------------
# catalog keys must exist and interpolate
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "zh", "sg"])
@pytest.mark.parametrize(
    "key",
    [
        "gateway.provider.auth_failed",
        "gateway.provider.provider_policy",
        "gateway.provider.connection_interrupted",
        "gateway.provider.endpoint_unreachable",
        "gateway.provider.connection_error",
        "gateway.provider.rate_limited",
        "gateway.provider.usage_limit_reset",
        "gateway.provider.kept_failing",
        "gateway.context_overflow.overflow_reply",
        ],
)
def test_catalog_keys_resolve(lang, key):
    value = i18n.t(key, lang=lang)
    assert value != key, f"{lang}:{key} fell back to the bare key"
    assert value.strip(), f"{lang}:{key} is empty"


@pytest.mark.parametrize("lang", ["en", "zh", "sg"])
def test_usage_limit_reset_interpolates_the_window(lang):
    """The computed reset window is a variable; it must land in the string."""
    value = i18n.t("gateway.provider.usage_limit_reset", lang=lang, reset_window="4 hours")
    assert "4 hours" in value, f"{lang}: reset_window not interpolated"
    assert "{" not in value and "}" not in value, f"{lang}: unsubstituted placeholder"
