"""TIPS / composer placeholders / the `✦ Tip:` label follow the active language."""
from __future__ import annotations

import pytest

from agent.i18n import reset_language_cache


@pytest.fixture(autouse=True)
def _reset():
    reset_language_cache()
    yield
    reset_language_cache()


def test_tip_lists_have_stable_ids():
    from hermes_cli.tips import PLACEHOLDER_IDS, TIP_IDS
    assert len(TIP_IDS) == len(set(TIP_IDS)), "duplicate tip id"
    assert len(PLACEHOLDER_IDS) == len(set(PLACEHOLDER_IDS)), "duplicate placeholder id"
    assert len(TIP_IDS) >= 380
    assert len(PLACEHOLDER_IDS) >= 10


@pytest.mark.parametrize("lang,expected", [("en", "✦ Tip: "), ("zh", "✦ 提示：")])
def test_tip_label_localizes(lang, expected, monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", lang)
    reset_language_cache()
    from hermes_cli.tips import get_random_tip, tip_label
    assert tip_label() == expected
    assert get_random_tip()  # non-empty under every language


@pytest.mark.parametrize("getter", ["get_random_tip", "get_random_composer_placeholder"])
def test_idiom_tables_are_chinese_under_zh(getter, monkeypatch):
    """Every idiom must render in Chinese, not just some of them."""
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    reset_language_cache()
    import hermes_cli.tips as tips
    fn = getattr(tips, getter)
    table = tips.TIPS if getter == "get_random_tip" else tips.COMPOSER_PLACEHOLDERS
    seen = set()
    for _ in range(400):
        value = fn()
        seen.add(value)
        assert any("\u4e00" <= c <= "\u9fff" for c in value), (getter, value)
    assert len(seen) >= 2, "sampling never produced variety"


def test_idiom_tables_are_english_under_en(monkeypatch):
    """The English path renders unchanged -- a translated tip would break the contract."""
    monkeypatch.setenv("HERMES_LANGUAGE", "en")
    reset_language_cache()
    from hermes_cli.tips import TIP_IDS, _TIPS_BY_ID, _localized
    for tip_id in TIP_IDS:
        assert _localized(f"tips.{tip_id}", _TIPS_BY_ID[tip_id]) == _TIPS_BY_ID[tip_id]


def test_localized_falls_back_to_english_on_catalog_miss(monkeypatch):
    """A missing catalog key returns the English sentence, never the key name."""
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    reset_language_cache()
    from hermes_cli.tips import _localized
    assert _localized("tips.tip_999", "English fallback") == "English fallback"
