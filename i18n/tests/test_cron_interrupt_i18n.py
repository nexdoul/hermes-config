"""i18n coverage for the cron-interrupted notice in gateway/run_shutdown.py.

This notice told users a scheduled job was cut short by a shutdown/restart.
It was hardcoded English with three interpolated variables; it now goes
through ``agent.i18n.t``.
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


def _notice(job_name: str, restarting: bool):
    from gateway.run_shutdown import GatewayShutdownMixin

    return GatewayShutdownMixin._build_cron_interrupt_notice(
        job_name=job_name, restarting=restarting
    )


# ------------------------------------------------------------------ Chinese

def test_cron_notice_is_chinese_on_shutdown(chinese):
    msg = _notice("nightly-backup", restarting=False)
    assert "Scheduled job" not in msg
    assert "nightly-backup" in msg, "job name must survive translation"
    assert "cut short" not in msg


def test_cron_notice_is_chinese_on_restart(chinese):
    msg = _notice("nightly-backup", restarting=True)
    assert "Scheduled job" not in msg
    assert "nightly-backup" in msg


def test_chinese_notice_keeps_the_rerun_command(chinese):
    """The `hermes cron run <job>` hint must still be actionable after translation."""
    msg = _notice("nightly-backup", restarting=False)
    assert "hermes cron run" in msg
    assert "nightly-backup" in msg


def test_shutdown_and_restart_wording_differs_in_chinese(chinese):
    """The two variants must not collapse into one sentence."""
    shutdown_msg = _notice("j", restarting=False)
    restart_msg = _notice("j", restarting=True)
    assert shutdown_msg != restart_msg


# ------------------------------------------------------------------ English

def test_cron_notice_is_english_on_shutdown(english):
    msg = _notice("nightly-backup", restarting=False)
    assert "Scheduled job" in msg
    assert "nightly-backup" in msg


def test_cron_notice_is_english_on_restart(english):
    msg = _notice("nightly-backup", restarting=True)
    assert "Scheduled job" in msg


# ------------------------------------------------------------- catalog keys

@pytest.mark.parametrize("lang", ["en", "zh", "sg"])
def test_catalog_keys_resolve_in_every_supported_language(lang):
    for key in (
        "gateway.cron_interrupt.shutdown",
        "gateway.cron_interrupt.restart",
    ):
        value = i18n.t(key, lang=lang, job_name="JOB", rerun_command="hermes cron run JOB")
        assert value != key, f"{lang}:{key} fell back to the bare key"
        assert value.strip(), f"{lang}:{key} is empty"


@pytest.mark.parametrize("lang", ["en", "zh", "sg"])
def test_translated_notice_interpolates_both_variables(lang):
    """Format kwargs must land in the translated string, not stay as {braces}."""
    value = i18n.t(
        "gateway.cron_interrupt.shutdown",
        lang=lang,
        job_name="nightly-backup",
        rerun_command="hermes cron run nightly-backup",
    )
    assert "nightly-backup" in value
    assert "{" not in value and "}" not in value, f"{lang}: unsubstituted placeholder left behind"
