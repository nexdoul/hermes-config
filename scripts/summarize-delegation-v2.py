#!/usr/bin/env python3
"""Summarize recorded V2 evidence without publishing credentials/raw session data."""
import argparse, hashlib, json, pathlib
p=argparse.ArgumentParser(); p.add_argument('inputs',nargs='+'); p.add_argument('--output',required=True); a=p.parse_args()
summary={'scope':'Real AIAgent loops with original tool schemas, isolated write fixtures, pre-dispatch side-effect confinement. Not full Feishu transport acceptance.','reports':[]}
for raw in a.inputs:
    path=pathlib.Path(raw); data=json.loads(path.read_text())
    results=[]
    for r in data['results']:
        parent=r.get('parent_calls') or []
        spawns=[c for c in parent if c.get('name')=='delegate_task' and (c.get('arguments') or {}).get('action','spawn')=='spawn']
        results.append({'round':r['round'],'case':r['case'],'passed':r.get('passed'), 'first_attempt_success':r.get('first_attempt_success'),'fault_injected':r.get('fault_injected'), 'spawn_count':len(spawns),'batch_sizes':[len((c.get('arguments') or {}).get('tasks') or []) for c in spawns], 'child_tool_calls':r.get('child_call_names'), 'schema_repair_runs':r.get('schema_repair_runs'), 'post_completion_verification_count':len(r.get('post_completion_verification') or []), 'target_content':(r.get('target_state') or {}).get('in/broken.txt',{}).get('head'), 'unauthorized_workspace_changes':list((r.get('unexpected_workspace_changes') or {}).keys()), 'gate_denials':len(r.get('gate_denied') or []),'undrained_dispatches':r.get('undrained_dispatches')})
    summary['reports'].append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'model':data['model'],'provider':data.get('provider'),'policy_sha256':data['policy_sha256'],'all_passed':data.get('all_passed'),'results':results})
pathlib.Path(a.output).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'reports':len(summary['reports']),'cases':sum(len(x['results']) for x in summary['reports']),'output':a.output}))
