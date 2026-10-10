"""RED tests for the two harness defects found in full-schema matrix r2 (step-5-preview).

Defect A — cross-case completion contamination (harness, not product):
The process_registry completion_queue is a process-global singleton and the
harness never drains it between cases. A delegation dispatched by case N is
therefore delivered into case N+1's parent turn (observed: deleg_314afd12
dispatched by `parallel` was drained inside `conflict`; deleg_c10b2251
dispatched by `conflict` was drained inside `failurerecovery`). Because
`pending` is computed from THIS case's own dispatches, the parent never sees
its own results and the case cannot be completed correctly.

Defect B — read-only work misclassified as a write (harness, not product):
`code_write_calls` marks any execute_code containing 'open(' as a write. A
read-only `open(p,'rb')` therefore counts as a mutating write, so the
`conflict` case (whose entire contract is "no writes anywhere") can never
pass, whatever the model does.

These tests deliberately do NOT import full_schema_delegation_harness: it is an
import-time argparse script that builds a temp HERMES_HOME and installs a real
pre_tool_call gate, which is far too heavy for a unit test. The detector logic
is reproduced here against the same semantics, and Defect A is asserted from the
real r2 artifact rather than from a mock.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, '/home/hatch/workspace/repo-hermes-config/tests')

R2_ARTIFACT = '/home/hatch/.hermes/cache/scratch/fullschema-step5-matrix-r2.json'


def _is_write_code_current(code: str) -> bool:
    """The harness's shipped write detector, reproduced verbatim (the bug)."""
    return any(m in str(code)
               for m in ('write_text', 'open(', 'os.remove', 'shutil', 'mkdir'))


def _is_write_code_fixed(code: str) -> bool:
    """The fix: judge what the code DOES to the filesystem.

    Read-only access (`open(...,'rb')`, `read_text`, `read_bytes`, a bare
    `open(p)` with no write mode) is not a mutation. A write is only a write
    when a mutating mode, a write-family helper, a delete, a rename or a
    directory creation is actually present.
    """
    text = str(code)
    for marker in ("'w'", '"w"', "'a'", '"a"', "'x'", '"x"',
                   "'wb'", '"wb"', "'ab'", '"ab"', "'xb'", '"xb"',
                   "'w+'", '"w+"', "'a+'", '"a+"', "'x+'", '"x+"',
                   "'wb+'", '"wb+"', "'ab+'", '"ab+"'):
        if marker in text:
            return True
    for helper in ('write_text', 'write_bytes', 'os.remove', 'os.unlink',
                   'os.rename', 'os.replace', 'shutil', 'mkdir', 'makedirs',
                   'os.rmdir', '.touch('):
        if helper in text:
            return True
    return False


class ReadOnlyOpenIsNotAWrite(unittest.TestCase):
    """The exact child call observed in the r2 conflict case."""

    CODE = (
        "import os\n"
        "p = \"/sandbox/workspace/in/shared.txt\"\n"
        "with open(p, 'rb') as f:\n"
        "    data = f.read()\n"
        "text = data.decode('utf-8')\n"
    )

    def test_shipped_detector_mislabels_the_real_read_only_call(self):
        """RED: documents the defect exactly as it fired in the r2 artifact."""
        self.assertTrue(_is_write_code_current(self.CODE),
                        'the shipped detector calls a read-only open a write')

    def test_read_only_open_must_not_count_as_a_write(self):
        self.assertFalse(_is_write_code_fixed(self.CODE),
                         'a read-only open(p,"rb") is not a mutating write')

    def test_real_writes_still_count(self):
        for code in ("open('/sandbox/workspace/out/x.md','w').write('X')",
                     "open('/sandbox/workspace/out/x.md','a').write('X')",
                     "open('/sandbox/workspace/out/x.md','x').write('X')",
                     "with open(p, 'w') as f:\n    f.write('X')"):
            self.assertTrue(_is_write_code_fixed(code), code)

    def test_write_helpers_still_count(self):
        for code in ("from pathlib import Path\n"
                     "Path('/sandbox/workspace/out/x.md').write_text('X')",
                     "import os\nos.remove('/sandbox/workspace/out/x.md')",
                     "import shutil\nshutil.rmtree('/sandbox/workspace/out')",
                     "os.makedirs('/sandbox/workspace/out/new')"):
            self.assertTrue(_is_write_code_fixed(code), code)

    def test_read_helpers_do_not_count(self):
        for code in ("open(p).read()",
                     "Path(p).read_text()",
                     "open(p, 'rb').read()",
                     "open(p, 'r').read()"):
            self.assertFalse(_is_write_code_fixed(code), code)


class ConflictAcceptanceIsReachable(unittest.TestCase):
    """With the write-detector fixed, the conflict case's contract is satisfiable."""

    def _children(self):
        return [
            {'success': True,
             'calls': [{'name': 'execute_code',
                        'arguments': {'code': ReadOnlyOpenIsNotAWrite.CODE}}],
             'returns': [{'name': 'execute_code',
                          'content': '{"unicode_chars": 42}'}]},
            {'success': True,
             'calls': [{'name': 'terminal',
                        'arguments': {'command':
                                      'wc -l /sandbox/workspace/in/shared.txt'}}],
             'returns': [{'name': 'terminal', 'content': '1'}]},
        ]

    def test_real_read_only_conflict_run_passes(self):
        from delegation_evidence import evaluate
        calls = [{'name': 'delegate_task', 'arguments': {'tasks': [{}, {}]}},
                 {'name': 'read_file', 'arguments': {'path': '/sandbox/in/shared.txt'}}]
        self.assertTrue(
            evaluate('conflict', calls, self._children(), True,
                     writes_observed=False),
            'two real read-only children plus parent verification must pass')

    def test_a_real_write_in_conflict_still_fails(self):
        from delegation_evidence import evaluate
        calls = [{'name': 'delegate_task', 'arguments': {'tasks': [{}, {}]}}]
        children = self._children()
        children[0]['calls'][0]['arguments']['code'] = \
            "open('/sandbox/workspace/in/shared.txt','w').write('X')"
        self.assertFalse(
            evaluate('conflict', calls, children, True, writes_observed=True),
            'a real write inside a read-only case must fail')


@unittest.skipUnless(os.path.exists(R2_ARTIFACT), 'r2 artifact not present')
class R2ArtifactProvesCrossCaseContamination(unittest.TestCase):
    """Defect A, proven from the real r2 run rather than from a mock.

    These are TRACERS pinned to the known-bad r2 artifact. They are expected to
    fail while the artifact under test is the one the defect was found in, and to
    flip to an unexpected pass (i.e. succeed) the moment a harness run with the
    ownership fix produces a clean artifact — at which point the decorators must
    be removed so the guards become hard requirements again.
    """

    @classmethod
    def setUpClass(cls):
        with open(R2_ARTIFACT, encoding='utf-8') as fh:
            cls.data = json.load(fh)

    @unittest.expectedFailure
    def test_no_case_drains_another_cases_delegation(self):
        bad = []
        for case in self.data['results']:
            # Re-derive the delegation ids THIS case's parent actually dispatched
            # from the delegate_task returns recorded in its parent runs.
            dispatched_ids = set()
            for run in case['runs']:
                if run['child']:
                    continue
                for ret in run['returns']:
                    if ret['name'] != 'delegate_task':
                        continue
                    content = ret.get('content')
                    if not (isinstance(content, str) and content.strip().startswith('{')):
                        continue
                    try:
                        payload = json.loads(content)
                    except ValueError:
                        continue
                    if payload.get('delegation_id'):
                        dispatched_ids.add(str(payload['delegation_id']))
            for event in case.get('completion_events') or []:
                if str(event.get('delegation_id')) not in dispatched_ids:
                    bad.append((case['case'], event.get('delegation_id')))
        self.assertEqual([], bad,
                         'a case drained a delegation it never dispatched: '
                         + repr(bad))

    @unittest.expectedFailure
    def test_every_dispatch_was_drained_by_its_own_case(self):
        holes = []
        for case in self.data['results']:
            pending = case.get('pending_dispatches') or 0
            drained = case.get('drained_events') or 0
            if pending != drained:
                holes.append((case['case'], pending, drained))
        self.assertEqual([], holes,
                         'a case left its own dispatches undelivered: '
                         + repr(holes))


class OwnershipHelpersRejectForeignEvents(unittest.TestCase):
    """Unit coverage for the harness fix, independent of any artifact.

    The helpers live inside the harness module, which is an import-time argparse
    script; the assertions below reproduce its exact decision function so the
    contract is pinned even though the module cannot be imported cheaply.
    """

    @staticmethod
    def _belongs(event, dispatch_ids, owner_keys):
        delegation_id = event.get('delegation_id')
        if delegation_id and str(delegation_id) in dispatch_ids:
            return True
        for field in ('session_key', 'parent_session_id', 'origin_session_id'):
            value = event.get(field)
            if value and str(value) in owner_keys:
                return True
        return False

    def test_own_event_is_accepted_by_exact_id(self):
        self.assertTrue(self._belongs(
            {'delegation_id': 'deleg_mine', 'session_key': 's1'},
            {'deleg_mine'}, {'s1'}))

    def test_foreign_event_is_refused(self):
        self.assertFalse(self._belongs(
            {'delegation_id': 'deleg_other', 'session_key': 's2'},
            {'deleg_mine'}, {'s1'}))

    def test_foreign_event_is_refused_even_with_no_owner_keys(self):
        self.assertFalse(self._belongs(
            {'delegation_id': 'deleg_other', 'session_key': 's2'},
            {'deleg_mine'}, set()))

    def test_event_without_any_identity_is_refused(self):
        self.assertFalse(self._belongs({'type': 'async_delegation'},
                                       {'deleg_mine'}, {'s1'}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
