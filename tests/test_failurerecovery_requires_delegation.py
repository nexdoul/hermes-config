"""RED/GREEN: the delegation case must not let a misleading tool_search reply
falsely report that delegation is unavailable.

Observed in matrix r3 (`failurerecovery`, step-5-preview): the agent's own tool
schemas DID contain delegate_task (34 schemas, `delegate_task` among them, zero
gate denies), yet the model called tool_search, got a reply whose
`available_sources` listed only the 4 DEFERRED tools
(cronjob / session_search / terminal / todo), and concluded in its final answer:

    "delegate_task 在当前会话不可用（可用工具源仅 cronjob / session_search /
     terminal / todo）"

That conclusion was false and the harness did not catch it, because the case's
acceptance only checked "did the target file change and was it read back".
So a run in which delegation was never exercised passed the failure-recovery
case by doing the work itself.

Root cause of the misleading reply (runtime, verified by reproduction):
`_available_source_summary(catalog)` is built from the DEFERRABLE subset only,
so every eagerly-visible tool is invisible to it. In the sandbox config the
curated defer list defers 4 plugin tools; the other 31 (including delegate_task,
source ('plugin','delegation')) stay eager and therefore never appear in
`available_sources`. The summary is correct for production discovery but is
easily misread as "these are the only tools I have".

The fix belongs in the harness, not the runtime: the case must assert that the
parent actually DELEGATED, so a run that silently falls back to doing the work
itself fails loudly instead of passing on a side effect.
"""
import os
import sys
import unittest

sys.path.insert(0, '/home/hatch/workspace/repo-hermes-config/tests')

R3_ARTIFACT = '/home/hatch/.hermes/cache/scratch/fullschema-step5-matrix-r3.json'


class FailureRecoveryRequiresRealDelegation(unittest.TestCase):
    """The case asks for delegation; a self-performed rescue must not pass silently."""

    def _run(self, *, delegated, target_changed, head, writes_observed):
        from delegation_evidence import evaluate
        calls = ([{'name': 'delegate_task', 'arguments': {'tasks': [{'goal': 'x'}]}},
                  {'name': 'read_file', 'arguments': {'path': '/w/in/broken.txt'}}]
                 if delegated else
                 [{'name': 'read_file', 'arguments': {'path': '/w/in/broken.txt'}},
                  {'name': 'write_file', 'arguments': {'path': '/w/in/broken.txt'}}])
        children = ([{'success': True,
                      'calls': [{'name': 'write_file',
                                 'arguments': {'path': '/w/in/broken.txt'}}],
                      'returns': [{'name': 'write_file', 'content': 'ok'}]}]
                    if delegated else [])
        return evaluate(
            'failurerecovery', calls, children, True,
            writes_observed=writes_observed,
            target_state={'in/broken.txt': {
                'changed_from_before': target_changed,
                'head': head,
            }})

    def test_real_delegation_with_recovery_passes(self):
        self.assertTrue(self._run(delegated=True, target_changed=True,
                                  head='RECOVERED-OK\n', writes_observed=True))

    def test_self_performed_recovery_without_delegation_fails(self):
        """The r3 shape: correct side effect, but delegation never happened."""
        self.assertFalse(
            self._run(delegated=False, target_changed=True,
                      head='RECOVERED-OK\n', writes_observed=True),
            'a parent that did the work itself must not satisfy a case that '
            'asked for a delegated child')

    def test_delegated_but_unchanged_target_fails(self):
        self.assertFalse(self._run(delegated=True, target_changed=False,
                                   head='old', writes_observed=True))

    def test_delegated_but_wrong_content_fails(self):
        self.assertFalse(self._run(delegated=True, target_changed=True,
                                   head='STILL-BROKEN\n', writes_observed=True))


@unittest.skipUnless(os.path.exists(R3_ARTIFACT), 'r3 artifact not present')
class R3ArtifactShowsTheFalseUnavailableClaim(unittest.TestCase):
    """Tracer pinned to the real r3 run that produced the false conclusion."""

    @classmethod
    def setUpClass(cls):
        import json
        with open(R3_ARTIFACT, encoding='utf-8') as fh:
            cls.data = json.load(fh)
        cls.case = next(c for c in cls.data['results']
                        if c['case'] == 'failurerecovery')

    def test_delegate_task_was_in_the_schemas_the_model_saw(self):
        self.assertIn('delegate_task', self.case['parent_schemas'],
                      'the tool really was offered to the model')

    def test_the_model_nevertheless_claimed_it_was_unavailable(self):
        tail = self.case['final_response_tail']
        self.assertIn('delegate_task', tail)
        self.assertIn('不可用', tail,
                      'the model reported delegation as unavailable')

    def test_no_child_ever_ran(self):
        self.assertEqual(0, self.case['child_runs'])

    def test_the_side_effect_was_real_even_so(self):
        self.assertTrue(self.case['writes_observed'])
        broken = (self.case['target_state'] or {}).get('in/broken.txt') or {}
        self.assertTrue(broken.get('changed_from_before'))
        self.assertTrue(str(broken.get('head') or '').strip().startswith('RECOVERED-OK'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
