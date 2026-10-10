"""Summarise the full-schema matrix artifacts into one compact evidence record.

The raw artifacts are large (200-400 KB each) and contain sandbox paths; this keeps
only the verdict, the ownership integrity check and the real observed side effects,
which is what a reviewer needs. No secrets, no production paths beyond the sandbox
root that the harness itself records.
"""
import json
import pathlib
import sys

SCRATCH = pathlib.Path('/home/hatch/.hermes/cache/scratch')
ARTIFACTS = [
    ('fullschema-step5-matrix-r5.json', 'step-5-preview', 'round 1 after policy fix'),
    ('fullschema-step5-matrix-r5b.json', 'step-5-preview', 'round 2 repeat'),
    ('fullschema-sol-matrix-r1.json', 'gpt-6.1-sol', 'round 1 after policy fix'),
    ('fullschema-sol-matrix-r2.json', 'gpt-6.1-sol', 'round 2 repeat'),
]

out = {
    'scope': ('Full production-equivalent tool schemas (no schema filtering), real side '
              'effects confined to an isolated workspace by a real pre_tool_call dispatch '
              'gate, async completion queue drained turn-by-turn with exact ownership '
              'matching. Production policy not installed.'),
    'runs': [],
}

for filename, model, label in ARTIFACTS:
    path = SCRATCH / filename
    if not path.exists():
        print(f'MISSING: {filename}', file=sys.stderr)
        continue
    d = json.loads(path.read_text(encoding='utf-8'))
    violations = []
    for case in d['results']:
        own = set()
        for run in case['runs']:
            if run['child']:
                continue
            for ret in run['returns']:
                if ret['name'] != 'delegate_task':
                    continue
                content = ret.get('content')
                if isinstance(content, str) and content.strip().startswith('{'):
                    try:
                        payload = json.loads(content)
                    except ValueError:
                        continue
                    if payload.get('delegation_id'):
                        own.add(str(payload['delegation_id']))
        for ev in case.get('completion_events') or []:
            if str(ev.get('delegation_id')) not in own:
                violations.append({'case': case['case'], 'kind': 'foreign_event',
                                   'delegation_id': ev.get('delegation_id')})
        if (case.get('pending_dispatches') or 0) != (case.get('drained_events') or 0):
            violations.append({'case': case['case'], 'kind': 'undelivered',
                               'pending': case.get('pending_dispatches'),
                               'drained': case.get('drained_events')})
    out['runs'].append({
        'artifact': filename,
        'model': d.get('model'),
        'requested_model': d.get('requested_model'),
        'provider': d.get('provider'),
        'label': label,
        'all_passed': d.get('all_passed'),
        'policy_sha256': d.get('policy_sha256'),
        'production_toolsets': d.get('production_toolsets'),
        'ownership_violations': violations,
        'cases': [{
            'case': c['case'],
            'passed': c['passed'],
            'pending_dispatches': c.get('pending_dispatches'),
            'drained_events': c.get('drained_events'),
            'child_runs': c.get('child_runs'),
            'writes_observed': c.get('writes_observed'),
            'gate_denied': [{'tool': e.get('tool'), 'reason': e.get('reason')}
                            for e in (c.get('gate_denied') or [])],
            'workspace_changes': sorted((c.get('workspace_changes') or {}).keys()),
            'unexpected_workspace_changes': sorted(
                (c.get('unexpected_workspace_changes') or {}).keys()),
            'target_state': {k: {'changed_from_before': v.get('changed_from_before'),
                                 'head': v.get('head')}
                             for k, v in (c.get('target_state') or {}).items()},
        } for c in d['results']],
    })

dest = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'tests/results/full-schema-matrix.json')
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'wrote {dest}')
for run in out['runs']:
    n_pass = sum(1 for c in run['cases'] if c['passed'])
    print(f"  {run['model']:16s} {run['label']:26s} "
          f"{n_pass}/{len(run['cases'])} all_passed={run['all_passed']} "
          f"violations={len(run['ownership_violations'])}")
