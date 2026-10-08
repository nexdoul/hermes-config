"""The 💾 Self-improvement summary follows the active language.

Platform contract: adapters match on the leading 💾 emoji (see
plugins/platforms/discord/adapter.py:182), NOT on the English words, so the
label may be translated. The skill/verb tokens inside the summary are produced
by the classifier and MUST stay English -- see test_verbs_stay_english.
"""
from __future__ import annotations

from __future__ import annotations

import pytest

from agent.i18n import reset_language_cache


@pytest.fixture(autouse=True)
def _reset():
    reset_language_cache()
    yield
    reset_language_cache()


class _StubAgent:
    def __init__(self):
        self.lines = []
        self.callback_arg = None
        self.background_review_callback = self._cb

    def _cb(self, text):
        self.callback_arg = text

    def _safe_print(self, text):
        self.lines.append(text)


def test_publish_review_summary_uses_localized_label(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    reset_language_cache()
    from agent.background_review import _publish_review_summary
    agent = _StubAgent()
    _publish_review_summary(agent, ["Memory updated"])
    assert agent.lines == ["  💾 自改进复核：Memory updated"], agent.lines
    assert agent.callback_arg == "💾 自改进复核：Memory updated", agent.callback_arg


def test_publish_review_summary_english_label_unchanged(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "en")
    reset_language_cache()
    from agent.background_review import _publish_review_summary
    agent = _StubAgent()
    _publish_review_summary(agent, ["Memory updated", "Memory updated"])
    assert agent.lines == ["  💾 Self-improvement review: Memory updated"], agent.lines
    assert agent.callback_arg == "💾 Self-improvement review: Memory updated"


def test_action_lines_localize_verbs_but_keep_skill_classifier_tokens(monkeypatch):
    """`Skill 'x' patched` -> Chinese sentence, while `label` stays Skill/Memory/User profile."""
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    reset_language_cache()
    from agent.background_review import _action_lines
    data = {"success": True, "operations_applied": True, "message": "Skill 'hermes-release' patched.",
            "results": [{"action": "patch", "name": "hermes-release", "success": True}]}
    detail = {"tool": "skill_manage", "action": "patch", "name": "hermes-release"}
    lines = _action_lines(data, detail, verbose=False)
    assert lines == ["Skill「hermes-release」已打补丁"], lines
    assert "patched" not in lines[0]


def test_action_lines_memory_label_stays_english_prefix(monkeypatch):
    """`label` must stay 'Memory'/'User profile' -- _classify_review_result() parses the prefix."""
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    reset_language_cache()
    from agent.background_review import _action_lines, _classify_review_result
    data = {"success": True, "message": "Entry replaced"}
    detail = {"tool": "memory", "target": "memory", "action": "replace", "content": "x"}
    lines = _action_lines(data, detail, verbose=False)
    assert lines == ["Memory已更新"], lines
    # The classifier must keep working on the translated line.
    assert _classify_review_result(lines) == "memory", _classify_review_result(lines)


def test_verbose_skill_line_localizes(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "zh")
    reset_language_cache()
    from agent.background_review import _verbose_skill_line
    data = {"_change": {"old": "old text", "new": "new text"}}
    detail = {"action": "patch", "name": "hermes-release"}
    line = _verbose_skill_line(data, detail, "")
    assert "patched:" not in line and "📝" in line, line
