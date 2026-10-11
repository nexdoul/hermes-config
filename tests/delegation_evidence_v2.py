"""Project-level acceptance. Failed attempts and schema repair are not final failures."""
from delegation_evidence import evaluate, VERIFY_TOOLS

def evaluate_v2(case, calls, children, unchanged, **kw):
    if not unchanged or kw.get('unexpected_changes') or kw.get('post_verification') is False:
        return False
    delegates = [c for c in calls if c.get('name') == 'delegate_task' and (c.get('arguments') or {}).get('action', 'spawn') == 'spawn']
    verified = any(c.get('name') in VERIFY_TOOLS for c in calls)
    successful = [c for c in children if c.get('success') and c.get('calls') and c.get('returns')]
    if case in ('parallel', 'conflict'):
        return bool(any(len((c.get('arguments') or {}).get('tasks') or []) >= 2 for c in delegates)
                    and len(successful) >= 2 and verified
                    and (case != 'conflict' or not kw.get('writes_observed')))
    if case == 'serial':
        targets = kw.get('target_state') or {}
        return bool(not any(len((c.get('arguments') or {}).get('tasks') or []) >= 2 for c in delegates)
                    and verified and kw.get('writes_observed')
                    and targets.get('out/report-a.md', {}).get('head', '').strip() == 'SERIAL-A-OK'
                    and targets.get('out/report-b.md', {}).get('head', '').strip() == 'SERIAL-B-OK')
    if case.startswith('recovery_'):
        target = (kw.get('target_state') or {}).get('in/broken.txt') or {}
        return bool(len(delegates) >= 2 and successful and verified
                    and target.get('head', '') == 'RECOVERED-OK'
                    and kw.get('fault_injected'))
    return evaluate(case, calls, children, unchanged, **kw)
