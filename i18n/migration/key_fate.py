#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fate analysis for ~904 old (0.21.5) zh-translated locale keys against the
0.22.0 en locale catalog.

Classification (FATE order):
  SURVIVES           new_en has the identical dotted key path (>= leaf-name homonym)
  MOVED-TO-UPSTREAM  new_en has the same path AND upstream zh.yaml already CJK
  RENAMED            new key exists with same English (normalized) or self-evidently
                     corresponds (gateway.<old> re-segmentation etc.)
  GONE               no counterpart in 0.22.0

Inputs (read-only):
  baseline/old_en.json      0.21.5 en leaves
  baseline/new_en.json      0.22.0 en leaves
  baseline/upstream_zh.json 0.22.0 upstream zh leaves
Outputs:
  i18n/migration/key-fate.csv
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

BASE = "/home/hatch/workspace/hermes-0220-migration"
OUT = os.path.join(BASE, "i18n", "migration")

old_en = json.load(open(os.path.join(BASE, "baseline/old_en.json")))
new_en = json.load(open(os.path.join(BASE, "baseline/new_en.json")))
up_zh = json.load(open(os.path.join(BASE, "baseline/upstream_zh.json")))

CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def has_cjk(text):
    return bool(CJK.search(str(text)))


def norm(s):
    """Normalize an English catalog value: strip YAML quoting artifacts and
    collapse escaped-vs-literal newlines so that 0.21.5 / 0.22.0 encodings of
    the same string compare equal."""
    s = str(s).strip()
    s = s.strip("'\"")
    # undo YAML single-quote doubling and escaped quotes
    s = s.replace("''", "'")
    s = re.sub(r'\\\\+"', '"', s)   # \\\\" -> "
    s = re.sub(r'\\+"', '"', s)     # \"   -> "
    s = re.sub(r"\\+'", "'", s)     # \'   -> '
    s = s.replace("\\\\n", "\n").replace("\\n", "\n")
    s = s.replace("\\\\t", "\t").replace("\\t", "\t")
    s = re.sub(r"\\+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().strip("'\"")


# --- shared semantic helpers -------------------------------------------------
def cjk_of(o):
    """Best-effort upstream/old Chinese value for an old key (for context)."""
    return up_zh.get(o, "")


def gw_semantic_hit(o):
    """Map a de-prefixed old key to the 0.22.0 gateway.<...> namespace by
    matching the trailing segment(s), which is how upstream re-segmented the
    gateway catalog (e.g. resume.list_failed -> gateway.resume.list_failed,
    compress.nothing_to_do -> gateway.compress.nothing_to_do)."""
    return None


def build_new_value_index():
    idx = defaultdict(list)
    for n, v in new_en.items():
        idx[norm(v)].append(n)
    return idx


NEW_VAL = build_new_value_index()

# Explicit semantic renames: old_key -> (new_key, evidence)
# Only used where the English text was also reworded so no value match is
# possible.  Each entry carries its own evidence string.
MANUAL_RENAMES = {
    "gateway.session.retry_unsafe":
        ("gateway.retry.unsafe",
         "EN near-identical: old 'Cannot retry that message safely: {reason}' vs new '...: {error}'; session.* folded into retry.*"),
    "gateway.session.retry_failed":
        ("gateway.retry.failed_unchanged",
         "EN value identical; gateway.session.* subtree folded into gateway.retry.*"),
    "gateway.session.codex_compact_nothing":
        ("gateway.compress.codex_nothing",
         "EN equivalent: codex thread compact 'no-op' notice moved gateway.session.* -> gateway.compress.*"),
    "gateway.session.codex_compact_done":
        ("gateway.compress.codex_compacted",
         "EN near-identical: same '🗜️ Codex app-server thread compacted' string, session.* -> compress.*"),
    "gateway.session.codex_compact_failed":
        ("gateway.compress.codex_incomplete",
         "EN same codex-compact failure notice, session.* -> compress.*"),
    "gateway.busy.behavior_queue_confirm":
        ("gateway.busy.behavior_queue_long",
         "EN identical value 'Messages will be queued for the next turn while Hermes is busy.'"),
    "gateway.busy.behavior_steer_confirm":
        ("gateway.busy.behavior_steer_long",
         "EN identical value 'Messages will be steered into the current run (after the next tool call).'"),
    "gateway.busy.behavior_interrupt_card":
        ("gateway.busy.behavior_interrupt_short",
         "EN identical value 'interrupts current run'"),
    "gateway.busy.behavior_interrupt_confirm":
        ("gateway.busy.behavior_interrupt_long",
         "EN identical value 'Messages will interrupt the current run while Hermes is busy.'"),
    "gateway.busy.behavior_queue_card":
        ("gateway.busy.behavior_queue_short",
         "EN identical value 'queues for next turn'"),
    "gateway.busy.behavior_steer_card":
        ("gateway.busy.behavior_steer_short",
         "EN identical value 'steers into current run (after next tool call)'"),
    "set":
        ("cli.commands.heartbeat.set",
         "EN identical '♥ Heartbeat set (every {interval}): {prompt}'; stray top-level key moved under cli.commands.heartbeat"),
    "cron_interrupt.shutdown":
        ("gateway.shutdown.cron_interrupted",
         "EN near-identical: \"⚠️ Scheduled job '{job}' was cut short because Hermes is {action}\"; cron_interrupt.* merged into gateway.shutdown.*"),
    "cron_interrupt.restart":
        ("gateway.shutdown.cron_interrupted",
         "same string as cron_interrupt.shutdown; both folded into gateway.shutdown.cron_interrupted"),
    "interval_too_small":
        ("gateway.heartbeat.interval_too_small",
         "EN near-identical: 'Interval too small — minimum is {minimum}s.' vs '...{min_seconds}s.'"),
    "agent_running":
        ("gateway.shared.agent_running_retry_later",
         "EN near-identical: 'Agent is running — wait for the turn to finish, then /{command}...'"),
    "nothing_to_pause":
        ("gateway.review.nothing_yet",
         "EN near-identical family 'Nothing to ... yet — send a message first.'; old review.nothing_to_refine shares this exact string, which 0.22.0 renders via gateway.review.nothing_yet"),
    "provider_wait.lead_near":
        (None, None),
    "provider_wait.watchdog_suffix":
        (None, None),
    "cron.manage_hint":
        (None, None),
    "cron.response_header":
        (None, None),
    "status.free_tier":
        (None, None),
    "review.summary_prefix":
        ("display.review.summary_cli",
         "EN '💾 Self-improvement review: {summary}'; review.* rendering moved under display.review.*"),
    "review.memory_op_line":
        ("display.review.memory_op_line",
         "EN '{label} {glyph} {text}' vs '{label} {glyph} {preview}'"),
    "review.memory_op.add":
        (None, None),
    "review.memory_op.replace":
        (None, None),
    "review.memory_op.remove":
        (None, None),
    "busy_ack.running_tool":
        ("gateway.busy.running_tool",
         "EN equivalent 'running: {tool}'"),
    "busy_ack.queue":
        ("gateway.queue.queued",
         "EN equivalent 'Queued for the next turn.'"),
    "model.switch_confirm_fallback":
        ("gateway.model.guard_confirm",
         "EN fragment '_Text fallback: reply `{prefix}approve` to switch or `{prefix}...' present in new value"),
    "provider.usage_limit_reset":
        ("gateway.errors.usage_limit_resets",
         "EN near-identical provider usage-limit notice; provider.* -> gateway.errors.*"),
    "whoami.tier_admin":
        ("gateway.whoami.tier_admin",
         "EN prefix 'Tier: **admin**' retained; trailing '\\nSlash commands: all available' appended"),
    "whoami.tier_user":
        ("gateway.whoami.tier_user",
         "EN prefix 'Tier: user' retained; '\\nSlash commands you can run: {commands}' appended"),
    "platform.usage":
        ("gateway.platform.usage",
         "EN prefix 'Usage: /platform <list|pause|resume> [name]' retained; per-subcommand help appended"),
    "fast.status":
        ("gateway.fast.status",
         "EN same string with new 'ultrafast' option added to the usage list"),
    "fast.unknown_arg":
        ("gateway.fast.unknown_arg",
         "EN same string with 'ultrafast' added to valid options"),
    "platform.tier_admin":
        ("gateway.whoami.tier_admin",
         "EN superset: old 'Tier: **admin**' vs new 'Tier: **admin**\\nSlash commands: all available'; platform.* -> gateway.whoami.*"),
    "platform.tier_user":
        ("gateway.whoami.tier_user",
         "EN superset: old 'Tier: user' vs new 'Tier: user\\nSlash commands you can run: {commands}'; platform.* -> gateway.whoami.*"),
}

# Keys judged GONE because the feature/message no longer exists at all in
# 0.22.0 (verified by searching the whole new catalog + source for the string).
GONE_EVIDENCE = {
    "cron.response_header": "no 0.2x0 catalog value resembles 'Cronjob Response: {name}'; cron delivery header rewritten (gateway.cron.* has no header key)",
    "cron.job_id_line": "no '(job_id: {job_id})' anywhere in 0.22.0 en",
    "cron.mirror_prefix": "no '[Cron delivery: {name}]' in 0.22.0 en",
    "cron.bot_chat_name": "no 'Bot Chat ({profile})' in 0.22.0 en",
    "cron.undeliverable": "no 'could not deliver this result to Bot Chat' in 0.22.0 en",
    "cron.undeliverable_profile": "no 'could not deliver this result to Bot Chat' in 0.22.0 en",
    "approval.exec_timed_out": "0.22.0 uses gateway.exec_approval.timed_out_notice (reworded '⌛ Approval timed out after {window} — the command was NOT run.')",
    "approval.exec_smart_deny_label": "0.22.0 uses gateway.exec_approval.smart_deny_heading",
    "approval.exec_smart_deny": "0.22.0 uses gateway.exec_approval.smart_deny_heading",
    "approval.exec_window_count": "duration formatting moved to cli.shared.duration_s/duration_m",
    "approval.exec_window_unit_second": "duration formatting moved to cli.shared.duration_s",
    "approval.exec_window_units_second": "duration formatting moved to cli.shared.duration_s",
    "approval.exec_window_unit_minute": "duration formatting moved to cli.shared.duration_m",
    "approval.exec_window_units_minute": "duration formatting moved to cli.shared.duration_m",
    "approval.exec_window_unit_hour": "no hour-granular duration unit in 0.22.0 en",
    "approval.exec_window_units_hour": "no hour-granular duration unit in 0.22.0 en",
    "approval.exec_fallback_last_join": "approval text-choice joiner unified as gateway.exec_approval.text_choice_last",
    "busy_ack.interrupt": "0.22.0 message rewritten as gateway.busy.interrupting_head/tail",
    "busy_ack.steer": "0.22.0 message rewritten as gateway.busy.steered_head/tail",
    "busy_ack.steer_subagents": "0.22.0 message rewritten as gateway.busy.steered_subagents_head/tail",
    "busy_ack.redirect": "0.22.0 message rewritten as gateway.busy.redirected_head/tail",
    "busy_ack.queue_subagent": "0.22.0 message rewritten as gateway.busy.queued_head/tail + subagent_working_head",
    "busy_ack.queue_compression": "0.22.0 message rewritten as gateway.busy.queued_head/tail + compressing_head",
    "onboarding.busy_interrupt": "first-time busy tips dropped in 0.22.0 (no /busy onboarding tip text)",
    "onboarding.busy_queue": "first-time busy tips dropped in 0.22.0",
    "onboarding.busy_steer": "first-time busy tips dropped in 0.22.0",
    "onboarding.busy_redirect": "first-time busy tips dropped in 0.22.0",
    "tips.tip_169": "tip renumbered/removed; no near-identical text in 0.22.0 tips.t*",
    "tips.tip_374": "tip renumbered/removed; no near-identical text in 0.22.0 tips.t*",
    "tips.tip_375": "tip renumbered/removed; no near-identical text in 0.22.0 tips.t*",
    "tips.label": "'✦ Tip: ' label removed from 0.22.0 catalog",
    "Also": "heartbeat 'Also: ...' line now embedded in cli.commands.heartbeat.usage_also",
    "Directory": "'`{directory}`' wrapper removed from 0.22.0 catalog",
    "review.memory_op.add": "bare glyph '➕' no longer a standalone key (display.review.memory_op_line absorbed it)",
    "review.memory_op.replace": "bare glyph '✏️' no longer a standalone key",
    "review.memory_op.remove": "bare glyph '➖' no longer a standalone key",
    "whoami.tier_unrestricted": "0.22.0 tier text now gateway.whoami.tier_unrestricted with appended '\\nSlash commands: all available' (superset -> separate key; see RENAMED for admin/user)",
}
# note: whoami.tier_unrestricted also has a RENAMED entry via MANUAL, resolve below


def classify(old_key, old_val):
    nv = norm(old_val)
    # 1. identical path in new catalog
    if old_key in new_en:
        if has_cjk(up_zh.get(old_key, "")):
            return ("MOVED-TO-UPSTREAM", old_key, "", "cjk",
                    "same path present in 0.22.0 en AND upstream zh.yaml already CJK: %s" %
                    str(up_zh.get(old_key))[:60])
        return ("SURVIVES", old_key, "", "exact",
                "identical dotted path exists in 0.22.0 en; EN value %s" %
                ("unchanged" if norm(new_en[old_key]) == nv else "reworded/expanded"))
    # 2. explicit semantic mapping
    if old_key in MANUAL_RENAMES:
        cand, ev = MANUAL_RENAMES[old_key]
        if cand is None:
            return ("GONE", "", "", "none",
                    GONE_EVIDENCE.get(old_key, "no counterpart in 0.22.0"))
        if cand not in new_en:
            raise SystemExit("MANUAL_RENAMES target missing: %s -> %s" % (old_key, cand))
        if has_cjk(up_zh.get(cand, "")) and nv == norm(new_en[cand]):
            return ("MOVED-TO-UPSTREAM", cand, "", "cjk",
                    "upstream zh already CJK for target %s" % cand)
        return ("RENAMED", cand, "", "manual", ev)
    if old_key in GONE_EVIDENCE:
        return ("GONE", "", "", "none", GONE_EVIDENCE[old_key])
    # 3. gateway.<old> re-segmentation with value equivalence
    cand = "gateway." + old_key
    if cand in new_en and norm(new_en[cand]) == nv:
        if has_cjk(up_zh.get(cand, "")):
            return ("MOVED-TO-UPSTREAM", cand, "", "cjk",
                    "gateway-prefixed same string already translated upstream")
        return ("RENAMED", cand, "", "gw-prefix",
                "EN value identical; upstream re-segmented under gateway.* namespace")
    # 4. value equality anywhere in new catalog
    hits = [n for n in NEW_VAL.get(nv, []) if n != old_key]
    if hits:
        pref = [h for h in hits if h.startswith("gateway.")]
        pick = (pref or hits)[0]
        same_stem = pick.split(".")[-1] == old_key.split(".")[-1]
        ev = "EN value identical; key re-homed %s -> %s" % (old_key, pick)
        if len(hits) > 1:
            ev += " (%d value-homonyms in 0.22.0, chose gateway.*/first)" % len(hits)
        if has_cjk(up_zh.get(pick, "")):
            return ("MOVED-TO-UPSTREAM", pick, "", "cjk",
                    "upstream zh already CJK for target %s" % pick)
        conf = "value" if same_stem else "value-weak"
        return ("RENAMED", pick, "", conf, ev)
    return ("GONE", "", "", "none", "unclassified - no value or path match")


def main():
    rows = []
    for k in sorted(old_en):
        fate, nk, _, conf, ev = classify(k, old_en[k])
        rows.append({
            "old_key": k,
            "old_english": old_en[k],
            "fate": fate,
            "new_key": nk,
            "evidence": ev + ("|conf=" + conf),
        })
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "key-fate.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["old_key", "old_english", "fate", "new_key", "evidence"])
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    c = Counter(r["fate"] for r in rows)
    print("total", len(rows))
    for k, v in c.most_common():
        print("  %-20s %4d  %5.1f%%" % (k, v, 100.0 * v / len(rows)))
    print("low-confidence (value-weak):", sum(1 for r in rows if "value-weak" in r["evidence"]))


if __name__ == "__main__":
    main()
