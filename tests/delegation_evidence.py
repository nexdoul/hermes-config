"""Conservative live-test acceptance; prose never substitutes for tool evidence."""
def evaluate(case, calls, children, unchanged):
    if not unchanged:
        return False
    delegates = [c for c in calls if c['name'] == 'delegate_task' and c['arguments'].get('action', 'spawn') == 'spawn']
    if case == 'parallel':
        return any(len(c['arguments'].get('tasks', [])) >= 2 for c in delegates) and len(children) >= 2 and all(c.get('success') for c in children)
    return not delegates
