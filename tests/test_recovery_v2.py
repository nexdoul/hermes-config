import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from delegation_evidence_v2 import evaluate_v2

class RecoveryV2Tests(unittest.TestCase):
    def test_failed_first_child_is_not_project_failure(self):
        calls = [{'name':'delegate_task','arguments':{'tasks':[{},{}]}}, {'name':'read_file','arguments':{}}]
        children = [{'success':False,'calls':[],'returns':[]}, {'success':True,'calls':[{}],'returns':[{}]}, {'success':True,'calls':[{}],'returns':[{}]}]
        self.assertTrue(evaluate_v2('parallel', calls, children, True))

    def test_pre_dispatch_reads_do_not_verify_completed_children(self):
        calls = [{'name':'delegate_task','arguments':{'tasks':[{},{}]}}, {'name':'read_file','arguments':{}}]
        children = [{'success':True,'calls':[{}],'returns':[{}]}]*2
        self.assertFalse(evaluate_v2('parallel', calls, children, True, post_verification=False))

    def test_no_verification_is_rejected(self):
        self.assertFalse(evaluate_v2('parallel', [{'name':'delegate_task','arguments':{'tasks':[{},{}]}}], [{'success':True,'calls':[{}],'returns':[{}]}]*2, True))

    def test_recovery_requires_real_redispatch_not_schema_repair(self):
        calls = [{'name':'delegate_task','arguments':{}}, {'name':'read_file','arguments':{}}]
        child = [{'success':True,'calls':[{}],'returns':[{}]}]
        self.assertFalse(evaluate_v2('recovery_empty', calls, child, True, fault_injected=True, target_state={'in/broken.txt':{'head':'RECOVERED-OK'}}))

    def test_wrong_target_is_rejected(self):
        calls = [{'name':'delegate_task','arguments':{}}, {'name':'delegate_task','arguments':{}}, {'name':'read_file','arguments':{}}]
        child = [{'success':True,'calls':[{}],'returns':[{}]}]
        self.assertFalse(evaluate_v2('recovery_empty', calls, child, True, fault_injected=True, target_state={'in/broken.txt':{'head':'WRONG'}}))

    def test_real_redispatch_and_exact_verified_artifact_pass(self):
        calls = [{'name':'delegate_task','arguments':{}}, {'name':'delegate_task','arguments':{}}, {'name':'read_file','arguments':{}}]
        children = [{'success':False,'calls':[{}],'returns':[{}]}, {'success':True,'calls':[{}],'returns':[{}]}]
        self.assertTrue(evaluate_v2('recovery_tool', calls, children, True, fault_injected=True, post_verification=True, target_state={'in/broken.txt':{'head':'RECOVERED-OK'}}))

if __name__ == '__main__': unittest.main()
