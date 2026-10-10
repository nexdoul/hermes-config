"""Regression tracer: successful child prose alone must not satisfy real work."""
import unittest
from delegation_evidence import evaluate

class EvidenceStrengthTests(unittest.TestCase):
    def test_parallel_requires_observed_child_actions_and_parent_verification(self):
        calls = [{'name': 'delegate_task', 'arguments': {'tasks': [{}, {}]}}]
        children = [{'success': True, 'calls': [], 'returns': []},
                    {'success': True, 'calls': [], 'returns': []}]
        self.assertFalse(evaluate('parallel', calls, children, True),
                         'Dispatch and child final prose are not real-action evidence')

if __name__ == '__main__':
    unittest.main()
