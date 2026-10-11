#!/usr/bin/env python3
"""Print sanitized production policy/readback and runtime resolution; no credentials."""
import argparse, hashlib, json, pathlib, os, yaml
p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--policy',required=True);a=p.parse_args()
os.environ['HERMES_HOME']=a.home
cfg=yaml.safe_load((pathlib.Path(a.home)/'config.yaml').read_text())
key=(cfg.get('agent') or {}).get('system_prompt') or ''
expected=pathlib.Path(a.policy).read_text().strip()
from hermes_cli.config import load_config, resolve_ephemeral_system_prompt_from_config
print(json.dumps({'key_present':bool(key),'length':len(key),'sha256':hashlib.sha256(key.encode()).hexdigest(),'file_exact':key==expected,'resolver_exact':resolve_ephemeral_system_prompt_from_config(load_config())==key,'marker_count':key.count('[DEFAULT_PARALLEL_DELEGATION_V2]'),'model':(cfg.get('model') or {}).get('default'),'provider':(cfg.get('model') or {}).get('provider'),'approvals_mode':(cfg.get('approvals') or {}).get('mode')}))
assert key==expected and key.count('[DEFAULT_PARALLEL_DELEGATION_V2]')==1
