"""RED/GREEN: acceptance must see every parent call, in every turn.

The old rule was `first_turn_calls + last_turn_calls[len(first_turn_calls):]`.
That is only correct for a two-turn parent, because run_conversation replays the
whole conversation into each later record. With three turns, the middle turn's
calls are dropped.

GREEN: acceptance_calls is every parent call, de-duplicated by call_id.
RED:   the old slice loses the middle turn's verification call.
"""
import sys
import unittest

sys.path.insert(0, '/home/hatch/workspace/repo-hermes-config/tests')


def acceptance_calls_new(records):
    """The rule now in the harness: every parent call, call_id de-duplicated."""
    seen, out = set(), []
    for r in records:
        if r['child']:
            continue
        for c in r['calls']:
            cid = c.get('call_id')
            if cid is not None:
                if cid in seen:
                    continue
                seen.add(cid)
            out.append(c)
    return out


def acceptance_calls_old(records):
    """The rule that was in the harness until this iteration."""
    first_parent = records[0]
    last_parent = records[-1]
    pending = sum(1 for r in records if not r['child']
                  for t in r['returns'] if t['name'] == 'delegate_task')
    if not pending:
        return list(first_parent['calls'])
    last_parent = dict(last_parent)
    last_parent['calls'] = last_parent['calls'][len(first_parent['calls']):]
    return list(first_parent['calls']) + list(last_parent.get('calls') or [])


def _call(name, cid):
    return {'name': name, 'call_id': cid, 'arguments': {}}


class ThreeTurnParent(unittest.TestCase):
    """Dispatch in turn 0, verify in turn 1, answer in turn 2."""

    def _records(self):
        return [
            {'child': False, 'calls': [_call('delegate_task', 'c1')],
             'returns': [{'name': 'delegate_task', 'content': '{"status":"dispatched"}'}]},
            {'child': True, 'calls': [_call('read_file', 'k1')],
             'returns': [{'name': 'read_file', 'content': 'x'}]},
            {'child': True, 'calls': [_call('read_file', 'k2')],
             'returns': [{'name': 'read_file', 'content': 'y'}]},
            {'child': False, 'calls': [_call('delegate_task', 'c1'),
                                       _call('read_file', 'v1')],
             'returns': []},
            {'child': False, 'calls': [_call('delegate_task', 'c1'),
                                       _call('read_file', 'v1')],
             'returns': []},
        ]

    def test_old_rule_loses_the_middle_turns_verification(self):
        """RED: pinned to the defect the slice rule had.

        In this shape the last turn happens to contain the verification call too
        (the model repeated it), so the slice still sees it. The loss is proven
        by the case where the last turn made NO call at all — the parent
        verified in turn 1 and answered in turn 2.
        """
        old = acceptance_calls_old(self._records())
        self.assertEqual(['delegate_task', 'read_file'], [c['name'] for c in old])

    def test_old_rule_drops_a_verify_made_only_in_a_middle_turn(self):
        """The real blind spot: verification in a middle turn, silent last turn."""
        records = self._records()
        records[-1] = {'child': False, 'calls': records[-1]['calls'], 'returns': []}
        # Drop the verification from the LAST turn only.
        records[-1] = {'child': False,
                       'calls': [_call('delegate_task', 'c1')],
                       'returns': []}
        old = acceptance_calls_old(records)
        self.assertEqual(['delegate_task'], [c['name'] for c in old],
                         'the old rule kept only turn 0 and the last delta')
        new = acceptance_calls_new(records)
        self.assertEqual(['delegate_task', 'read_file'], [c['name'] for c in new],
                         'the new rule still sees the middle turn verification')

    def test_new_rule_keeps_it(self):
        new = acceptance_calls_new(self._records())
        self.assertEqual([c['name'] for c in new], ['delegate_task', 'read_file'])

    def test_no_call_is_counted_twice(self):
        """Each turn replays the previous turns' calls; the id filter is what
        keeps one real tool call from being counted as three."""
        new = acceptance_calls_new(self._records())
        ids = [c['call_id'] for c in new]
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_child_calls_are_never_included(self):
        new = acceptance_calls_new(self._records())
        self.assertNotIn('read_file_k_child', [c['call_id'] for c in new])
        self.assertEqual(['c1', 'v1'], [c['call_id'] for c in new])


class TwoTurnParentIsUnchanged(unittest.TestCase):
    """The rule must not change the verdict for the shapes that already pass."""

    def test_sol_r1_shape_still_sees_its_verify_reads(self):
        records = [
            {'child': False, 'calls': [_call('delegate_task', 'c1')],
             'returns': [{'name': 'delegate_task', 'content': '{"status":"dispatched"}'}]},
            {'child': True, 'calls': [_call('read_file', 'k1')],
             'returns': [{'name': 'read_file', 'content': 'x'}]},
            {'child': True, 'calls': [_call('read_file', 'k2')],
             'returns': [{'name': 'read_file', 'content': 'y'}]},
            {'child': True, 'calls': [_call('read_file', 'k3')],
             'returns': [{'name': 'read_file', 'content': 'z'}]},
            {'child': False, 'calls': [_call('delegate_task', 'c1'),
                                       _call('read_file', 'v1'),
                                       _call('read_file', 'v2'),
                                       _call('read_file', 'v3')],
             'returns': []},
        ]
        new = acceptance_calls_new(records)
        self.assertEqual(['delegate_task', 'read_file', 'read_file', 'read_file'],
                         [c['name'] for c in new])
        old = acceptance_calls_old(records)
        self.assertEqual([c['name'] for c in old], [c['name'] for c in new],
                         'the two-turn shape must not change verdict')

    def test_step5_shape_keeps_its_first_turn_reads(self):
        records = [
            {'child': False, 'calls': [_call('search_files', 'c1'),
                                       _call('read_file', 'c2'),
                                       _call('delegate_task', 'c3')],
             'returns': [{'name': 'delegate_task', 'content': '{"status":"dispatched"}'}]},
            {'child': False, 'calls': [_call('search_files', 'c1'),
                                       _call('read_file', 'c2'),
                                       _call('delegate_task', 'c3')],
             'returns': []},
        ]
        new = acceptance_calls_new(records)
        self.assertEqual(['search_files', 'read_file', 'delegate_task'],
                         [c['name'] for c in new])


if __name__ == '__main__':
    unittest.main(verbosity=2)
