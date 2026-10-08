"""Cron delivery wording follows the active language, while the machine-readable
contract prefixes stay byte-identical (strip_cron_wrapper parses them)."""
from __future__ import annotations

import pytest

from agent.i18n import reset_language_cache, t


@pytest.mark.parametrize("lang,expected", [
    ("en", "Cronjob Response: {name}"),
    ("zh", "定时任务回复：{name}"),
])
def test_response_header_key_exists_in_both_languages(lang, expected, monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", lang)
    reset_language_cache()
    try:
        assert t("cron.response_header", name="每日简报") == expected.format(name="每日简报")
    finally:
        reset_language_cache()


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_wrapper_keeps_contract_prefix(lang, monkeypatch):
    """`Cronjob Response: ` is a sentinel for context_compressor / yuanbao / desktop TS."""
    monkeypatch.setenv("HERMES_LANGUAGE", lang)
    reset_language_cache()
    try:
        from cron.scheduler_delivery import CRON_RESPONSE_PREFIX
        assert CRON_RESPONSE_PREFIX == "Cronjob Response: "
    finally:
        reset_language_cache()


@pytest.mark.parametrize("lang,expected_sub", [
    ("en", "To stop or manage this job"),
    ("zh", "想停止或管理这个任务"),
])
def test_manage_hint_localizes(lang, expected_sub, monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", lang)
    reset_language_cache()
    try:
        assert expected_sub in t("cron.manage_hint", name="每日简报")
        # The quoted stop phrase is part of the copy in both languages.
        assert "每日简报" in t("cron.manage_hint", name="每日简报")
    finally:
        reset_language_cache()
