"""i18n coverage for the slash-command reply copy across 5 gateway modules.

These replies were hardcoded English f-strings/constants. They must resolve
through ``agent.i18n.t`` so ``zh``/``sg`` users see Chinese.
"""
from __future__ import annotations

import pytest

from agent import i18n

KEYS = [
    # --- gateway/platform (slash_commands.py) ---
    "gateway.platform.usage",
    "gateway.platform.tier_user",
    "gateway.platform.tier_unrestricted",
    "gateway.platform.tier_admin",
    "gateway.platform.resumed",
    "gateway.platform.paused",
    "gateway.platform.not_in_queue",
    "gateway.platform.already_retrying",
    "gateway.platform.not_enabled",
    # --- gateway/skills (slash_commands.py) ---
    "gateway.skills.write_approval_off",
    "gateway.skills.unknown_subcommand",
    "gateway.skills.admin_only",
    "gateway.skills.no_bundles",
    # --- gateway/goal (slash_commands_goals.py) ---
    "gateway.goal.requires_admin",
    "gateway.goal.no_active_goal",
    "gateway.goal.subgoal_bad_index",
    "gateway.goal.loops_unavailable",
    # --- gateway/heartbeat (slash_commands_goals.py) ---
    "gateway.heartbeat.usage",
    "gateway.heartbeat.interval_too_small",
    "gateway.heartbeat.prompt_required",
    "gateway.heartbeat.set",
    "gateway.heartbeat.agent_running",
    "gateway.heartbeat.nothing_to_pause",
    "gateway.heartbeat.nothing_to_refine",
    "gateway.heartbeat.reviewing",
    # --- gateway/session (slash_commands_session.py) ---
    "gateway.session.codex_compact_nothing",
    "gateway.session.codex_compact_done",
    "gateway.session.codex_compact_failed",
    "gateway.session.retry_unsafe",
    "gateway.session.retry_failed",
    # --- gateway/model (slash_commands_model.py) ---
    "gateway.model.switch_cancelled",
    "gateway.model.config_load_failed",
    "gateway.model.stale_override",
    "gateway.model.switch_confirm_fallback",
    # --- gateway/turn (run_turn.py) ---
    "gateway.turn.unexpected_silence",
    "gateway.turn.hint_401",
    "gateway.turn.hint_402",
    "gateway.turn.hint_529",
    "gateway.turn.hint_rate_limited",
    "gateway.turn.hint_usage_limit",
    "gateway.turn.hint_usage_limit_reset",
    "gateway.turn.hint_rejected",
    "gateway.turn.auto_reset_context",
    "gateway.turn.history_unavailable",
    "gateway.turn.agent_inactive",
]


@pytest.mark.parametrize("lang", ["en", "zh", "sg"])
@pytest.mark.parametrize("key", KEYS)
def test_catalog_keys_resolve(lang, key):
    value = i18n.t(key, lang=lang)
    assert value != key, f"{lang}:{key} fell back to the bare key"


@pytest.mark.parametrize("key", KEYS)
def test_chinese_translations_are_not_english(key):
    """zh/sg must not silently fall back to the English copy."""
    zh = i18n.t(key, lang="zh")
    en = i18n.t(key, lang="en")
    if en and any(ch.isalpha() for ch in en):
        # English copy with letters must differ from the Chinese one.
        assert zh != en, f"zh copy for {key} is identical to English"


@pytest.mark.parametrize("key", KEYS)
def test_placeholder_parity_with_english(key):
    """Any {placeholder} present in English must survive translation."""
    en = i18n.t(key, lang="en")
    for lang in ("zh", "sg", "ja", "de", "es", "fr", "pt", "ru", "ko", "it", "tr", "uk", "hu", "ar", "ga", "af", "zh-hant"):
        translated = i18n.t(key, lang=lang)
        for placeholder in _placeholders(en):
            assert placeholder in translated, f"{lang}:{key} lost {placeholder}"


def _placeholders(text: str) -> list[str]:
    import re

    return re.findall(r"\{[a-z_]+\}", text or "")
