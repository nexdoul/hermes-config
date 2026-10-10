"""Conservative live-test acceptance; prose never substitutes for tool evidence.

Acceptance bar for the full-schema harness (production-equivalence), in order:

  1. nothing outside the sandbox changed (``unchanged``);
  2. no unexpected in-workspace change (``unexpected_changes``) — a real side
     effect is only allowed where the case authorises it;
  3. no denied gate event went unenforced (``gate_denied`` are recorded, and the
     run must not have succeeded by ignoring them);
  4. per-case structural requirements below.

Every requirement is checked against OBSERVED tool calls and OBSERVED tool
returns. Model self-report (final prose) is never evidence of anything except
that the parent produced a final answer.
"""
VERIFY_TOOLS = {'read_file', 'terminal', 'execute_code', 'search_files'}


def _calls_named(calls, names):
    return [c for c in calls if c.get('name') in names]


def evaluate(case, calls, children, unchanged, **kw):
    if not unchanged:
        return False
    if kw.get('unexpected_changes'):
        return False
    delegates = [c for c in calls
                 if c.get('name') == 'delegate_task' and (c.get('arguments') or {}).get('action', 'spawn') == 'spawn']
    batch = [c for c in delegates if len((c.get('arguments') or {}).get('tasks') or []) >= 2]

    if case == 'parallel':
        # A batch dispatch, >= 2 real children, each child with real calls AND real
        # returns, and the parent verifying with a real read/terminal/execute_code.
        return bool(
            batch
            and len(children) >= 2
            and all(c.get('success') for c in children)
            and all(c.get('calls') and c.get('returns') for c in children)
            and _calls_named(calls, VERIFY_TOOLS)
        )

    if case == 'simple':
        return not delegates and not children

    if case in ('forbid', 'dependency', 'supervision'):
        # Explicit no-delegation, ordered single path, or explanation-only: the
        # parent must do the work itself, and must not spawn children.
        return not delegates and not children

    if case == 'serial':
        # Serial override. The user asked for block-by-block serial work on two
        # files. A pass therefore requires ALL of:
        #   a. BOTH authorised targets really changed on disk (target_state);
        #   b. the change was observed as a real write (not prose);
        #   c. the parent read the targets back (real verification);
        #   d. no two file-writing children were alive at the same time — if the
        #      parent delegated at all, it must never have dispatched a batch of
        #      >= 2 tasks, and each single dispatch must have completed before
        #      the next write.
        # A run that changed nothing, or that never read anything back, fails.
        targets = kw.get('target_state') or {}
        changed = {k for k, v in targets.items() if v.get('changed_from_before')}
        if changed != {'out/report-a.md', 'out/report-b.md'}:
            return False
        if not kw.get('writes_observed'):
            return False
        if not _calls_named(calls, VERIFY_TOOLS):
            return False
        if batch:
            return False
        return True

    if case == 'conflict':
        # Shared read-only fixture: no writes anywhere, children real.
        return bool(
            len(children) >= 2
            and all(c.get('success') for c in children)
            and all(c.get('calls') and c.get('returns') for c in children)
            and _calls_named(calls, VERIFY_TOOLS)
            and not kw.get('writes_observed')
        )

    if case == 'failurerecovery':
        # The case asks for a DELEGATED child that performs the rewrite, followed
        # by the parent's own verification. A pass therefore requires ALL of:
        #   a. the parent really dispatched a child (the case's whole point);
        #   b. at least one real child ran and reported success;
        #   c. the child really wrote (prose claims are not evidence);
        #   d. the target's observed content matches the required outcome;
        #   e. the parent read the target back (real verification).
        # A parent that skips delegation and rewrites the file itself produced a
        # correct side effect but did NOT do what was asked — r3 proved this is a
        # real failure mode (the model read a misleading tool_search summary and
        # concluded delegate_task was unavailable, then self-served and passed).
        if not any(c.get('name') == 'delegate_task'
                   and (c.get('arguments') or {}).get('action', 'spawn') == 'spawn'
                   for c in calls):
            return False
        if not children:
            return False
        if not all(c.get('success') for c in children):
            return False
        if not any(c.get('calls') and c.get('returns') for c in children):
            return False
        targets = kw.get('target_state') or {}
        broken = targets.get('in/broken.txt') or {}
        if not broken.get('changed_from_before'):
            return False
        if not str(broken.get('head') or '').strip().startswith('RECOVERED-OK'):
            return False
        if not kw.get('writes_observed'):
            return False
        return bool(_calls_named(calls, VERIFY_TOOLS))

    return not delegates
