"""Strengthened acceptance for the side-effect cases: no prose-only passes.

RED/GREEN record:
  RED   - the previous `serial` rule was `bool(_calls_named(calls, VERIFY_TOOLS))`,
          which a run that changed NOTHING and only read files satisfied.
          test_serial_requires_real_target_change FAILED against that rule.
          The previous `failurerecovery` rule had the same hole.
  GREEN - after requiring the observed on-disk target state, both hold.
"""
import unittest
from delegation_evidence import evaluate

VERIFY = [{'name': 'read_file', 'arguments': {'path': '/ws/out/report-a.md'}}]
BOTH_CHANGED = {
    'out/report-a.md': {'changed_from_before': True, 'head': 'SERIAL-A-OK\n'},
    'out/report-b.md': {'changed_from_before': True, 'head': 'SERIAL-B-OK\n'},
    'in/broken.txt': {'changed_from_before': False, 'head': 'PLACEHOLDER\n'},
}
RECOVERED = {
    'out/report-a.md': {'changed_from_before': False, 'head': 'PLACEHOLDER\n'},
    'out/report-b.md': {'changed_from_before': False, 'head': 'PLACEHOLDER\n'},
    'in/broken.txt': {'changed_from_before': True, 'head': 'RECOVERED-OK\n'},
}


class SerialAcceptanceTests(unittest.TestCase):
    def test_serial_requires_real_target_change(self):
        """Reading files without changing anything must NOT pass serial."""
        self.assertFalse(
            evaluate('serial', VERIFY, [], True, target_state=BOTH_CHANGED,
                     writes_observed=False),
            'reads alone are not a completed serial edit')

    def test_serial_requires_both_targets(self):
        one = dict(BOTH_CHANGED)
        one['out/report-b.md'] = {'changed_from_before': False, 'head': 'PLACEHOLDER-B\n'}
        self.assertFalse(
            evaluate('serial', VERIFY, [], True, target_state=one, writes_observed=True),
            'only one of the two authorised targets changed')

    def test_serial_rejects_parallel_batch_dispatch(self):
        calls = [{'name': 'delegate_task',
                  'arguments': {'tasks': [{'goal': 'a'}, {'goal': 'b'}]}}]
        self.assertFalse(
            evaluate('serial', calls + VERIFY, [], True, target_state=BOTH_CHANGED,
                     writes_observed=True),
            'a >=2-task batch is parallel, not serial')

    def test_serial_accepts_real_serial_work(self):
        calls = [{'name': 'patch', 'arguments': {'path': '/ws/out/report-a.md'}},
                 {'name': 'read_file', 'arguments': {'path': '/ws/out/report-a.md'}},
                 {'name': 'patch', 'arguments': {'path': '/ws/out/report-b.md'}},
                 {'name': 'read_file', 'arguments': {'path': '/ws/out/report-b.md'}}]
        self.assertTrue(
            evaluate('serial', calls, [], True, target_state=BOTH_CHANGED,
                     writes_observed=True))


class FailureRecoveryAcceptanceTests(unittest.TestCase):
    """The case's subject is a DELEGATED child that performs the rewrite.

    Strengthened in r3: the previous rule checked only the observed side effect,
    so a parent that never delegated (and rewrote the file itself) passed. That
    is exactly what happened in matrix r3 — see
    test_failurerecovery_requires_delegation.py for the artifact tracers.
    """

    DELEGATED = [{'name': 'delegate_task', 'arguments': {'tasks': [{'goal': 'rewrite broken.txt'}]}}]
    CHILD = [{'success': True,
              'calls': [{'name': 'write_file',
                         'arguments': {'path': '/ws/in/broken.txt'}}],
              'returns': [{'name': 'write_file', 'content': 'ok'}]}]

    def test_failurerecovery_requires_a_real_delegated_child(self):
        """Self-performed recovery, however correct, is not what was asked."""
        self.assertFalse(
            evaluate('failurerecovery', VERIFY, [], True, target_state=RECOVERED,
                     writes_observed=True),
            'a parent that did the work itself must not pass a delegation case')

    def test_failurerecovery_requires_a_successful_child(self):
        self.assertFalse(
            evaluate('failurerecovery', self.DELEGATED + VERIFY,
                     [{'success': False, 'calls': [{'name': 'write_file'}],
                       'returns': [{'name': 'write_file', 'content': 'err'}]}],
                     True, target_state=RECOVERED, writes_observed=True),
            'a failed child is not a recovery')

    def test_failurerecovery_requires_a_child_that_really_acted(self):
        self.assertFalse(
            evaluate('failurerecovery', self.DELEGATED + VERIFY,
                     [{'success': True, 'calls': [], 'returns': []}],
                     True, target_state=RECOVERED, writes_observed=True),
            'child prose is not an observed write')

    def test_failurerecovery_requires_real_write_and_readback(self):
        self.assertFalse(
            evaluate('failurerecovery', self.DELEGATED + VERIFY, self.CHILD, True,
                     target_state=RECOVERED, writes_observed=False),
            'no observed write means nothing was recovered')

    def test_failurerecovery_requires_unchanged_target_to_change(self):
        unchanged = {k: dict(v) for k, v in RECOVERED.items()}
        unchanged['in/broken.txt'] = {'changed_from_before': False, 'head': 'broken\n'}
        self.assertFalse(
            evaluate('failurerecovery', self.DELEGATED + VERIFY, self.CHILD, True,
                     target_state=unchanged, writes_observed=True),
            'the target file never changed')

    def test_failurerecovery_requires_correct_content(self):
        wrong = {k: dict(v) for k, v in RECOVERED.items()}
        wrong['in/broken.txt'] = {'changed_from_before': True, 'head': 'STILL-BROKEN\n'}
        self.assertFalse(
            evaluate('failurerecovery', self.DELEGATED + VERIFY, self.CHILD, True,
                     target_state=wrong, writes_observed=True),
            'content does not match the required outcome')

    def test_failurerecovery_accepts_real_recovery(self):
        self.assertTrue(
            evaluate('failurerecovery', self.DELEGATED + VERIFY, self.CHILD, True,
                     target_state=RECOVERED, writes_observed=True))


class UnchangedGateTests(unittest.TestCase):
    def test_protected_change_always_fails(self):
        self.assertFalse(evaluate('serial', VERIFY, [], False,
                                  target_state=BOTH_CHANGED, writes_observed=True))

    def test_unexpected_workspace_change_always_fails(self):
        self.assertFalse(evaluate('serial', VERIFY, [], True,
                                  unexpected_changes={'in/timer.txt': {}},
                                  target_state=BOTH_CHANGED, writes_observed=True))


if __name__ == '__main__':
    unittest.main(verbosity=2)
