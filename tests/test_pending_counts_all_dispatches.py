"""RED/GREEN: every dispatch must be counted, whatever turn it was made in.

Found on the 101box run (`fullschema-box-matrix-r1.json`, gpt-5.6-luna).

The harness computed `pending` from the FIRST parent run only:

    dispatches = [... for t in first_parent['returns'] if t['name'] == 'delegate_task']

The box model dispatches in a LATER turn. The artifact shows it directly:

    conflict        parent_runs=1  pend=0 drain=0  child=1   <- run1 dispatched, never waited for
    failurerecovery parent_runs=1  pend=0 drain=0  child=1   <- run1 dispatched, never waited for
    serial          parent_runs=2  pend=1 drain=1            <- run0 AND run2 dispatched
    parallel        parent_runs=2  pend=1 drain=1            <- run0 AND run4 dispatched

So a dispatch made after the first turn was invisible to the drain loop: the case
was judged on a parent turn the model never got to finish, and the new case-boundary
interrupt then killed that live child ("[subagent-0] Interrupted during API call"),
turning otherwise-passing cases into failures. The interrupt was correct; feeding it
`pending` that ignored later dispatches was the bug.

Fix: `pending` counts delegate_task returns across ALL parent runs, and the
interrupt only fires when the drain genuinely gave up (pending > drained), so a
delegation whose completion was already delivered is never killed mid-integration.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, '/home/hatch/workspace/repo-hermes-config/tests')

BOX_ARTIFACT = '/home/hatch/.hermes/cache/scratch/fullschema-box-matrix-r1.json'


def pending_from_first_run_only(case) -> int:
    """The old (buggy) computation: only the first parent run's dispatches."""
    dispatches = [json.loads(t['content']) for t in case['runs'][0]['returns']
                  if t['name'] == 'delegate_task' and isinstance(t['content'], str)
                  and t['content'].strip().startswith('{')]
    return sum(1 for d in dispatches if d.get('status') == 'dispatched')


def pending_from_all_parent_runs(case) -> int:
    """The fix: every parent run's dispatches."""
    dispatches = [json.loads(t['content']) for r in case['runs'] if not r['child']
                  for t in r['returns']
                  if t['name'] == 'delegate_task' and isinstance(t['content'], str)
                  and t['content'].strip().startswith('{')]
    return sum(1 for d in dispatches if d.get('status') == 'dispatched')


class PendingCountsEveryDispatch(unittest.TestCase):
    """Synthetic case reproducing the box shape: dispatch happens in run1, not run0."""

    def _case(self):
        return {'runs': [
            # parent run 0: no dispatch at all
            {'child': False, 'returns': [{'name': 'read_file', 'content': 'x'}]},
            # parent run 1: the dispatch happens here
            {'child': False, 'returns': [{'name': 'delegate_task',
                                          'content': '{"status": "dispatched"}'}]},
            {'child': True, 'returns': []},
        ]}

    def test_old_rule_missed_a_later_dispatch(self):
        """RED: documents the bug exactly as it fired on the box."""
        self.assertEqual(0, pending_from_first_run_only(self._case()))

    def test_new_rule_counts_it(self):
        self.assertEqual(1, pending_from_all_parent_runs(self._case()))

    def test_both_rules_agree_for_a_first_turn_dispatch(self):
        case = {'runs': [
            {'child': False, 'returns': [{'name': 'delegate_task',
                                          'content': '{"status": "dispatched"}'}]},
        ]}
        self.assertEqual(1, pending_from_first_run_only(case))
        self.assertEqual(1, pending_from_all_parent_runs(case))

    def test_child_runs_are_never_counted(self):
        case = {'runs': [
            {'child': False, 'returns': []},
            {'child': True, 'returns': [{'name': 'delegate_task',
                                         'content': '{"status": "dispatched"}'}]},
        ]}
        self.assertEqual(0, pending_from_all_parent_runs(case),
                         'a child cannot dispatch, and its returns must not count')

    def test_non_dispatched_returns_are_not_pending(self):
        case = {'runs': [
            {'child': False, 'returns': [{'name': 'delegate_task',
                                          'content': '{"status": "error"}'}]},
        ]}
        self.assertEqual(0, pending_from_all_parent_runs(case))


@unittest.skipUnless(os.path.exists(BOX_ARTIFACT), 'box artifact not present')
class BoxArtifactProvesTheDefect(unittest.TestCase):
    """Tracers pinned to the real 101box run."""

    @classmethod
    def setUpClass(cls):
        with open(BOX_ARTIFACT, encoding='utf-8') as fh:
            cls.data = json.load(fh)

    def test_some_cases_dispatched_after_the_first_parent_run(self):
        late = []
        for case in self.data['results']:
            for i, run in enumerate(case['runs']):
                if run['child'] or i == 0:
                    continue
                if any(t['name'] == 'delegate_task' for t in run['returns']):
                    late.append((case['case'], i))
        self.assertTrue(late,
                        'the box model dispatched in a later turn, which the old '
                        'pending computation could not see')

    def test_old_rule_under_reports_pending_for_those_cases(self):
        holes = []
        for case in self.data['results']:
            old = pending_from_first_run_only(case)
            new = pending_from_all_parent_runs(case)
            if new > old:
                holes.append((case['case'], old, new))
        self.assertTrue(holes,
                        'the old rule counted fewer dispatches than the model made: '
                        + repr(holes))

    def test_the_box_failures_are_consistent_with_the_defect(self):
        """Every box failure had a dispatch the old rule could not see."""
        failed = [c for c in self.data['results'] if not c['passed']]
        self.assertTrue(failed)
        for case in failed:
            self.assertGreater(pending_from_all_parent_runs(case),
                               pending_from_first_run_only(case),
                               f"{case['case']} failed with an unseen dispatch")


if __name__ == '__main__':
    unittest.main(verbosity=2)
