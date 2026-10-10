"""Unit acceptance tests for the delegation evidence predicate.

The predicate is the mission's only gate between "the model said so" and
"real tool evidence exists". Every branch below is asserted against OBSERVED
call/return records, never against prose.
"""
import unittest

from delegation_evidence import evaluate


def _child(success=True, calls=None, returns=None):
    return {'success': success,
            'calls': calls if calls is not None else [{'name': 'read_file'}],
            'returns': returns if returns is not None else [{'name': 'read_file'}]}


def _delegate(n=2, action='spawn'):
    return {'name': 'delegate_task', 'arguments': {'action': action, 'tasks': [{} for _ in range(n)]}}


def _read():
    return {'name': 'read_file', 'arguments': {'path': 'x'}}


class ParallelEvidenceTests(unittest.TestCase):
    def test_self_report_is_not_parallel_evidence(self):
        self.assertFalse(evaluate('parallel', [], [], True))

    def test_dispatch_plus_prose_is_not_enough(self):
        self.assertFalse(evaluate('parallel', [_delegate()], [_child(), _child()], True),
                         'dispatch and child final prose are not real-action evidence')

    def test_batch_dispatch_with_real_children_and_parent_verification_passes(self):
        calls = [_delegate(3), _read()]
        children = [_child() for _ in range(3)]
        self.assertTrue(evaluate('parallel', calls, children, True))

    def test_single_task_dispatch_is_not_parallel(self):
        self.assertFalse(evaluate('parallel', [_delegate(1), _read()], [_child()], True))

    def test_one_child_is_not_parallel(self):
        self.assertFalse(evaluate('parallel', [_delegate(2), _read()], [_child()], True))

    def test_failed_child_is_not_success(self):
        self.assertFalse(evaluate('parallel', [_delegate(2), _read()],
                                  [_child(), _child(success=False)], True))

    def test_child_with_calls_but_no_returns_is_not_evidence(self):
        self.assertFalse(evaluate('parallel', [_delegate(2), _read()],
                                  [_child(returns=[]), _child()], True))

    def test_parent_must_verify_with_a_real_tool(self):
        self.assertFalse(evaluate('parallel', [_delegate(2)], [_child(), _child()], True))

    def test_control_action_is_not_a_dispatch(self):
        calls = [{'name': 'delegate_task', 'arguments': {'action': 'list'}}, _read()]
        self.assertFalse(evaluate('parallel', calls, [_child(), _child()], True))


class NegativeCaseTests(unittest.TestCase):
    def test_simple_must_not_delegate(self):
        self.assertFalse(evaluate('simple', [_delegate()], [], True))

    def test_simple_with_no_calls_passes(self):
        self.assertTrue(evaluate('simple', [], [], True))

    def test_forbid_must_not_delegate(self):
        self.assertFalse(evaluate('forbid', [_delegate()], [_child()], True))

    def test_forbid_done_inline_passes(self):
        self.assertTrue(evaluate('forbid', [_read()], [], True))

    def test_dependency_must_not_delegate(self):
        self.assertFalse(evaluate('dependency', [_delegate()], [_child()], True))

    def test_supervision_must_not_delegate(self):
        self.assertFalse(evaluate('supervision', [_delegate()], [_child()], True))


class SafetyTests(unittest.TestCase):
    def test_files_must_remain_unchanged(self):
        self.assertFalse(evaluate('simple', [], [], False))

    def test_unexpected_workspace_change_is_a_failure(self):
        self.assertFalse(evaluate('parallel', [_delegate(2), _read()], [_child(), _child()], True,
                                  unexpected_changes={'in/shared.txt': {}}))

    def test_conflict_case_forbids_any_observed_write(self):
        children = [_child() for _ in range(2)]
        self.assertTrue(evaluate('conflict', [_delegate(2), _read()], children, True,
                                 writes_observed=False))
        self.assertFalse(evaluate('conflict', [_delegate(2), _read()], children, True,
                                  writes_observed=True))

    def test_serial_and_failurerecovery_require_observed_verification(self):
        # Strengthened bar: reads alone are NOT enough — the authorised targets
        # must really have changed on disk and the change must be an observed
        # write. See test_delegation_evidence_side_effects.py for the full matrix.
        serial_ok = {'out/report-a.md': {'changed_from_before': True, 'head': 'SERIAL-A-OK\n'},
                     'out/report-b.md': {'changed_from_before': True, 'head': 'SERIAL-B-OK\n'},
                     'in/broken.txt': {'changed_from_before': False, 'head': 'x'}}
        recovered = {'out/report-a.md': {'changed_from_before': False, 'head': 'x'},
                     'out/report-b.md': {'changed_from_before': False, 'head': 'x'},
                     'in/broken.txt': {'changed_from_before': True, 'head': 'RECOVERED-OK\n'}}
        delegated = [{'name': 'delegate_task',
                      'arguments': {'tasks': [{'goal': 'rewrite broken.txt'}]}}]
        child = [{'success': True,
                  'calls': [{'name': 'write_file'}],
                  'returns': [{'name': 'write_file', 'content': 'ok'}]}]
        # no read at all -> fail
        self.assertFalse(evaluate('serial', [], [], True, target_state=serial_ok,
                                  writes_observed=True))
        self.assertFalse(evaluate('failurerecovery', [], [], True, target_state=recovered,
                                  writes_observed=True))
        # read but nothing changed on disk -> fail (the old rule passed this)
        self.assertFalse(evaluate('serial', [_read()], [], True, target_state=serial_ok,
                                  writes_observed=False))
        self.assertFalse(evaluate('failurerecovery', [_read()], [], True,
                                  target_state=recovered, writes_observed=False))
        # real change + real read -> pass
        self.assertTrue(evaluate('serial', [_read()], [], True, target_state=serial_ok,
                                 writes_observed=True))
        self.assertTrue(evaluate('failurerecovery', delegated + [_read()], child, True,
                                 target_state=recovered, writes_observed=True))


if __name__ == '__main__':
    unittest.main()
