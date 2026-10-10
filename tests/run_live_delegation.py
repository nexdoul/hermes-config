#!/usr/bin/env python3
"""Run with Hermes runtime's Python and PYTHONPATH. Never copies secrets into artifacts.
Real AIAgent + real delegate_task; tool exposure restricted to read_file/delegate_task.
No terminal/write/cron/message tools in either parent or children.
"""
import argparse, hashlib, json, os, pathlib, tempfile, threading, time

parser = argparse.ArgumentParser()
parser.add_argument('--production-home', required=True)
parser.add_argument('--policy', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--provider', default='dsh-mysub-oai')
parser.add_argument('--model', default='gpt-6.1-sol')
parser.add_argument('--rounds', type=int, default=3)
parser.add_argument('--cases', default='parallel,simple,forbid,dependency,supervision')
a = parser.parse_args()
root = pathlib.Path(a.production_home)
from dotenv import load_dotenv
load_dotenv(root / '.env', override=False)
import yaml
cfg = yaml.safe_load((root / 'config.yaml').read_text())
policy = pathlib.Path(a.policy).read_text()
scratch = pathlib.Path(os.environ.get('TMPDIR', root / 'cache/scratch'))
home = pathlib.Path(tempfile.mkdtemp(prefix='delegation-live-', dir=scratch))
os.environ['HERMES_HOME'] = str(home)
os.environ.pop('HERMES_EPHEMERAL_SYSTEM_PROMPT', None)
fixture = home / 'fixture'
fixture.mkdir()
for name in ('timer','cron','daemon'):
    (fixture / (name + '.txt')).write_text(name + ': analyze failure recovery, stop semantics, idempotency and resource cost. No deployment authorized.\n')
cfg.setdefault('agent', {})['system_prompt'] = policy
cfg.setdefault('terminal', {})['cwd'] = str(fixture)
(home / 'config.yaml').write_text(yaml.safe_dump(cfg, allow_unicode=True))
os.chmod(home / 'config.yaml', 0o600)
os.chdir(fixture)
from hermes_cli.config import load_config, resolve_ephemeral_system_prompt_from_config
from hermes_cli.runtime_provider import resolve_runtime_provider
from run_agent import AIAgent
import model_tools
original_defs = model_tools.get_tool_definitions
allowed = {'read_file','delegate_task'}
def restricted_defs(*args, **kwargs):
    return [t for t in original_defs(*args, **kwargs) if t['function']['name'] in allowed]
model_tools.get_tool_definitions = restricted_defs
rt = resolve_runtime_provider(requested=a.provider, target_model=a.model)
# Observe actual completed child loops, not model self-reports.
original_run = AIAgent.run_conversation
lock = threading.Lock()
records = []
def observed_run(self, *args, **kwargs):
    start = time.time()
    result = original_run(self, *args, **kwargs)
    calls = []
    returns = []
    for m in result.get('messages', []):
        for t in m.get('tool_calls') or []:
            f = t['function']
            ar = f.get('arguments', {})
            if isinstance(ar, str):
                try: ar = json.loads(ar)
                except ValueError: ar = {'raw':ar}
            calls.append({'name':f['name'], 'arguments':ar})
        if m.get('role') == 'tool': returns.append({'name':m.get('name'), 'content':m.get('content')})
    rec = {'start':start,'end':time.time(),'child':bool(getattr(self,'_parent_session_id',None)),
           'tools':sorted(self.valid_tool_names),'calls':calls,'returns':returns,
           'success':bool(result.get('final_response')) and not result.get('error'),
           'final_response':result.get('final_response'), 'error':result.get('error')}
    with lock: records.append(rec)
    return result
AIAgent.run_conversation = observed_run
from delegation_evidence import evaluate
prompts = {
 'parallel': f'比较三种互相独立的方案：systemd timer、cron、独立常驻脚本。分别深入分析恢复语义、停止语义、幂等边界和资源成本，每种结合对应资料 {fixture}/timer.txt、cron.txt、daemon.txt，最后统一比较。不改文件、不部署，简洁交付。',
 'simple':'只回答：你好',
 'forbid': '比较systemd timer、cron、独立常驻脚本的恢复与停止语义。本次禁止子Agent，串行完成；不修改文件、不部署。',
 'dependency': f'本次只有一条有先后依赖的路径：读取 {fixture}/timer.txt，然后根据读取结果判断停止语义，最后依据判断提出一个风险。严格顺序执行，不做独立扩展，不修改。',
 'supervision':'解释为什么一次内置子Agent任务不能当作永久监督，并给出一次性任务完成判据。仅解释，不创建cron/watchdog，不重启任何东西。',
}
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
protected = [root / 'config.yaml',root / 'SOUL.md',root / 'cron/jobs.json',pathlib.Path('/home/hatch/AGENTS.md')]
before = {str(p):digest(p) for p in protected if p.exists()}
fixture_before = {p.name:digest(p) for p in fixture.iterdir()}
report = {'model':a.model,'provider':a.provider,'rounds':a.rounds,'restricted_tools':sorted(allowed),'results':[]}
for round_no in range(a.rounds):
    for case in a.cases.split(','):
        records.clear()
        agent = AIAgent(model=a.model, provider=rt['provider'],api_key=rt.get('api_key'),base_url=rt.get('base_url'),api_mode=rt.get('api_mode'),
                        enabled_toolsets=['delegation','file'],ephemeral_system_prompt=resolve_ephemeral_system_prompt_from_config(load_config()),
                        max_iterations=16,quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,cwd=str(fixture))
        case_before = {str(p):digest(p) for p in protected if p.exists()}
        try:
            result = agent.run_conversation(prompts[case])
            # Top-level delegate_task always dispatches asynchronously in this runtime.
            # Consume its real completion queue exactly as a UI would, not transcript polling.
            from tools.process_registry import process_registry
            from tools.process_registry_notifications import format_process_notification
            completion_events = []
            first_parent = records[-1]
            dispatches = [json.loads(t['content']) for t in first_parent['returns'] if t['name']=='delegate_task' and isinstance(t['content'], str)]
            pending = sum(1 for d in dispatches if d.get('status')=='dispatched')
            for _ in range(pending):
                event = process_registry.completion_queue.get(timeout=240)
                assert event.get('type') == 'async_delegation', event.get('type')
                completion_events.append(event)
                result = agent.run_conversation(format_process_notification(event), conversation_history=result['messages'])
            # run_conversation(history=...) returns complete history; keep only this turn's calls.
            child = [r for r in records if r['child']]
            parent = records[-1]
            if pending:
                parent['calls'] = parent['calls'][len(first_parent['calls']):]
            acceptance_calls = first_parent['calls'] + (parent['calls'] if pending else [])
            changed_targets = [str(p) for p in protected if str(p) in case_before and (not p.exists() or digest(p)!=case_before[str(p)])]
            # Production cron can legitimately change due to its live scheduler. Read-only
            # tool allowlist proves tests cannot write it; record concurrent changes explicitly.
            unchanged = not [p for p in changed_targets if not p.endswith('/cron/jobs.json')] and fixture_before=={p.name:digest(p) for p in fixture.iterdir()}
            all_calls = [c for r in records for c in r['calls']]
            invalid_calls = [c for c in all_calls if c['name'] not in allowed]
            invalid_tools = [r['tools'] for r in records if not set(r['tools']) <= allowed]
            passed = evaluate(case,acceptance_calls,child,unchanged) and parent['success'] and not invalid_calls and not invalid_tools
            entry = {'round':round_no+1,'case':case,'passed':passed,'unchanged':unchanged,'concurrent_production_changes':changed_targets,'completion_events':completion_events,'runs':list(records)}
            report['results'].append(entry)
            pathlib.Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps({'round':round_no+1,'case':case,'passed':passed,'children':len(child),'calls':[c['name'] for c in parent['calls']]},ensure_ascii=False),flush=True)
        finally: agent.close()
report['all_passed'] = all(r['passed'] for r in report['results'])
pathlib.Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if report['all_passed'] else 1)
