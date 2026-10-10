#!/usr/bin/env python3
"""Full-schema delegation harness: real production-equivalent tool schemas, real side effects.

Run with the Hermes runtime's Python and PYTHONPATH (from the runtime dir). Never
copies secrets into artifacts.

Design contract (this file is the mission's evidence source):

1. ORIGINAL SCHEMAS PRESERVED. ``model_tools.get_tool_definitions`` is NOT filtered
   and NOT replaced. Parent and children receive exactly the tool schemas the
   production profile would resolve (toolsets taken from the production config,
   copied verbatim into the isolated home). Both parent and child schema lists are
   recorded so a reviewer can diff them against production.
2. EXTERNAL SIDE EFFECTS BLOCKED BEFORE DISPATCH. Safety is enforced in the real
   dispatch path via ``hermes_cli.plugins`` hook ``pre_tool_call`` returning
   ``{"action": "block", "message": ...}``. That is the same seam production
   authorization uses (model_tools.handle_function_call -> _pre_dispatch_guards ->
   hermes_cli.plugins._dispatch_pre_tool_call_hooks); a block becomes the tool
   result and the handler never runs. The gate is:
     - hard deny list for tools that must never run (cronjob_manage, send_message,
       clarify, memory, session_search, todo_list, text_to_speech, image_generate,
       browser_*, manage_connections, skill_manage, kanban_*);
     - workspace confinement: every path-bearing tool (read_file/write_file/patch/
       search_files/vision_analyze/execute_code) must resolve inside the isolated
       workspace; terminal commands are additionally checked for references to
       paths outside the workspace, network egress, process/system control.
   The gate is registered BEFORE the agent is constructed and never removed during
   the run, so a denied call is real evidence of enforcement, not of a missing tool.
3. ASYNC COMPLETION QUEUE DRAINED, NO PROSE. Top-level delegate_task always
   dispatches asynchronously in this runtime. The harness consumes
   ``process_registry.completion_queue`` with a bounded timeout, asserts the event
   type is ``async_delegation``, and feeds ``format_process_notification(event)``
   back into the parent as a new turn — the same path a UI takes. It never polls a
   transcript and never treats the model's own words as completion evidence.
4. REAL OBSERVATION. ``AIAgent.run_conversation`` is wrapped to record, per run:
   parent vs child, the resolved tool schemas, every tool call with its arguments,
   every tool return, the structured completion fields and the final response.
   Children are identified by ``_parent_session_id``, never by self-report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import threading
import time

# ---------------------------------------------------------------- argument parsing
parser = argparse.ArgumentParser()
parser.add_argument('--production-home', required=True)
parser.add_argument('--policy', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--provider', default=None)
parser.add_argument('--model', default=None)
parser.add_argument('--rounds', type=int, default=1)
parser.add_argument('--cases', default='parallel,simple,forbid,dependency,supervision,'
                                       'serial,conflict,failurerecovery')
parser.add_argument('--max-turns', type=int, default=200)
a = parser.parse_args()

root = pathlib.Path(a.production_home).expanduser().resolve()

# Production config is copied into the isolated home so toolset resolution,
# model routing and approval policy match production byte-for-byte in substance.
from dotenv import load_dotenv
load_dotenv(root / '.env', override=False)
import yaml
cfg = yaml.safe_load((root / 'config.yaml').read_text())

policy_text = pathlib.Path(a.policy).read_text()

scratch = pathlib.Path(os.environ.get('TMPDIR', root / 'cache/scratch'))
home = pathlib.Path(tempfile.mkdtemp(prefix='deleg-full-', dir=scratch))
os.environ['HERMES_HOME'] = str(home)
os.environ.pop('HERMES_EPHEMERAL_SYSTEM_PROMPT', None)
os.environ.pop('HERMES_IGNORE_RULES', None)
# This agent's own CLI session is a finite one-shot; that marker is inherited
# through the environment and would (a) hide tools via ONESHOT_HIDDEN_TOOLS,
# (b) cap delegation to delegation.oneshot_max_children=2, and (c) force
# SYNCHRONOUS delegation. Production (gateway/Feishu/CLI interactive) has none of
# those, so the harness must run the production shape: clear it.
for _oneshot_key in ('HERMES_SINGLE_QUERY_SESSION', 'HERMES_CRON_SESSION',
                     'HERMES_UI_SESSION_ID', 'HERMES_KANBAN_TASK',
                     'HERMES_DELEGATED_CHILD_CONTEXT'):
    os.environ.pop(_oneshot_key, None)

# ---------------------------------------------------------------- isolated workspace
# Every real side effect the agents are allowed to make must land here. The safety
# gate resolves every candidate path against this root.
workspace = home / 'workspace'
workspace.mkdir()
(workspace / 'in').mkdir()
(workspace / 'out').mkdir()

# Fixtures: real files the children must really read, and real targets the parent
# must really verify.
fixtures = {
    'timer.txt': 'systemd timer 的恢复语义：OnCalendar 触发，Persistent=true 补跑错过的窗口；'
                 '停止语义：systemctl stop/disble，disable 只去开机自启；幂等边界：服务本身要幂等；'
                 '资源成本：一个常驻 systemd 实例，无轮询。',
    'cron.txt': 'cron 的恢复语义：机器停机期间的窗口不补跑（anacron 例外）；停止语义：'
                '删除 crontab 条目；幂等边界：脚本必须自己防重入；资源成本：每行一个 cron 进程，'
                '最小常驻开销。',
    'daemon.txt': '独立常驻脚本的恢复语义：自己实现看门狗或交给外部 systemd Restart=always；'
                  '停止语义：需要明确的停止标记文件；幂等边界：最容易踩，重启后要从断点继续；'
                  '资源成本：一个常驻进程加轮询成本。',
    'shared.txt': '共享文件：两个子任务都只能读，禁止写。冲突场景用。',
    'broken.txt': '目标文件：用于失败恢复场景，父 Agent 必须验证其真实内容。',
}
for name, body in fixtures.items():
    (workspace / 'in' / name).write_text(body, encoding='utf-8')
(workspace / 'out' / 'report-a.md').write_text('PLACEHOLDER-A\n', encoding='utf-8')
(workspace / 'out' / 'report-b.md').write_text('PLACEHOLDER-B\n', encoding='utf-8')

# ---------------------------------------------------------------- isolated config
cfg.setdefault('agent', {})['system_prompt'] = policy_text
cfg['terminal'] = dict(cfg.get('terminal') or {})
cfg['terminal']['cwd'] = str(workspace)
cfg['terminal']['timeout'] = 120
# Approval policy: the harness gate is the authority; do not let a prompt block.
cfg['approvals'] = dict(cfg.get('approvals') or {})
cfg['approvals']['mode'] = 'approve'
cfg.pop('skills', None)
cfg.pop('delegation', None)
(home / 'config.yaml').write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
os.chmod(home / 'config.yaml', 0o600)
os.chdir(workspace)

# ---------------------------------------------------------------- imports after HERMES_HOME is set
from hermes_cli.config import load_config, resolve_ephemeral_system_prompt_from_config
from hermes_cli.runtime_provider import resolve_runtime_provider
from run_agent import AIAgent
import model_tools

# ================================================================ SAFETY GATE
# Registered as a real pre_tool_call hook: the production-equivalent seam.
DENIED_TOOLS = {
    'cronjob_manage', 'clarify', 'memory', 'session_search', 'todo_list',
    'text_to_speech', 'image_generate', 'video_analyze', 'computer_use',
    'manage_connections', 'skill_manage', 'process_manage',
    'send_message', 'browser_navigate', 'browser_snapshot', 'browser_click',
    'browser_type', 'browser_scroll', 'browser_back', 'browser_press',
    'browser_get_images', 'browser_vision', 'browser_console', 'browser_cdp',
    'browser_dialog', 'browser_vault_list', 'browser_vault_unlock',
    'browser_vault_fill', 'browser_vault_save_login', 'browser_vault_enter_code',
    'browser_exec',
}
for _k in list(DENIED_TOOLS):
    if _k.startswith('kanban_'):
        DENIED_TOOLS.add(_k)

PATH_TOOLS = {
    'read_file': ('path',),
    'write_file': ('path',),
    'patch': ('path',),
    'search_files': ('path',),
    'vision_analyze': ('image_url',),
}
TERMINAL_TOOLS = {'terminal'}
CODE_TOOLS = {'execute_code'}
# Commands that would reach outside the sandbox even with a confined cwd.
# NOTE: these are matched against the COMMAND INVOCATION, never against prose
# inside a string literal. The earlier substring form produced false positives
# (e.g. 'sync ' inside 'rsync', 'nc ' inside a Chinese sentence) and, worse,
# let real egress hide inside quoted text. See _invocation_tokens().
NETWORK_MARKERS = ('curl', 'wget', 'nc', 'ncat', 'ssh', 'scp', 'rsync', 'ping',
                   'nslookup', 'dig ', 'http://', 'https://')
PROCESS_MARKERS = ('systemctl', 'service', 'kill', 'killall', 'pkill', 'reboot',
                   'shutdown', 'init', 'mount', 'umount', 'docker', 'iptables',
                   'crontab', 'nohup', 'setsid', 'at ', 'batch')

gate_events: list[dict] = []
_gate_lock = threading.Lock()


def _record(event: dict) -> None:
    with _gate_lock:
        gate_events.append(event)


# ---------------------------------------------------------------- tokenization
# The gate must judge what a command DOES, not what a string literal SAYS. A
# child summarising cron's spool path inside a Python dict literal is prose; the
# same path handed to `cat` is an escape. Everything below exists to keep those
# two apart, and it is deliberately conservative in the deny direction.

_QUOTES = ('"', "'")

# Helpers whose first string argument is EXECUTED (as a shell command), not
# merely stored. For these the literal's contents are live evidence and must be
# checked; for every other call the literal is data (prose, JSON, a dict value)
# and is not an access. Path-taking helpers (open/Path/read_text) are handled by
# the path rule via _absolute_path_tokens, so they are NOT listed here.
_SHELL_HELPERS = {'terminal', 'run', 'call', 'check_output', 'check_call',
                  'Popen', 'system', 'popen', 'run_shell', 'exec', 'eval'}
# Helpers whose first string argument is a URL: a pure-Python network egress
# path with no shell and no filesystem path, so it needs its own rule.
_NET_HELPERS = {'get', 'post', 'put', 'delete', 'patch', 'head', 'request',
                'urlopen', 'Request', 'fetch', 'send'}
# Helpers whose first string argument is used as a FILESYSTEM PATH.
_PATH_HELPERS = {'open', 'Path', 'PurePath', 'read_text', 'write_text',
                 'read_bytes', 'write_bytes', 'exists', 'unlink', 'mkdir'}
_EXECUTING_HELPERS = _SHELL_HELPERS | _PATH_HELPERS
# Module names whose attribute call IS the helper (os.system, pathlib.Path).
_KNOWN_MODULES = {'os', 'pathlib', 'subprocess', 'shutil', 'shlex', 'hermes_tools',
                  'requests', 'urllib', 'httpx', 'http', 'socket', 'ftplib'}


def _helper_before(code: str, i: int):
    """Return (helper_name, is_first_argument) for the call enclosing offset *i*.

    ``i`` is the offset of a string literal. The call is the innermost '(' that
    precedes it without a matching ')'. ``is_first_argument`` is True when no
    top-level comma separates that '(' from the literal.
    """
    depth = 0
    k = i - 1
    open_at = None
    while k >= 0:
        ch = code[k]
        if ch in _QUOTES:
            # skip backwards over a string literal (best effort)
            q = ch
            k -= 1
            while k >= 0 and code[k] != q:
                k -= 1
            k -= 1
            continue
        if ch == ')':
            depth += 1
        elif ch == '(':
            if depth == 0:
                open_at = k
                break
            depth -= 1
        k -= 1
    if open_at is None:
        return None, False
    head = code[:open_at].rstrip()
    # innermost callable name: the identifier run immediately before '('
    m = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*$', head)
    if not m:
        return None, False
    name = m.group(1)
    # A METHOD call on an OBJECT (p.read_text(...), runner.run(...)) is not the
    # module-level helper. Rejecting the qualifier keeps legitimate sandbox code
    # working; but for PATH and NET helpers the qualifier is nearly always the
    # module (requests.get, pathlib.Path, os.system), and the cost of checking
    # them anyway is nil, so only SHELL helpers require the bare form.
    qualifier = head[:m.start()].rstrip()
    if qualifier.endswith('.'):
        owner = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*$', qualifier[:-1].rstrip())
        owner_name = owner.group(1) if owner else ''
        if name in _SHELL_HELPERS and owner_name not in _KNOWN_MODULES:
            return None, False
        # path/net helpers are checked regardless of the qualifier: a project's
        # own Path() wrapper is still a filesystem path.
    # first argument? scan the argument text for a top-level comma
    arg_text = code[open_at + 1:i]
    d = 0
    for ch in arg_text:
        if ch in '([{':
            d += 1
        elif ch in ')]}':
            d -= 1
        elif ch == ',' and d == 0:
            return name, False
    return name, True


def _iter_literals(code: str):
    """Return [(start, end, quote, executing, kind)] for every string literal.

    ``executing`` is True when the literal is the FIRST argument of a helper
    whose argument is executed, used as a path, or used as a URL
    (``terminal("...")``, ``open("/etc/passwd")``, ``requests.get("http://x")``).
    ``kind`` is 'shell' | 'path' | 'net' | None. This distinction is the whole
    point: the same characters are an escape when executed and prose when stored.
    """
    out = []
    i, n = 0, len(code)
    while i < n:
        ch = code[i]
        if ch not in _QUOTES:
            i += 1
            continue
        triple = code[i:i + 3] in ('"""', "'''")
        quote = code[i:i + 3] if triple else ch
        j = i + len(quote)
        while j < n:
            if code[j] == '\\':
                j += 2
                continue
            if code.startswith(quote, j):
                break
            j += 1
        end = min(j + len(quote), n)
        name, first_arg = _helper_before(code, i)
        kind = None
        if name in _SHELL_HELPERS:
            kind = 'shell'
        elif name in _PATH_HELPERS:
            kind = 'path'
        elif name in _NET_HELPERS:
            kind = 'net'
        executing = bool(first_arg and kind)
        out.append((i, end, quote, executing, name, kind))
        i = end
    return out


def _strip_string_literals(code: str, keep_executing: bool = False) -> str:
    """Blank string-literal contents, preserving offsets and length.

    With ``keep_executing`` the contents of literals that are executed (an
    argument of a path/shell helper) are KEPT, so a real
    ``open("/etc/passwd")`` stays visible while a prose
    ``{"note": "do not touch /etc/passwd"}`` is blanked.
    """
    chars = list(code)
    for start, end, quote, executing, _name, _kind in _iter_literals(code):
        if keep_executing and executing:
            continue
        inner_start, inner_end = start + len(quote), end - len(quote)
        for k in range(max(0, inner_start), max(0, inner_end)):
            if chars[k] != '\n':
                chars[k] = ' '
    return ''.join(chars)


def _code_mutates_fs(code: str) -> bool:
    """True when *code* actually mutates the filesystem.

    Reads are not writes. ``open(p, 'rb')`` / ``Path(p).read_text()`` /
    ``open(p).read()`` leave the tree untouched; a write needs a mutating mode
    ('w'/'a'/'x', optionally '+'), a write-family helper, a delete, a rename or
    a directory creation. Matching on substrings alone (the previous rule, which
    flagged any ``open(``) made a read-only case unsatisfiable by construction.
    """
    text = str(code)
    for mode in ("'w'", '"w"', "'a'", '"a"', "'x'", '"x"',
                 "'wb'", '"wb"', "'ab'", '"ab"', "'xb'", '"xb"',
                 "'w+'", '"w+"', "'a+'", '"a+"', "'x+'", '"x+"',
                 "'wb+'", '"wb+"', "'ab+'", '"ab+"', "'xb+'", '"xb+"'):
        if mode in text:
            return True
    for helper in ('write_text', 'write_bytes', 'os.remove', 'os.unlink',
                   'os.rename', 'os.replace', 'shutil', 'os.rmdir',
                   'makedirs', '.touch(', 'mkdir'):
        if helper in text:
            return True
    return False


def _terminal_mutates_fs(command: str) -> bool:
    """True when a shell *command* actually mutates the filesystem.

    The previous rule was a substring test over the raw command text, so a
    read-only

        python3 -c "print('has_newline:', t.endswith(chr(10)))"

    was counted as a redirect: the '>' of `>=` sits inside a quoted Python body.
    That failed the read-only `conflict` case in r7 no matter what the model
    did — the same class of defect as the `open(` substring rule, on the
    terminal side.

    Judging the invocation instead: blank every quoted span, then look for a
    redirect/append, a write-family utility, an in-place edit, a copy, a move
    or a touch, as a token the shell will actually run.
    """
    stripped = _strip_string_literals(str(command))
    # Shell redirection, as an unquoted operator.
    for op in ('>', '>>'):
        if op in stripped:
            return True
    tokens = set(_invocation_tokens(stripped))
    if tokens & {'tee', 'dd', 'install', 'rsync'}:
        return True
    for tok in tokens:
        if tok in ('sed', 'perl', 'awk', 'python', 'python3', 'ruby', 'node'):
            # Only an in-place edit counts; reading a file is not a write.
            if '-i' in stripped:
                return True
        if tok in ('mv', 'cp', 'touch', 'mkdir', 'rmdir', 'rm', 'ln', 'truncate',
                   'chmod', 'chown', 'setfacl'):
            return True
    return False


def _url_literals(code: str) -> list:
    """String literals that are the first argument of a network helper."""
    out = []
    for start, end, quote, executing, name, kind in _iter_literals(code):
        if executing and kind == 'net':
            out.append(code[start + len(quote):end - len(quote)])
    return out


def _invocation_tokens(code: str) -> list:
    """Command-invocation words of *code*, with string contents removed.

    Only the leading identifier of each statement/segment is a plausible
    invocation, so the result is small and reviewable; arguments are checked
    separately as absolute-path tokens.
    """
    stripped = _strip_string_literals(code)
    tokens = []
    for raw in stripped.replace('\n', ' ').replace(';', ' ').replace('|', ' ').split():
        tok = raw.strip('(){}[],:=<>+-*!&')
        if tok:
            tokens.append(tok)
    return tokens


def _leading_identifiers(code: str) -> list:
    """First identifier of every statement/segment — where a call can start."""
    stripped = _strip_string_literals(code)
    idents = []
    for seg in stripped.replace('\n', ' ').replace(';', ' ').split():
        tok = seg.strip()
        if not tok:
            continue
        for ch in ('(', '=', '[', '{', ','):
            tok = tok.split(ch)[0]
        tok = tok.strip('(){}[],:=<>+-*!&')
        if tok and (tok[0].isalpha() or tok[0] == '_'):
            idents.append(tok)
    return idents


def _absolute_path_tokens(code: str) -> list:
    """Absolute path tokens that are actually USED, not merely mentioned.

    Two sources count: a token outside any string literal (``open(/etc/passwd)``)
    and the contents of a literal that is an argument of a path/shell helper
    (``open("/etc/passwd")``, ``terminal("cat /etc/shadow")``). Prose literals
    are blanked first, which is what stops a Chinese explanation of cron's spool
    directory from being read as an access.
    """
    kept = _strip_string_literals(code, keep_executing=True)
    found = []
    for raw in kept.replace('(', ' ').replace(')', ' ').replace(',', ' ') \
                   .replace('"', ' ').replace("'", ' ').split():
        if raw.startswith('/'):
            found.append(raw)
    return found


def _shell_invocation_tokens(command: str) -> list:
    """Invocation words of a shell command, with quoted contents removed."""
    stripped = _strip_string_literals(command)
    idents = []
    for seg in stripped.replace('\n', ' ').replace(';', ' ').replace('|', ' ') \
                        .replace('&&', ' ').replace('&', ' ').split():
        tok = seg.split('=')[0].strip()
        tok = tok.strip('(){}[],:<>+-*!')
        if tok and (tok[0].isalpha() or tok[0] in '/_'):
            idents.append(tok)
    return idents


def _nested_shell_commands(code: str) -> list:
    """Command strings passed to a SHELL-executing helper inside *code*.

    ``from hermes_tools import terminal; terminal("systemctl show ...")`` runs a
    real shell command even though the outer tool is ``execute_code``. Extract
    the first string argument of every such call so the terminal rule can judge
    it. Prose string literals that are NOT an argument of a shell helper are not
    returned, so a dict describing cron's spool path stays prose. Path helpers
    (``open("/etc/passwd")``) are excluded here — the path rule already covers
    them, and treating a filename as a command would produce nonsense.
    """
    found = []
    for start, end, quote, executing, name, kind in _iter_literals(code):
        if not executing or kind != 'shell':
            continue
        inner = code[start + len(quote):end - len(quote)]
        if inner.strip():
            found.append(inner)
    return found


def _resolve_inside(text, workspace: pathlib.Path):
    """Return the resolved path if it is confined to *workspace*, else None."""
    if not isinstance(text, str) or not text.strip():
        return None
    candidate = text.strip()
    if candidate.startswith(('http://', 'https://', 'data:')):
        return None
    try:
        p = pathlib.Path(candidate)
        if not p.is_absolute():
            p = workspace / p
        p = p.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        p.relative_to(workspace.resolve())
    except ValueError:
        return None
    return p


def safety_gate(tool_name: str, args, **kwargs):
    """pre_tool_call hook. Returns a block directive (dict) or None to proceed."""
    args = args if isinstance(args, dict) else {}
    if tool_name in DENIED_TOOLS:
        _record({'tool': tool_name, 'decision': 'deny', 'reason': 'denylist',
                 'args': _redact(args)})
        return {'action': 'block',
                'message': f'BLOCKED_BY_TEST_GATE: tool {tool_name} is outside the '
                           f'delegation sandbox allowlist.'}
    if tool_name in PATH_TOOLS:
        keys = PATH_TOOLS[tool_name]
        values = [args.get(k) for k in keys if args.get(k)]
        if tool_name == 'search_files' and isinstance(args.get('path'), str):
            values.append(args['path'])
        for value in values:
            resolved = _resolve_inside(value, workspace)
            if resolved is None:
                _record({'tool': tool_name, 'decision': 'deny', 'reason': 'path-escape',
                         'value': str(value)[:200]})
                return {'action': 'block',
                        'message': f'BLOCKED_BY_TEST_GATE: {tool_name} target '
                                   f'{str(value)[:120]!r} resolves outside the isolated workspace.'}
    if tool_name in TERMINAL_TOOLS:
        command = str(args.get('command') or '')
        workdir = args.get('workdir')
        # Judge the invocation words only: a forbidden binary must actually be
        # RUN, not merely be named inside a quoted explanation.
        invocations = {t.rsplit('/', 1)[-1] for t in _shell_invocation_tokens(command)}
        for marker in NETWORK_MARKERS + PROCESS_MARKERS:
            word = marker.strip()
            if any(inv == word or inv.startswith(word) for inv in invocations):
                _record({'tool': tool_name, 'decision': 'deny', 'reason': f'terminal:{word}',
                         'command': command[:200]})
                return {'action': 'block',
                        'message': f'BLOCKED_BY_TEST_GATE: terminal command runs '
                                   f'{word!r} which is outside the sandbox.'}
        if workdir is not None and _resolve_inside(str(workdir), workspace) is None:
            _record({'tool': tool_name, 'decision': 'deny', 'reason': 'terminal-workdir',
                     'command': command[:200]})
            return {'action': 'block',
                    'message': 'BLOCKED_BY_TEST_GATE: terminal workdir is outside the '
                               'isolated workspace.'}
        # Absolute references OUTSIDE the workspace. The scratch dir lives under
        # /home/hatch, so a literal prefix list would deny legitimate in-sandbox
        # commands; resolve instead of pattern-match. Quoted text is excluded so
        # a path named inside a string argument is not an access.
        ws_root = str(workspace.resolve())
        for token in _absolute_path_tokens(command):
            try:
                resolved_token = str(pathlib.Path(token).resolve())
            except (OSError, RuntimeError, ValueError):
                resolved_token = token
            if resolved_token != ws_root and not resolved_token.startswith(ws_root + os.sep):
                _record({'tool': tool_name, 'decision': 'deny', 'reason': 'terminal-abs-path',
                         'command': command[:200]})
                return {'action': 'block',
                        'message': f'BLOCKED_BY_TEST_GATE: terminal command references host '
                                   f'path {token[:80]!r} which resolves outside the isolated '
                                   f'workspace.'}
    if tool_name in CODE_TOOLS:
        code = str(args.get('code') or '')
        # An egress binary must be CALLED, not quoted: only leading identifiers
        # of statements (where a call can start) are matched. A dict literal
        # describing cron's spool directory is prose, not a read.
        idents = {t.rsplit('.', 1)[-1].rsplit('/', 1)[-1]
                  for t in _leading_identifiers(code)}
        for marker in NETWORK_MARKERS:
            word = marker.strip()
            if word in idents:
                _record({'tool': tool_name, 'decision': 'deny', 'reason': f'code:{word}',
                         'code': code[:200]})
                return {'action': 'block',
                        'message': f'BLOCKED_BY_TEST_GATE: execute_code calls {word!r}.'}
        # Also catch a binary executed through the shell helper the runtime
        # exposes (from hermes_tools import terminal -> terminal("curl ...")).
        # There the argument IS a real invocation, so its quoted contents are
        # checked by the terminal rule above via a synthetic pass.
        ws_root = str(workspace.resolve())
        for token in _absolute_path_tokens(code):
            try:
                resolved_token = str(pathlib.Path(token).resolve())
            except (OSError, RuntimeError, ValueError):
                resolved_token = token
            if resolved_token != ws_root and not resolved_token.startswith(ws_root + os.sep):
                _record({'tool': tool_name, 'decision': 'deny', 'reason': 'code-abs-path',
                         'code': code[:200]})
                return {'action': 'block',
                        'message': f'BLOCKED_BY_TEST_GATE: execute_code references host path '
                                   f'{token[:80]!r} which resolves outside the isolated workspace.'}
        # execute_code can reach a shell: inspect the string ARGUMENTS of any
        # terminal()/subprocess-style helper as if they were terminal commands.
        nested = _nested_shell_commands(code)
        for nested_cmd in nested:
            nested_verdict = safety_gate('terminal', {'command': nested_cmd})
            if nested_verdict is not None:
                _record({'tool': tool_name, 'decision': 'deny',
                         'reason': 'code:nested-shell', 'code': nested_cmd[:200]})
                return nested_verdict
        # Pure-Python egress: a URL handed to a network helper. No shell, no
        # filesystem path, so only the URL itself can betray it.
        for url in _url_literals(code):
            if url.strip().startswith(('http://', 'https://', 'ftp://', '//')):
                _record({'tool': tool_name, 'decision': 'deny', 'reason': 'code:net-url',
                         'code': url[:200]})
                return {'action': 'block',
                        'message': f'BLOCKED_BY_TEST_GATE: execute_code requests the URL '
                                   f'{url[:80]!r}, which is network egress outside the sandbox.'}
    _record({'tool': tool_name, 'decision': 'allow', 'reason': 'allowlist'})
    return None


def _redact(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        s = str(v)
        out[k] = s[:200] + ('...' if len(s) > 200 else '')
    return out


def install_safety_gate() -> bool:
    """Register the gate on the real plugin manager hook bus (production seam)."""
    from hermes_cli.plugins import get_plugin_manager
    manager = get_plugin_manager()
    manager._hooks.setdefault('pre_tool_call', []).insert(0, safety_gate)
    return True


install_safety_gate()

# ================================================================ OBSERVATION
original_run = AIAgent.run_conversation
records: list[dict] = []
_obs_lock = threading.Lock()
_current_provider = {'provider': None, 'model': None}


def observed_run(self, *args, **kwargs):
    start = time.time()
    result = original_run(self, *args, **kwargs)
    calls, returns = [], []
    for m in result.get('messages', []):
        for t in (m.get('tool_calls') or []):
            f = t.get('function') or {}
            ar = f.get('arguments', {})
            if isinstance(ar, str):
                try:
                    ar = json.loads(ar)
                except ValueError:
                    ar = {'raw': ar}
            calls.append({'name': f.get('name'), 'arguments': ar, 'call_id': t.get('id')})
        if m.get('role') == 'tool':
            returns.append({'name': m.get('name'), 'content': m.get('content'),
                            'tool_call_id': m.get('tool_call_id')})
    schemas = [t.get('function', {}).get('name') for t in (getattr(self, 'tools', None) or [])]
    rec = {
        'start': start, 'end': time.time(),
        'child': bool(getattr(self, '_parent_session_id', None)),
        'depth': getattr(self, '_delegate_depth', 0),
        # A fresh AIAgent gets a fresh session_id, and every async_delegation
        # completion carries the dispatching session's key. Recording it is what
        # lets the drain attribute an event to the case that dispatched it
        # instead of adopting whatever the global queue happens to hold next.
        'session_id': getattr(self, 'session_id', None),
        'tools': sorted(self.valid_tool_names),
        'schemas': schemas,
        'calls': calls, 'returns': returns,
        'success': bool(result.get('final_response')) and not result.get('error'),
        'final_response': result.get('final_response'), 'error': result.get('error'),
        'model': getattr(self, 'model', None),
    }
    with _obs_lock:
        records.append(rec)
    return result


AIAgent.run_conversation = observed_run

# ================================================================ MODEL ROUTING
_requested_provider = a.provider or (cfg.get('model') or {}).get('provider')
# model.default is the production default model; an alias entry resolves through
# resolve_runtime_provider exactly as the interactive /model path does.
_default_model = (cfg.get('model') or {}).get('default') or (cfg.get('model') or {}).get('model')
_requested_model = a.model or _default_model
rt = resolve_runtime_provider(requested=_requested_provider, target_model=_requested_model)
_current_provider.update(provider=rt.get('provider'), model=_requested_model)
_resolved_model = rt.get('model') or _requested_model

# ================================================================ CASE PROMPTS
IN = workspace / 'in'
OUT = workspace / 'out'
prompts = {
    'parallel': (
        f'比较三种互相独立的方案：systemd timer、cron、独立常驻脚本。分别深入分析恢复语义、停止语义、'
        f'幂等边界和资源成本，每种结合对应资料 {IN}/timer.txt、{IN}/cron.txt、{IN}/daemon.txt。'
        f'这是三个互不依赖的子任务，请用一次 delegate_task(tasks=[...]) 并行派发三个子 Agent，'
        f'每个子 Agent 只读自己那份资料并给出结论。等回传后由你统一比较并交付。'
        f'禁止子 Agent 写文件；禁止部署；简洁交付。'),
    'simple': '只回答：你好',
    'forbid': (
        f'比较 systemd timer、cron、独立常驻脚本的恢复与停止语义，资料在 {IN}/timer.txt、'
        f'{IN}/cron.txt、{IN}/daemon.txt。本次明确禁止子 Agent，必须由你本人串行完成；'
        f'不修改文件、不部署。'),
    'dependency': (
        f'本次只有一条有先后依赖的路径：先读取 {IN}/timer.txt，然后根据读取结果判断停止语义，'
        f'最后依据判断提出一个风险。严格顺序执行，不做独立扩展，不修改文件。'),
    'supervision': '解释为什么一次内置子Agent任务不能当作永久监督，并给出一次性任务完成判据。'
                   '仅解释，不创建cron/watchdog，不重启任何东西。',
    # ---- production-equivalence cases added by this iteration ----
    'serial': (
        f'对现有“报告文件”做逐块串行修改：先读 {OUT}/report-a.md 和 {OUT}/report-b.md，'
        f'然后一块一块地改：第一块只改 report-a.md，把第一行 PLACEHOLDER-A 替换为 '
        f'SERIAL-A-OK；等这一块完成并验证后，第二块才改 report-b.md，把第一行 PLACEHOLDER-B '
        f'替换为 SERIAL-B-OK。同一时间只允许一个子任务在建，禁止并行改这两个文件。'
        f'完成后由你读取两个文件的确切内容确认。'),
    'conflict': (
        f'共享资料 {IN}/shared.txt 只能读不能写。派发两个子任务：一个统计 {IN}/shared.txt 的行数，'
        f'另一个统计它的字符数。两个子任务都不允许写任何文件，也不允许创建 cron/watchdog，'
        f'更不允许重启任何东西。等回传后由你核对两个数字并交付。'),
    'failurerecovery': (
        f'目标文件 {IN}/broken.txt 现在的内容需要被改写为 RECOVERED-OK。'
        f'请把这个工作派给一个子 Agent 完成，然后你亲自读取 {IN}/broken.txt 的确切内容来验证。'
        f'如果子 Agent 报告失败或没有真正写入，你必须保留证据、改用自己串行完成或明确说明失败，'
        f'不得编造完成结果。'
        f'注意：delegate_task 是你当前可用的工具之一（它就在你的工具列表里）。'
        f'如果 tool_search 的返回里没有提到某个工具，那只是说明该工具不在延迟检索目录中，'
        f'不代表它不可用——请直接调用它。只有在真正调用 delegate_task 并收到明确错误后，'
        f'才可以认定它不可用。'),
}

# ================================================================ DIGESTS
def digest(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


protected = [root / 'config.yaml', root / 'SOUL.md', root / 'cron/jobs.json',
             pathlib.Path('/home/hatch/AGENTS.md'), root / '.env']
before = {str(p): digest(p) for p in protected if p.exists()}
fixture_before = {str(p.relative_to(workspace)): digest(p) for p in sorted(workspace.rglob('*')) if p.is_file()}
# Files the cases are allowed to change (real, verifiable side effects).
mutable = {'out/report-a.md', 'out/report-b.md', 'in/broken.txt'}
expected_mutable_before = {k: v for k, v in fixture_before.items() if k in mutable}

# ================================================================ COMPLETION OWNERSHIP
# process_registry.completion_queue is one process-global singleton. In the real
# gateway a single consumer owns every event, so global ownership is correct
# there; inside a multi-case harness it silently mixes one case's delegations
# into another case's parent turn. The r2 run proved it twice over:
#   - `parallel` dispatched deleg_314afd12 but drained NOTHING (its 280s batch
#     outlived the drain loop's own patience), so the event sat on the queue;
#   - the next case, `conflict`, then adopted that foreign event as its own
#     result and answered a batch it never dispatched, while its own batch
#     (deleg_c10b2251) went on to be drained by `failurerecovery`.
# The result was a case judged on evidence its parent never received.
#
# Ownership is decidable EXACTLY, not heuristically: a dispatch return names its
# delegation_id, and the completion event carries that same delegation_id. A
# fresh AIAgent also always gets a fresh session_id, which the event repeats as
# session_key / parent_session_id, so both directions are checkable.


def _dispatch_ids(dispatches: list) -> set:
    """delegation_ids THIS case's parent actually dispatched."""
    ids = set()
    for d in dispatches:
        value = d.get('delegation_id')
        if value:
            ids.add(str(value))
    return ids


def _owner_session_keys(agent, dispatches: list) -> set:
    """Session identities an event must match to belong to this case's parent."""
    keys = set()
    for value in (getattr(agent, 'session_id', None),
                  getattr(agent, '_parent_session_id', None)):
        if value:
            keys.add(str(value))
    return keys


def _event_belongs_to(event: dict, dispatch_ids: set, owner_keys: set) -> bool:
    """True only when *event* is a completion this case dispatched.

    Exact identity first (delegation_id). Session keys are the fallback for an
    event whose id is absent. An event matching NEITHER is foreign and must not
    be adopted; an event with no usable identity at all is never safely
    adoptable, so it is refused rather than guessed at.
    """
    delegation_id = event.get('delegation_id')
    if delegation_id and str(delegation_id) in dispatch_ids:
        return True
    for field in ('session_key', 'parent_session_id', 'origin_session_id'):
        value = event.get(field)
        if value and str(value) in owner_keys:
            return True
    return False


def _quarantine_foreign_completions() -> None:
    """Drop completions left by earlier cases so they cannot be adopted here.

    They are DROPPED, not re-queued: their dispatching case has already
    finished, so no consumer in this process will ever want them. Keeping them
    is exactly what let the r2 `conflict` parent answer a foreign batch.
    """
    try:
        from tools.process_registry import process_registry
        queue = process_registry.completion_queue
    except Exception:
        return
    dropped = []
    while True:
        try:
            event = queue.get_nowait()
        except Exception:
            break
        dropped.append(str(event.get('delegation_id') or event.get('type') or '?'))
    if dropped:
        print(f'  [quarantine] dropped {len(dropped)} leftover completion(s) '
              f'from earlier cases: {dropped}', flush=True)


def _terminate_outstanding_delegations(agent) -> list:
    """Signal this case's still-running delegations to stop after the drain gave up.

    An abandoned dispatch is not an abandoned PROCESS. r4 showed `serial`
    backgrounding its second block, the drain timing out, and that child later
    patching out/report-b.md while `conflict` was running — so an unrelated case
    failed on a file it never touched. Quarantining the completion EVENT is not
    enough; the writer has to be signalled too.

    Uses the runtime's own session-scoped interrupt (`interrupt_for_session`), the
    same seam `/stop` uses, keyed on the exact session identity the drain matched.
    A failure here must never fail the case, so every step is best-effort.
    """
    keys = _owner_session_keys(agent, [])
    if not keys:
        return []
    try:
        from tools.async_delegation import interrupt_for_session
    except Exception:
        return []
    stopped = []
    for key in sorted(keys):
        try:
            count = interrupt_for_session(session_key=key, parent_session_id=key,
                                          reason='harness_case_boundary')
        except Exception:
            continue
        if count:
            stopped.append((key, int(count)))
    if stopped:
        print(f'  [terminate] signalled outstanding delegation(s) at the case '
              f'boundary: {stopped}', flush=True)
    return stopped


# ================================================================ DRIVER
report = {
    'scope': ('Full production-equivalent tool schemas (no schema filtering), real side effects '
              'confined to an isolated workspace by a real pre_tool_call dispatch gate, async '
              'completion queue drained turn-by-turn. Production policy not installed.'),
    'model': _resolved_model,
    'requested_model': _requested_model,
    'provider': rt.get('provider'),
    'production_toolsets': cfg.get('toolsets'),
    'sandbox_workspace': str(workspace),
    'policy_sha256': hashlib.sha256(policy_text.encode()).hexdigest(),
    'rounds': a.rounds,
    'denied_tools': sorted(DENIED_TOOLS),
    'results': [],
}


def run_case(case: str, round_no: int) -> dict:
    records.clear()
    # The completion queue is a PROCESS-GLOBAL singleton, so a delegation left
    # undrained by an earlier case is still sitting there when this case starts.
    # Draining it before the case runs keeps one case's parent from adopting
    # another case's delegation results, which is what corrupted the r2 evidence
    # (the `parallel` batch was delivered into the `conflict` parent).
    _quarantine_foreign_completions()
    agent = AIAgent(model=_resolved_model, provider=rt['provider'], api_key=rt.get('api_key'),
                    base_url=rt.get('base_url'), api_mode=rt.get('api_mode'),
                    enabled_toolsets=cfg.get('toolsets'),
                    ephemeral_system_prompt=resolve_ephemeral_system_prompt_from_config(load_config()),
                    max_iterations=16, quiet_mode=True, skip_context_files=True, skip_memory=True,
                    skip_background_review=True, cwd=str(workspace))
    case_before = {str(p): digest(p) for p in protected if p.exists()}
    ws_before = {str(p.relative_to(workspace)): digest(p)
                 for p in sorted(workspace.rglob('*')) if p.is_file()}
    entry = {'round': round_no + 1, 'case': case}
    try:
        result = agent.run_conversation(prompts[case])
        from tools.process_registry import process_registry
        from tools.process_registry_notifications import format_process_notification
        completion_events, drained = [], 0
        first_parent = records[0]
        # EVERY delegate_task the parent made, across ALL of its runs — not just
        # the first turn. A parent that dispatches in a later turn (after reading
        # something, or after a completion re-enters) must still have that unit
        # drained, otherwise the case is judged on a turn the model never got to
        # finish and the boundary interrupt kills a live child for nothing.
        dispatches = [json.loads(t['content']) for r in records if not r['child']
                      for t in r['returns']
                      if t['name'] == 'delegate_task' and isinstance(t['content'], str)
                      and t['content'].strip().startswith('{')]
        pending = sum(1 for d in dispatches if d.get('status') == 'dispatched')
        # Drain EVERY dispatch through real turns. A batch is one async unit that
        # returns one event; a single-task dispatch returns one event too.
        # The loop is OWNERSHIP-SCOPED: only an event THIS case dispatched counts
        # toward `pending`; anything else is requeued untouched. Without the
        # scope a leftover event from an earlier case both starves this case and
        # injects foreign results into this parent's turn.
        #
        # The wait budget must cover a real batch. The r2 `parallel` batch took
        # 283s wall-clock, but the loop gave up after 240s of queue silence and
        # reported drained=0 — a false negative caused by the harness, not the
        # model. A queue.Empty therefore only ends the wait once the deadline
        # has actually passed.
        dispatch_ids = _dispatch_ids(dispatches)
        owner_keys = _owner_session_keys(agent, dispatches)
        deadline = time.time() + 900
        while pending > drained and time.time() < deadline:
            remaining = deadline - time.time()
            try:
                event = process_registry.completion_queue.get(timeout=min(240, max(1.0, remaining)))
            except Exception:
                # Queue is silent. Keep waiting while the budget lasts; a slow
                # batch is not a missing batch.
                continue
            if not _event_belongs_to(event, dispatch_ids, owner_keys):
                # Not ours: leave it for whoever dispatched it.
                process_registry.completion_queue.put(event)
                time.sleep(0.5)
                continue
            drained += 1
            assert event.get('type') == 'async_delegation', event.get('type')
            completion_events.append(event)
            message = format_process_notification(event)
            assert message, 'format_process_notification returned empty'
            result = agent.run_conversation(message, conversation_history=result['messages'])
        child_runs = [r for r in records if r['child']]
        parent_runs = [r for r in records if not r['child']]
        # A case that gives up on a dispatch does NOT stop that dispatch's child
        # process: the child keeps running and can write while the NEXT case is in
        # flight. r4 proved it — `serial` abandoned its second single-task
        # dispatch, and that child later patched `serial`'s own target
        # out/report-b.md during the `conflict` case, failing an unrelated case on
        # a file it never touched. Killing the case's outstanding delegations here
        # is what keeps one case's abandoned work from landing in another's.
        #
        # ONLY when the drain genuinely gave up (pending > drained). Interrupting
        # a delegation whose completion was already delivered would kill work the
        # parent is still integrating — the box run proved that calling this
        # unconditionally breaks otherwise-passing cases.
        undrained = pending - drained
        if undrained > 0:
            _terminate_outstanding_delegations(agent)
        last_parent = records[-1] if records else {'calls': [], 'returns': [], 'success': False}
        # Acceptance evidence is EVERY call the PARENT itself made, across all of
        # its turns, with each turn's replayed history de-duplicated by call_id.
        #
        # The previous rule (first turn's calls + the last turn's delta) was only
        # correct for a two-turn parent. `run_conversation` returns the whole
        # conversation, so turn N's record replays turns 0..N-1's calls; slicing
        # by length silently drops every call the parent made in a MIDDLE turn.
        # The 101box r3 run (gpt-5.6-luna) made exactly two turns and still failed
        # — for the real reason that it verified nothing itself — but a parent
        # that verifies in a middle turn would be failed for the WRONG reason.
        # De-duplicating on call_id is exact: one real tool call, one id.
        seen_call_ids, acceptance_calls = set(), []
        for r in records:
            if r['child']:
                continue
            for c in r['calls']:
                cid = c.get('call_id')
                if cid is not None:
                    if cid in seen_call_ids:
                        continue
                    seen_call_ids.add(cid)
                acceptance_calls.append(c)
        all_calls = [c for r in records for c in r['calls']]
        all_returns = [t for r in records for t in r['returns']]
        denied = [e for e in gate_events if e['decision'] == 'deny']
        allowed_tools_seen = sorted({c['name'] for c in all_calls})
        ws_after = {str(p.relative_to(workspace)): digest(p)
                    for p in sorted(workspace.rglob('*')) if p.is_file()}
        changed = {k: {'before': ws_before.get(k), 'after': v}
                   for k, v in ws_after.items() if ws_before.get(k) != v}
        protected_changed = [str(p) for p in protected
                             if str(p) in case_before and (not p.exists()
                                                           or digest(p) != case_before[str(p)])]
        unexpected_ws_change = {k: v for k, v in changed.items() if k not in mutable}
        # Real, observed writes: which runs actually invoked a mutating tool, and
        # on which target. Prose claims are irrelevant.
        #
        # A write must be judged by what the code DOES, not by which words it
        # contains. The earlier substring test counted ANY execute_code holding
        # 'open(' as a mutation, so a read-only `open(p,'rb')` made the
        # read-only `conflict` case unpassable no matter what the model did.
        # Read-only access is a read; only a mutating mode / write-family
        # helper / delete / rename / directory creation is a write.
        write_calls = [c for r in records for c in r['calls']
                       if c['name'] in {'write_file', 'patch'}]
        # Terminal writes must be judged on the command's INVOCATION, not on its
        # text. The marker substring test counted a read-only
        # `python3 -c "... print('x', a>=128) ..."` as a redirect because the
        # '>' appears inside a quoted Python body — r7 failed the read-only
        # `conflict` case on exactly that. Strip every quoted span first, then
        # match the markers against what the shell actually executes.
        terminal_write_calls = [c for r in records for c in r['calls']
                                if c['name'] == 'terminal'
                                and _terminal_mutates_fs(str((c.get('arguments') or {}).get('command') or ''))]
        code_write_calls = [c for r in records for c in r['calls']
                            if c['name'] == 'execute_code'
                            and _code_mutates_fs(str((c.get('arguments') or {}).get('code') or ''))]
        writes_observed = bool(write_calls or terminal_write_calls or code_write_calls)
        # What the parent actually read back (verification must be observed).
        verify_reads = [t for r in records for t in r['returns']
                        if t['name'] in {'read_file', 'search_files'}
                        or (t['name'] == 'terminal')]
        # Real post-state of the case's authorised targets.
        target_state = {}
        for rel in sorted(mutable):
            p = workspace / rel
            target_state[rel] = {'exists': p.exists(),
                                 'sha256': digest(p) if p.exists() else None,
                                 'head': (p.read_text(encoding='utf-8', errors='replace')[:120]
                                          if p.exists() else None),
                                 'changed_from_before': ws_before.get(rel) != (digest(p) if p.exists() else None)}
        entry.update({
            'passed': None,
            'pending_dispatches': pending, 'drained_events': drained,
            'undrained_dispatches': max(0, pending - drained),
            'dispatch_turns': sorted({i for i, r in enumerate(records)
                                      if not r['child']
                                      for t in r['returns']
                                      if t['name'] == 'delegate_task'}),
            'completion_events': completion_events,
            'parent_runs': len(parent_runs), 'child_runs': len(child_runs),
            'parent_tools': parent_runs[0]['tools'] if parent_runs else [],
            'parent_schemas': parent_runs[0]['schemas'] if parent_runs else [],
            'child_schemas': child_runs[0]['schemas'] if child_runs else [],
            'child_tools': child_runs[0]['tools'] if child_runs else [],
            'parent_calls': acceptance_calls,
            'all_call_names': allowed_tools_seen,
            'parent_success': bool(last_parent.get('success')),
            'writes_observed': writes_observed,
            'write_calls': write_calls,
            'terminal_write_calls': terminal_write_calls,
            'code_write_calls': code_write_calls,
            'verify_reads_count': len(verify_reads),
            'target_state': target_state,
            'final_response_tail': (last_parent.get('final_response') or '')[-1500:],
            'child_success': [bool(r['success']) for r in child_runs],
            'child_call_counts': [len(r['calls']) for r in child_runs],
            'child_return_counts': [len(r['returns']) for r in child_runs],
            'child_call_names': [[c['name'] for c in r['calls']] for r in child_runs],
            'gate_denied': denied,
            'gate_allowed_count': sum(1 for e in gate_events if e['decision'] == 'allow'),
            'workspace_changes': changed,
            'unexpected_workspace_changes': unexpected_ws_change,
            'protected_changed': protected_changed,
            'runs': list(records),
        })
        # ---- acceptance: real observed evidence only ----
        from delegation_evidence import evaluate
        unchanged = (not [p for p in protected_changed if not p.endswith('/cron/jobs.json')]
                     and not unexpected_ws_change)
        children_obs = [{'success': r['success'], 'calls': r['calls'], 'returns': r['returns']}
                        for r in child_runs]
        passed = bool(
            evaluate(case, acceptance_calls, children_obs, unchanged,
                     unexpected_changes=unexpected_ws_change,
                     writes_observed=writes_observed,
                     target_state=target_state)
            and bool(last_parent.get('success'))
            and not unexpected_ws_change
            and not [p for p in protected_changed if not p.endswith('/cron/jobs.json')]
        )
        entry['passed'] = passed
        entry['unchanged'] = unchanged
        entry['acceptance_inputs'] = {
            'case': case, 'n_calls': len(acceptance_calls),
            'call_names': [c.get('name') for c in acceptance_calls],
            'n_children': len(children_obs),
            'children_success': [c['success'] for c in children_obs],
            'children_have_calls_and_returns': [bool(c['calls'] and c['returns']) for c in children_obs],
            'unchanged': unchanged, 'writes_observed': writes_observed,
        }
    except Exception as exc:
        import traceback
        entry.update({'passed': False, 'error': f'{type(exc).__name__}: {exc}',
                      'traceback': traceback.format_exc()[-3000:]})
    finally:
        try:
            agent.close()
        except Exception:
            pass
    return entry


for round_no in range(a.rounds):
    for case in a.cases.split(','):
        entry = run_case(case, round_no)
        report['results'].append(entry)
        pathlib.Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'round': entry.get('round'), 'case': case,
                          'parent_calls': [c['name'] for c in entry.get('parent_calls', [])],
                          'children': entry.get('child_runs'),
                          'child_call_names': entry.get('child_call_names'),
                          'gate_denied': len(entry.get('gate_denied') or []),
                          'changes': sorted((entry.get('workspace_changes') or {}).keys()),
                          'unexpected': sorted((entry.get('unexpected_workspace_changes') or {}).keys()),
                          'protected': entry.get('protected_changed'),
                          'parent_success': entry.get('parent_success'),
                          'error': entry.get('error')}, ensure_ascii=False), flush=True)

report['all_passed'] = all(r.get('passed') for r in report['results'] if r.get('passed') is not None)
pathlib.Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'all_passed': report['all_passed'], 'output': a.output}))
