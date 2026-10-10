"""i18n coverage for the gateway shutdown/restart notices.

These notices used to be hardcoded English in ``gateway/run_shutdown.py``.
They must now go through ``agent.i18n.t`` so ``zh``/``sg`` users see Chinese.
"""

from __future__ import annotations

import pytest

from agent import i18n


@pytest.fixture
def chinese(monkeypatch):
    """Force the active language to Chinese for the duration of a test."""
    monkeypatch.setattr(i18n, "get_language", lambda: "zh")
    return "zh"


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setattr(i18n, "get_language", lambda: "en")
    return "en"


def _notice_texts():
    """Build both notices exactly the way ``run_shutdown`` does."""
    from gateway.run_shutdown import GatewayShutdownMixin

    return GatewayShutdownMixin._build_notice_messages()


# ---------------------------------------------------------------- RED first

def test_shutdown_notice_is_chinese(chinese):
    shutdown_msg, _restart_msg = _notice_texts()
    assert "Hermes is shutting down" not in shutdown_msg
    assert "正在关闭" in shutdown_msg


def test_restart_notice_is_chinese(chinese):
    _shutdown_msg, restart_msg = _notice_texts()
    assert "Hermes is restarting" not in restart_msg
    assert "正在重启" in restart_msg


# ------------------------------------------------------- English still works

def test_shutdown_notice_is_english(english):
    shutdown_msg, _restart_msg = _notice_texts()
    assert "Hermes is shutting down" in shutdown_msg


def test_restart_notice_is_english(english):
    _shutdown_msg, restart_msg = _notice_texts()
    assert "Hermes is restarting" in restart_msg


# ------------------------------------------------------------- catalog keys

def test_catalog_keys_exist_and_are_translated():
    """Both keys must resolve in zh and sg, not fall back to the bare key."""
    for lang in ("zh", "sg"):
        for key in (
            "gateway.shutdown_notice.shutting_down",
            "gateway.shutdown_notice.restarting",
        ):
            value = i18n.t(key, lang=lang)
            assert value != key, f"{lang}:{key} fell back to the bare key"
            assert value.strip(), f"{lang}:{key} is empty"


def test_notices_are_not_identical_across_languages():
    """Guards against a copy-paste that makes zh identical to en."""
    en_s, en_r = (i18n.t(k, lang="en") for k in
                  ("gateway.shutdown_notice.shutting_down",
                   "gateway.shutdown_notice.restarting"))
    zh_s, zh_r = (i18n.t(k, lang="zh") for k in
                  ("gateway.shutdown_notice.shutting_down",
                   "gateway.shutdown_notice.restarting"))
    assert en_s != zh_s
    assert en_r != zh_r
