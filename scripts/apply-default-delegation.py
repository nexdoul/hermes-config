#!/usr/bin/env python3
"""Install only the verified policy key through supported Hermes CLI; private backup."""
import argparse, copy, json, os, pathlib, subprocess, time, yaml
p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--policy',required=True);a=p.parse_args()
home=pathlib.Path(a.home);target=home/'config.yaml'
before=yaml.safe_load(target.read_text())
assert not before.get('display',{}).get('personality'), 'personality would hide overlay'
assert not os.getenv('HERMES_EPHEMERAL_SYSTEM_PROMPT'), 'environment would hide overlay'
assert not before.get('agent',{}).get('system_prompt'), 'existing overlay: merge explicitly, never overwrite'
for proc in pathlib.Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        cmd=(proc/'cmdline').read_bytes()
        if b'hermes' in cmd and b'gateway' in cmd:
            assert b'HERMES_EPHEMERAL_SYSTEM_PROMPT=' not in (proc/'environ').read_bytes(), 'gateway overlay present'
    except (FileNotFoundError,PermissionError):pass
policy=pathlib.Path(a.policy).read_text().strip()
assert policy.count('[DEFAULT_PARALLEL_DELEGATION_V1]')==1
print('RED: policy marker absent; precheck OK',flush=True)
backup=home/('config.yaml.before-default-parallel-delegation-'+str(time.time_ns()))
with backup.open('xb') as f:f.write(target.read_bytes())
os.chmod(backup,0o600)
env=dict(os.environ,HERMES_HOME=str(home))
subprocess.run(['hermes','config','set','agent.system_prompt',policy],env=env,check=True,stdout=subprocess.DEVNULL)
after=yaml.safe_load(target.read_text());check=copy.deepcopy(after)
check['agent'].pop('system_prompt')
assert check==before,'unexpected unrelated changes'
assert after['agent']['system_prompt']==policy
from hermes_cli.config import load_config, resolve_ephemeral_system_prompt_from_config
assert resolve_ephemeral_system_prompt_from_config(load_config())==policy
print('GREEN: POLICY_OK; ONLY_AGENT_SYSTEM_PROMPT_CHANGED; resolver exact match')
print('private_backup='+str(backup))
