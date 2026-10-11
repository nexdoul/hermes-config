#!/usr/bin/env python3
"""Install V2 through CLI, replace only exact V1/V2 overlay, preserve all other config."""
import argparse, copy, hashlib, json, os, pathlib, subprocess, time, yaml
p=argparse.ArgumentParser()
p.add_argument('--home', required=True)
p.add_argument('--policy', required=True)
p.add_argument('--previous-policy', required=True)
p.add_argument('--hermes', required=True)
a=p.parse_args()
home=pathlib.Path(a.home).resolve()
target=home/'config.yaml'
before=yaml.safe_load(target.read_text())
policy=pathlib.Path(a.policy).read_text().strip()
old=pathlib.Path(a.previous_policy).read_text().strip()
assert policy.count('[DEFAULT_PARALLEL_DELEGATION_V2]') == 1
assert not before.get('display', {}).get('personality'), 'personality hides overlay'
assert not os.getenv('HERMES_EPHEMERAL_SYSTEM_PROMPT'), 'environment hides overlay'
current=before.get('agent', {}).get('system_prompt')
assert not current or current in (old,policy), 'unrelated overlay: merge required'
for proc in pathlib.Path('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try:
        cmd=(proc/'cmdline').read_bytes()
        if b'hermes' in cmd and b'gateway' in cmd:
            assert b'HERMES_EPHEMERAL_SYSTEM_PROMPT=' not in (proc/'environ').read_bytes(), 'gateway overlay hides policy'
    except (FileNotFoundError, PermissionError): pass
backup=home/('config.yaml.before-default-delegation-v2-'+str(time.time_ns()))
with backup.open('xb') as f: f.write(target.read_bytes())
os.chmod(backup,0o600)
env=dict(os.environ,HERMES_HOME=str(home))
subprocess.run([a.hermes,'config','set','agent.system_prompt',policy],env=env,check=True,stdout=subprocess.DEVNULL)
after=yaml.safe_load(target.read_text())
expected=copy.deepcopy(before)
expected.setdefault('agent', {})['system_prompt']=policy
assert after == expected, 'unrelated changes detected'
os.environ['HERMES_HOME']=str(home)
from hermes_cli.config import load_config, resolve_ephemeral_system_prompt_from_config
assert resolve_ephemeral_system_prompt_from_config(load_config()) == policy
print(json.dumps({'installed':True,'only_agent_system_prompt_changed':True,'resolver_exact':True,'length':len(policy),'sha256':hashlib.sha256(policy.encode()).hexdigest(),'backup':str(backup)}))
