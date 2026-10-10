import unittest
from delegation_evidence import evaluate

class EvidenceTests(unittest.TestCase):
    def test_self_report_is_not_parallel_evidence(self):
        self.assertFalse(evaluate('parallel', [], [], True))
    def test_failed_child_is_not_success(self):
        self.assertFalse(evaluate('parallel', [{'name':'delegate_task','arguments':{'tasks':[{},{}]}}], [{'success':False}], True))
    def test_spawn_action_is_a_real_delegation(self):
        self.assertTrue(evaluate('parallel', [{'name':'delegate_task','arguments':{'action':'spawn','tasks':[{},{}]}}], [{'success':True},{'success':True}], True))
    def test_simple_must_not_delegate(self):
        self.assertFalse(evaluate('simple', [{'name':'delegate_task','arguments':{}}], [], True))
    def test_files_must_remain_unchanged(self):
        self.assertFalse(evaluate('simple', [], [], False))

if __name__ == '__main__': unittest.main()
