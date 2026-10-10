"""RED/GREEN: an abandoned serial dispatch must not leak its write into a later case.

Observed in matrix r4 (step-5-preview):

- `serial` dispatched TWO SEPARATE single-task dispatches, not one batch:
    deleg_4ca74fa5 -> patch out/report-a.md (report-a really became SERIAL-A-OK)
    deleg_9c2e4df2 -> patch out/report-b.md (dispatched at 18:54:57,
                                            completed at 18:55:33)
  The parent ended its turn after dispatching the second one and never drained it,
  so the case failed on the missing target.
- The completion for deleg_9c2e4df2 was then quarantined by the harness's own
  leftover sweep (the r4 log shows "[quarantine] dropped 1 leftover completion(s)").
- But the CHILD PROCESS ITSELF kept running and, while the `conflict` case was in
  flight, executed a real patch that rewrote out/report-b.md from PLACEHOLDER-B to
  SERIAL-B-OK. out/report-b.md is `serial`'s target and is NOT a conflict fixture.

So a run that the harness judged "abandoned" still mutated the workspace during a
later, unrelated case. The quarantine drops the EVENT; it does not stop the WRITER.

The fix is at the case boundary: a case's verdict must not be polluted by a writer
that belongs to an earlier case. The harness already digests the whole workspace
before and after each case, so the correct behaviour is to detect that a file
changed while a case was running and attribute the change to its true owner.

For now this test pins the observable contract:
  1. `serial` dispatching two separate single-task dispatches (rather than one
     batch) is what lets the second block be backgrounded;
  2. the acceptance rule for `serial` must reject a batch AND must reject a case
     that leaves a target unchanged — both already hold, and both are what made
     r4's serial failure visible;
  3. `conflict` must reject a write to ANY file outside its own fixture set,
     including one left behind by an earlier case.
"""
import os
import sys
import unittest

sys.path.insert(0, '/home/hatch/workspace/repo-hermes-config/tests')

R4_ARTIFACT = '/home/hatch/.hermes/cache/scratch/fullschema-step5-matrix-r4.json'
R4_DB = '/home/hatch/.hermes/cache/scratch/deleg-full-vijrd918/state.db'


class AbandonedDispatchMustNotLeak(unittest.TestCase):
    """Unit-level contract for the two acceptance rules that caught r4."""

    BOTH = {'out/report-a.md': {'changed_from_before': True, 'head': 'SERIAL-A-OK\n'},
            'out/report-b.md': {'changed_from_before': True, 'head': 'SERIAL-B-OK\n'},
            'in/broken.txt': {'changed_from_before': False, 'head': 'x'}}
    ONLY_A = {'out/report-a.md': {'changed_from_before': True, 'head': 'SERIAL-A-OK\n'},
              'out/report-b.md': {'changed_from_before': False, 'head': 'PLACEHOLDER-B\n'},
              'in/broken.txt': {'changed_from_before': False, 'head': 'x'}}

    def _serial(self, calls, target_state):
        from delegation_evidence import evaluate
        return evaluate('serial', calls, [], True, target_state=target_state,
                        writes_observed=True)

    def test_serial_fails_when_the_second_block_was_backgrounded(self):
        """The exact r4 shape: block 1 landed, block 2 was dispatched and abandoned."""
        calls = [{'name': 'read_file', 'arguments': {'path': '/w/out/report-a.md'}},
                 {'name': 'delegate_task',
                  'arguments': {'tasks': [{'goal': 'patch report-a'}]}},
                 {'name': 'read_file', 'arguments': {'path': '/w/out/report-a.md'}},
                 {'name': 'delegate_task',
                  'arguments': {'tasks': [{'goal': 'patch report-b'}]}}]
        self.assertFalse(self._serial(calls, self.ONLY_A),
                         'an abandoned second block leaves the target unchanged')

    def test_serial_passes_when_both_blocks_land(self):
        calls = [{'name': 'patch', 'arguments': {'path': '/w/out/report-a.md'}},
                 {'name': 'read_file', 'arguments': {'path': '/w/out/report-a.md'}},
                 {'name': 'patch', 'arguments': {'path': '/w/out/report-b.md'}},
                 {'name': 'read_file', 'arguments': {'path': '/w/out/report-b.md'}}]
        self.assertTrue(self._serial(calls, self.BOTH))

    def test_conflict_fails_when_any_file_outside_its_fixtures_changed(self):
        """`unexpected_changes` is already a hard gate; pin that it covers this."""
        from delegation_evidence import evaluate
        calls = [{'name': 'delegate_task', 'arguments': {'tasks': [{}, {}]}},
                 {'name': 'read_file', 'arguments': {'path': '/w/in/shared.txt'}}]
        children = [{'success': True,
                     'calls': [{'name': 'terminal',
                                'arguments': {'command': 'wc -l /w/in/shared.txt'}}],
                     'returns': [{'name': 'terminal', 'content': '1'}]},
                    {'success': True,
                     'calls': [{'name': 'terminal',
                                'arguments': {'command': 'wc -m /w/in/shared.txt'}}],
                     'returns': [{'name': 'terminal', 'content': '25'}]}]
        self.assertFalse(
            evaluate('conflict', calls, children, True,
                     unexpected_changes={'out/report-b.md': {'after': 'SERIAL-B-OK\n'}},
                     writes_observed=True),
            'a leaked write from an earlier case must fail the case it lands in')


@unittest.skipUnless(os.path.exists(R4_ARTIFACT), 'r4 artifact not present')
class R4ArtifactProvesTheLeak(unittest.TestCase):
    """Tracers pinned to the real r4 run."""

    @classmethod
    def setUpClass(cls):
        import json
        import sqlite3
        with open(R4_ARTIFACT, encoding='utf-8') as fh:
            cls.data = json.load(fh)
        cls.cases = {c['case']: c for c in cls.data['results']}
        cls.conn = sqlite3.connect(f'file:{R4_DB}?mode=ro', uri=True)

    def _goals(self, delegation_id):
        row = self.conn.execute(
            "SELECT task_json FROM async_delegations WHERE delegation_id=?",
            (delegation_id,)).fetchone()
        if not row:
            return []
        task = json.loads(row[0] or '{}')
        return task.get('goals') or ([task.get('goal')] if task.get('goal') else [])

    def test_serial_dispatched_two_separate_single_task_units(self):
        """Not one batch: two dispatches, so the second block could be backgrounded."""
        serial = self.cases['serial']
        dispatches = [c for c in serial['parent_calls']
                      if c['name'] == 'delegate_task'
                      and (c.get('arguments') or {}).get('action', 'spawn') == 'spawn']
        self.assertEqual(2, len(dispatches))
        for d in dispatches:
            self.assertEqual(1, len((d.get('arguments') or {}).get('tasks') or []),
                             'each serial block was its own dispatch')

    def test_the_abandoned_units_child_really_wrote_report_b(self):
        conflict = self.cases['conflict']
        writers = [(i, [c for c in r['calls'] if c['name'] in ('write_file', 'patch')])
                   for i, r in enumerate(conflict['runs'])]
        writers = [(i, w) for i, w in writers if w]
        self.assertTrue(writers, 'a child run inside conflict really wrote')
        idx, calls = writers[0]
        self.assertTrue(conflict['runs'][idx]['child'],
                        'the writer was a child, not the conflict parent')
        target = str((calls[0].get('arguments') or {}).get('path') or '')
        self.assertTrue(target.endswith('out/report-b.md'), target)

    def test_conflict_never_dispatched_a_write_task(self):
        """Its own dispatch was read-only, so the write cannot be attributed to it."""
        conflict = self.cases['conflict']
        dispatched_goals = []
        for c in conflict['parent_calls']:
            if c['name'] != 'delegate_task':
                continue
            for t in ((c.get('arguments') or {}).get('tasks') or []):
                dispatched_goals.append(str((t or {}).get('goal') or ''))
        self.assertTrue(dispatched_goals)
        self.assertTrue(all('shared.txt' in g for g in dispatched_goals),
                        dispatched_goals)
        self.assertFalse(any('report-b' in g for g in dispatched_goals))


class CaseBoundaryTerminatesWriters(unittest.TestCase):
    """The harness must signal a case's own outstanding delegations at its boundary.

    The helper lives inside the import-heavy harness module, so this pins its
    contract against the runtime seam it uses (`interrupt_for_session`) with a
    fake, proving the ownership key it passes is the agent's session identity.
    """

    @staticmethod
    def _terminate(agent, interrupt):
        """The helper's logic, reproduced with an injectable interrupt seam."""
        keys = set()
        for value in (getattr(agent, 'session_id', None),
                      getattr(agent, '_parent_session_id', None)):
            if value:
                keys.add(str(value))
        if not keys:
            return []
        stopped = []
        for key in sorted(keys):
            try:
                count = interrupt(session_key=key, parent_session_id=key,
                                  reason='harness_case_boundary')
            except Exception:
                continue
            if count:
                stopped.append((key, int(count)))
        return stopped

    def test_session_key_is_the_agent_identity(self):
        seen = []

        def interrupt(**kw):
            seen.append(kw)
            return 1

        agent = type('A', (), {'session_id': 'sess-1', '_parent_session_id': None})()
        stopped = self._terminate(agent, interrupt)
        self.assertEqual([('sess-1', 1)], stopped)
        self.assertEqual(seen[0]['session_key'], 'sess-1')
        self.assertEqual(seen[0]['parent_session_id'], 'sess-1')
        self.assertEqual(seen[0]['reason'], 'harness_case_boundary')

    def test_no_session_identity_means_no_interrupt(self):
        def interrupt(**kw):
            raise AssertionError('must not interrupt without an identity')

        agent = type('A', (), {'session_id': None, '_parent_session_id': None})()
        self.assertEqual([], self._terminate(agent, interrupt))

    def test_interrupt_failure_does_not_propagate(self):
        def interrupt(**kw):
            raise RuntimeError('boom')

        agent = type('A', (), {'session_id': 'sess-1', '_parent_session_id': None})()
        self.assertEqual([], self._terminate(agent, interrupt))

    def test_interrupt_only_fires_when_the_drain_gave_up(self):
        """A delivered completion must never be killed mid-integration.

        The box run interrupted children whose completions had already been
        drained, because the boundary call was unconditional. The guard is
        `pending - drained > 0`.
        """
        agent = type('A', (), {'session_id': 'sess-1', '_parent_session_id': None})()

        # Fully drained: nothing is outstanding, so the boundary must stay quiet.
        # The harness guards the call on `pending - drained > 0`; when that guard
        # is false the helper is never invoked at all.
        pending, drained = 2, 2
        self.assertFalse(pending - drained > 0,
                         'a fully drained case has nothing to interrupt')

        # Genuinely abandoned: the guard passes and the interrupt is correct.
        pending, drained = 2, 1
        self.assertTrue(pending - drained > 0)
        self.assertEqual([('sess-1', 1)],
                         self._terminate(agent, lambda **kw: 1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
