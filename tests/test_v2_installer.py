import os
import pathlib
import subprocess
import tempfile
import unittest
import yaml

class V2InstallerTests(unittest.TestCase):
    def test_replaces_v1_without_other_config_changes(self):
        runtime=pathlib.Path('/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent')
        if not runtime.exists(): self.skipTest('local runtime path not applicable')
        repo=pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir='/home/hatch/.hermes/cache/scratch') as d:
            home=pathlib.Path(d)
            old=(repo/'policies/default-parallel-delegation.txt').read_text().strip()
            before={'agent':{'system_prompt':old},'model':{'default':'fixture'},'unrelated':{'keep':True}}
            (home/'config.yaml').write_text(yaml.safe_dump(before))
            env=dict(os.environ,HERMES_HOME=str(home),PYTHONPATH=str(runtime))
            env.pop('HERMES_EPHEMERAL_SYSTEM_PROMPT',None)
            proc=subprocess.run([str(runtime/'venv/bin/python3'),str(repo/'scripts/apply-default-delegation-v2.py'),'--home',str(home),'--policy',str(repo/'policies/default-parallel-delegation-v2.txt'),'--previous-policy',str(repo/'policies/default-parallel-delegation.txt'),'--hermes',str(runtime/'venv/bin/hermes')],env=env,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            after=yaml.safe_load((home/'config.yaml').read_text())
            self.assertEqual(after['unrelated'],before['unrelated'])
            self.assertEqual(after['model'],before['model'])
            self.assertEqual(after['agent']['system_prompt'],(repo/'policies/default-parallel-delegation-v2.txt').read_text().strip())

if __name__=='__main__': unittest.main()
