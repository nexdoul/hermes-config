"""Pin the policy-source rule: production config wins over --policy.

The harness used to always overwrite agent.system_prompt with the --policy
file's text, which meant a run could never prove that a PRODUCTION-installed
key is what the model actually sees. The isolated config now keeps the
production value when one exists.
"""
import sys
import unittest

sys.path.insert(0, '/home/hatch/workspace/repo-hermes-config/tests')


def resolve(cfg, policy_text):
    """The harness's rule, reproduced."""
    if not (cfg.get('agent') or {}).get('system_prompt'):
        cfg.setdefault('agent', {})['system_prompt'] = policy_text
    return (cfg.get('agent') or {}).get('system_prompt') or policy_text


class PolicySource(unittest.TestCase):
    def test_candidate_text_is_used_when_production_has_none(self):
        cfg = {'agent': {'reasoning_effort': 'xhigh'}}
        self.assertEqual('CANDIDATE', resolve(cfg, 'CANDIDATE'))
        self.assertEqual('CANDIDATE', cfg['agent']['system_prompt'])

    def test_production_value_is_used_when_present(self):
        """The whole point: an installed key must be what the model sees."""
        cfg = {'agent': {'system_prompt': 'INSTALLED', 'reasoning_effort': 'xhigh'}}
        self.assertEqual('INSTALLED', resolve(cfg, 'CANDIDATE'))
        self.assertEqual('INSTALLED', cfg['agent']['system_prompt'],
                         'the candidate text must not overwrite the installed key')

    def test_other_agent_keys_survive(self):
        cfg = {'agent': {'reasoning_effort': 'xhigh', 'reasoning_overrides': {}}}
        resolve(cfg, 'CANDIDATE')
        self.assertEqual('xhigh', cfg['agent']['reasoning_effort'])
        self.assertEqual({}, cfg['agent']['reasoning_overrides'])

    def test_empty_production_value_falls_back_to_candidate(self):
        cfg = {'agent': {'system_prompt': ''}}
        self.assertEqual('CANDIDATE', resolve(cfg, 'CANDIDATE'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
