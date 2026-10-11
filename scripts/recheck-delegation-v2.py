#!/usr/bin/env python3
"""Offline stricter re-evaluation of stored real traces; no fabricated model output."""
import argparse, ast, json, pathlib, sys, re
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tests'))
from delegation_evidence_v2 import evaluate_v2
p=argparse.ArgumentParser();p.add_argument('report');p.add_argument('--output',required=True);a=p.parse_args()
data=json.loads(pathlib.Path(a.report).read_text())
source=ast.parse((pathlib.Path(__file__).resolve().parents[1]/'tests/recovery_v2_harness.py').read_text())
names={'_helper_before','_iter_literals','_strip_string_literals','_terminal_mutates_fs','_code_mutates_fs','_invocation_tokens'}
ns={'re':re,'_QUOTES': ('"', "'"),'_SHELL_HELPERS':set(),'_PATH_HELPERS':set(),'_NET_HELPERS':set(),'_KNOWN_MODULES':set()}
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'<detectors>','exec'),ns)
for r in data['results']:
    r['historical_writes_observed']=r.get('writes_observed')
    tc=[c for run in r.get('runs',[]) for c in run['calls'] if c['name']=='terminal' and ns['_terminal_mutates_fs'](str(c.get('arguments',{}).get('command','')))]
    cc=[c for run in r.get('runs',[]) for c in run['calls'] if c['name']=='execute_code' and ns['_code_mutates_fs'](str(c.get('arguments',{}).get('code','')))]
    r['writes_observed']=bool(r.get('write_calls') or tc or cc)
    r['terminal_write_calls']=tc
    r['code_write_calls']=cc
    parents=[x for x in r.get('runs',[]) if not x['child']]
    children=[x for x in r.get('runs',[]) if x['child'] and not x.get('schema_repair')]
    prior={c.get('call_id') for run in parents[:-1] for c in run['calls']}
    final=parents[-1] if parents else {'calls':[],'returns':[]}
    returns={t.get('tool_call_id'):t for t in final['returns']}
    evidence=[]
    for call in final['calls']:
        if call.get('call_id') in prior or call.get('name') not in {'read_file','terminal','execute_code','search_files'}:continue
        ret=returns.get(call.get('call_id'),{})
        try: payload=json.loads(ret.get('content') or '{}')
        except (ValueError,TypeError):continue
        if not payload.get('error') and payload.get('exit_code',0)==0:evidence.append({'call':call,'return':ret})
    case=r['case']
    r['historical_passed']=r.get('passed')
    r['post_completion_verification']=evidence
    needs=case in ('parallel','conflict','serial') or case.startswith('recovery_')
    r['passed']=bool(evaluate_v2(case,r.get('parent_calls',[]),children,r.get('unchanged',False),unexpected_changes=r.get('unexpected_workspace_changes'),post_verification=bool(evidence) if needs else True,target_state=r.get('target_state'),fault_injected=r.get('fault_injected'),writes_observed=r.get('writes_observed')) and r.get('parent_success') and not r.get('undrained_dispatches'))
data['all_passed']=all(r['passed'] for r in data['results'])
data['re_evaluation']='Stricter final evaluator applied to original recorded calls/returns. Historical judgment preserved; no model rerun.'
pathlib.Path(a.output).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print([(r['round'],r['case'],r['passed']) for r in data['results']])
