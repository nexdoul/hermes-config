#!/usr/bin/env python3
"""本地验证、增量传输、可恢复的 SSH 原子发布。远端只运行 shell/rsync/curl。"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
import yaml

HOSTS = {'krvps', 'usvps', 'hkvps', 'cnvps'}
PROTECTED = {'uploads', 'logs', '.env'}
EXCLUDES = PROTECTED | {'.git', 'node_modules', '__pycache__', '.remote-dev', '.pytest_cache', '.venv', 'venv'}
REQUIRED = {'host', 'remote_path', 'local_path', 'build_command', 'test_command',
            'restart_command', 'health_url', 'health_keyword', 'github_repo'}

class Failure(RuntimeError):
    """拒绝不安全状态或操作失败。"""

def run(argv, **kw):
    p = subprocess.run(argv, text=True, capture_output=True, **kw)
    if p.returncode:
        raise Failure(f'命令失败({p.returncode}): {p.stderr.strip()} {p.stdout.strip()}')
    return p.stdout

def safe_path(value, local=False):
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts or not re.fullmatch(r'/[A-Za-z0-9_./-]+', value):
        raise Failure('路径必须为无特殊字符的绝对路径，不能包含 ..')
    if any(x in value or (local and x in str(p.resolve())) for x in ('.reverse-ssh-104', 'ssh-infra')):
        raise Failure('禁止访问 104 隧道或 ssh-infra')
    if local:
        if not p.resolve().is_relative_to(Path('/home/hatch')) or p.resolve() == Path('/home/hatch'):
            raise Failure('本地项目必须在 /home/hatch 的子目录')
    elif len(p.parts) < 3 or p.parts[1] in {'etc', 'proc', 'sys', 'dev', 'bin', 'sbin', 'usr', 'boot'} or value.rstrip('/') in {'/var/www', '/home/hatch', '/root', '/srv', '/opt'}:
        raise Failure('危险远端路径')
    return str(p)

def load_config(path, allow_missing=False):
    c = yaml.safe_load(Path(path).read_text())
    allowed = REQUIRED | {'git_url', 'excludes', 'health_attempts', 'health_interval', 'command_timeout', 'transaction_timeout'}
    if not isinstance(c, dict) or not REQUIRED <= c.keys() or c.keys() - allowed:
        raise Failure('配置缺少必需字段或包含未支持字段（禁止 local backend）')
    if any(not isinstance(c[k], str) or not c[k].strip() or '\n' in c[k] or '\r' in c[k] for k in REQUIRED):
        raise Failure('必需字段必须为非空字符串')
    if c['host'] not in HOSTS:
        raise Failure('仅允许已审批 SSH 别名')
    c['remote_path'] = safe_path(c['remote_path'])
    c['local_path'] = safe_path(c['local_path'], True)
    if not allow_missing and not Path(c['local_path']).is_dir():
        raise Failure('本地项目不存在')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', c['github_repo']) or c['github_repo'].split('/')[1] in {'.', '..'}:
        raise Failure('github_repo 必须为 OWNER/REPO')
    if 'git_url' in c:
        github_url(c['git_url'], c['github_repo'])
    custom = c.get('excludes', [])
    if not isinstance(custom, list) or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', x) or x in {'.', '..'} for x in custom):
        raise Failure('excludes 仅允许安全单组件名称列表，不支持路径/glob')
    c['excludes'] = sorted(EXCLUDES | set(custom))
    if not re.fullmatch(r'https?://[^\s]+', c['health_url']) or re.search(r'https?://[^/]*@', c['health_url']):
        raise Failure('健康 URL 无效或包含凭据')
    if any(x in c['health_url'] for x in ('?', '#')):
        raise Failure('健康 URL 不允许查询参数/fragment，避免凭据')
    # 远端重启只允许单个服务或容器重启命令，不接受 shell 重活或主机重启。
    if not re.fullmatch(r'(?:systemctl (?:--user )?restart [A-Za-z0-9_.@-]+(?:\.service)?|(?:docker|podman) restart [A-Za-z0-9_.-]+)', c['restart_command']):
        raise Failure('restart_command 仅允许 systemctl/docker/podman restart 单个服务')
    for k in ('build_command', 'test_command'):
        if re.search(r'(?:https?://|ssh://)[^\s/]*@|\b(?:ssh|scp|rsync|reboot|shutdown)\b|\.reverse-ssh-104|ssh-infra', c[k]):
            raise Failure('本地命令含远端操作、危险操作或凭据 URL')
    for k, default, maximum in [('health_attempts', 5, 30), ('health_interval', 2, 30), ('command_timeout', 120, 600), ('transaction_timeout', 900, 3600)]:
        v = c.get(k, default)
        if type(v) is not int or not 1 <= v <= maximum:
            raise Failure(f'{k} 超出范围')
        c[k] = v
    return c

def github_url(url, repo):
    """Only credential-free, exact GitHub repository URLs; never echo rejected input."""
    if not isinstance(url, str):
        raise Failure('Git URL 必须对应 github_repo，且不含凭据')
    valid = {f'https://github.com/{repo}', f'https://github.com/{repo}.git',
             f'git@github.com:{repo}', f'git@github.com:{repo}.git',
             f'ssh://git@github.com/{repo}', f'ssh://git@github.com/{repo}.git'}
    if url not in valid:
        raise Failure('Git URL 必须对应 github_repo，且不含凭据')


def github_private(c):
    try:
        data = json.loads(run(['gh', 'repo', 'view', c['github_repo'], '--json',
                               'nameWithOwner,isPrivate'], timeout=c['command_timeout']))
    except (Failure, ValueError):
        raise Failure('GitHub 私有仓库验证失败；检查现有 gh 认证与仓库权限') from None
    if data.get('isPrivate') is not True or data.get('nameWithOwner') != c['github_repo']:
        raise Failure('GitHub 仓库不是私有仓库或名称不匹配')


def git(c, *args):
    # Per-command helper only; no global config or credential writes.
    return run(['git', '-c', 'credential.helper=!gh auth git-credential', *args],
               cwd=c['local_path'], timeout=c['command_timeout'])


def origin_urls(c, push=False):
    # Read stored URLs before insteadOf expansion (test fixtures rewrite to local bare).
    data = git(c, 'config', '--get-regexp', r'^remote\.origin\.(url|pushurl)$')
    entries = [line.split(' ', 1) for line in data.splitlines()]
    urls = [v for k, v in entries if k == 'remote.origin.url']
    pushes = [v for k, v in entries if k == 'remote.origin.pushurl']
    return pushes if push and pushes else urls


def secret_check(path, files):
    """Conservative known-pattern check, not a comprehensive security scanner."""
    pattern = re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|'
                         rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')
    for rel in files:
        p = Path(path) / rel
        if p.name == '.env' or p.name.startswith('.env.') or p.suffix.lower() == '.pem' or p.name.startswith('id_'):
            raise Failure('检测到可能的凭据文件，拒绝发布')
        if p.is_file() and not p.is_symlink() and pattern.search(p.read_bytes()):
            raise Failure('检测到已知 token/私钥模式，拒绝发布')


def git_preflight(c, expected=None):
    github_private(c)
    root = git(c, 'rev-parse', '--show-toplevel').strip()
    if Path(root).resolve() != Path(c['local_path']).resolve():
        raise Failure('Git 根目录必须等于 local_path')
    # Check both fetch and every push URL, preventing a hidden alternate push target.
    for mode in ([], ['--push']):
        urls = origin_urls(c, bool(mode))
        if not urls:
            raise Failure('缺少 origin')
        for url in urls:
            github_url(url, c['github_repo'])
    if git(c, 'status', '--porcelain', '--untracked-files=all').strip():
        raise Failure('Git 工作区必须干净（包括未跟踪文件）')
    tracked = set(git(c, 'ls-files', '-z').split('\0')) - {''}
    secret_check(c['local_path'], tracked)
    for p in Path(c['local_path']).rglob('*'):
        rel = p.relative_to(c['local_path'])
        if any(x in c['excludes'] for x in rel.parts):
            continue
        if p.is_file() and str(rel) not in tracked:
            raise Failure('将上传的忽略/未跟踪文件必须先纳入 Git')
    sha = git(c, 'rev-parse', '--verify', 'HEAD^{commit}').strip()
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha):
        raise Failure('HEAD 不是有效 commit SHA')
    branch = git(c, 'symbolic-ref', '--quiet', '--short', 'HEAD').strip()
    remote = git(c, 'ls-remote', 'origin', 'refs/heads/' + branch).split()
    if remote != [sha, 'refs/heads/' + branch]:
        raise Failure('当前 branch commit 尚未 push 至 origin')
    metadata = dict(github_repo=c['github_repo'], git_commit=sha, git_branch=branch)
    if expected and any(expected.get(k) != v for k, v in metadata.items()):
        raise Failure('Git commit/branch 与 checkpoint 不符；使用新的 checkpoint')
    return metadata


def publish_tag(c, cp, state):
    if cp['action'] != 'deploy':
        return
    tag = 'deploy/' + c['host'] + '/' + cp['id']
    cp['github_tag'] = tag
    cp['github_tag_status'] = 'pending'
    save(state / 'checkpoint.json', cp)
    try:
        github_private(c)
        # Resume uses the recorded commit, never the current HEAD or branch.
        if cp['github_repo'] != c['github_repo']:
            raise Failure('checkpoint GitHub 仓库不符')
        for mode in ([], ['--push']):
            urls = origin_urls(c, bool(mode))
            if not urls:
                raise Failure('缺少 origin')
            for url in urls:
                github_url(url, cp['github_repo'])
        sha = cp['git_commit']
        if git(c, 'rev-parse', '--verify', sha + '^{commit}').strip() != sha:
            raise Failure('checkpoint commit 不存在')
        ref = 'refs/tags/' + tag
        def remote_commit():
            rows = [line.split() for line in git(c, 'ls-remote', 'origin', ref, ref + '^{}').splitlines()]
            values = {r: s for s, r in rows}
            return values.get(ref + '^{}', values.get(ref))
        existing = remote_commit()
        if existing and existing != sha:
            raise Failure('远端 tag 冲突；禁止 force 覆盖')
        if not existing:
            local = git(c, 'show-ref', '--tags').splitlines() if git(c, 'tag', '--list') else []
            if any(line.split()[1] == ref for line in local):
                if git(c, 'rev-parse', ref + '^{commit}').strip() != sha:
                    raise Failure('本地 tag 冲突；禁止 force 覆盖')
            else:
                git(c, 'tag', tag, sha)
            git(c, 'push', 'origin', ref + ':' + ref)
        if remote_commit() != sha:
            raise Failure('远端 tag readback 与发布 commit 不符')
        cp['github_tag_status'] = 'success'
        cp.pop('github_tag_error', None)
        save(state / 'checkpoint.json', cp)
    except (Failure, OSError, subprocess.TimeoutExpired, ValueError) as e:
        # Never reverse a successful online deployment because of GitHub bookkeeping.
        cp['github_tag_error'] = 'GitHub tag 发布或 readback 失败；检查认证、连接与 tag 冲突'
        save(state / 'checkpoint.json', cp)
        raise Failure('线上发布已成功，但 GitHub tag 失败；--resume 仅重试 tag，不回滚') from None


def tree_hash(path, excludes=EXCLUDES):
    """拒绝符号链接/特殊文件，指纹含文件名、权限、内容；排除共享及缓存。"""
    h = hashlib.sha256()
    for p in sorted(Path(path).rglob('*')):
        rel = p.relative_to(path)
        if any(x in excludes for x in rel.parts):
            continue
        if p.is_symlink() or (not p.is_file() and not p.is_dir()):
            raise Failure(f'发布源禁止符号链接/特殊文件: {rel}')
        h.update(str(rel).encode() + b'\0' + str(p.stat().st_mode & 0o777).encode() + b'\0')
        if p.is_file():
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)

@contextlib.contextmanager
def local_lock(path):
    with path.open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Failure('本地并发锁已被占用')
        yield

def ssh(c, script):
    return run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', c['host'], 'bash -s'], input=script, timeout=45)

def prelude(c):
    return f'''set -Eeuo pipefail
umask 077
base={shlex.quote(c['remote_path'])}
# 所有受管目录必须为真实目录，不允许通过 symlink 改写其他树。
test -d "$base" && test ! -L "$base"
test "$(realpath "$base")" = "$base"
for d in releases shared backups .transactions; do
  test ! -L "$base/$d"
  mkdir -p "$base/$d"
done
for d in uploads logs; do
  test -d "$base/shared/$d" && test ! -L "$base/shared/$d"
done
test -f "$base/shared/.env" && test ! -L "$base/shared/.env"
test -L "$base/current" || {{ echo '拒绝：current 不存在或为真实 docroot，需独立审批迁移' >&2; exit 20; }}
old=$(readlink "$base/current")
[[ "$old" =~ ^releases/[A-Za-z0-9_-]+$ ]] || exit 21
test -d "$base/$old" && test ! -L "$base/$old"
'''

def reserve(c, ident, expected=None, expected_baseline=None):
    s = prelude(c) + f'''id={shlex.quote(ident)}
exec 9>"$base/.transaction.lock"
flock -n 9 || {{ echo '远端事务并发锁' >&2; exit 22; }}
old=$(readlink "$base/current")
[[ "$old" =~ ^releases/[A-Za-z0-9_-]+$ ]] || exit 21
'''
    if expected is not None:
        s += f'test "$old" = {shlex.quote(expected)} || {{ echo "current 与 checkpoint 不符" >&2; exit 24; }}\n'
    s += '''baseline=$(cd "$base/$old"; find . -type f -print0 | sort -z | xargs -0 -r sha256sum | sha256sum | cut -d ' ' -f1)
'''
    if expected_baseline is not None:
        s += f'test "$baseline" = {shlex.quote(expected_baseline)} || {{ echo "current 指纹冲突" >&2; exit 24; }}\n'
    s += '''marker="$base/.transactions/$id.backup-complete"
if test -f "$marker"; then test "$(cat "$marker")" = "$old|$baseline"; fi
if mkdir "$base/.upload-lock" 2>/dev/null; then
  printf '%s' "$id" >"$base/.upload-lock/owner"
else
  test "$(cat "$base/.upload-lock/owner")" = "$id" || { echo '远端上传并发锁' >&2; exit 23; }
fi
backup="$base/backups/$id"
if test ! -f "$marker"; then
  test ! -L "$backup" && test ! -L "$backup.partial"
  rm -rf -- "$backup.partial"
  # cp -a preserves shared symlinks, never traverses their data.
  cp -a --no-preserve=ownership "$base/$old" "$backup.partial"
  test ! -e "$backup" || rm -rf -- "$backup"
  mv -T "$backup.partial" "$backup"
  printf '%s|%s\\n' "$old" "$baseline" >"$marker.tmp"
  mv -f "$marker.tmp" "$marker"
fi
printf '%s|%s\\n' "$old" "$baseline"
'''
    return ssh(c, s).strip()

def release_lock(c, ident):
    ssh(c, f'''set -eu
base={shlex.quote(c['remote_path'])}
exec 9>"$base/.transaction.lock"; flock -n 9
if test -f "$base/.upload-lock/owner" && test "$(cat "$base/.upload-lock/owner")" = {shlex.quote(ident)}; then rm -f "$base/.upload-lock/owner"; rmdir "$base/.upload-lock"; fi
''')

def transaction(c, cp, mode):
    """生成 nohup 独立事务；result 是持久终态，phase 用于断线诊断。"""
    q = shlex.quote
    ident, target = cp['id'], cp['target']
    s = prelude(c) + f'''id={q(ident)}
target={q(target)}
tx="$base/.transactions/$id"
exec 9>"$base/.transaction.lock"
flock -n 9 || exit 22
test ! -f "$tx.result" || exit 0
test "$(cat "$base/.upload-lock/owner")" = "$id"
test "$old" = {q(cp['old'])}
baseline=$(cd "$base/$old"; find . -type f -print0 | sort -z | xargs -0 -r sha256sum | sha256sum | cut -d ' ' -f1)
test "$baseline" = {q(cp['baseline'])} || {{ echo 'current 指纹冲突' >&2; exit 24; }}
result() {{ printf '%s\\n' "$1" >"$tx.result.tmp"; mv -f "$tx.result.tmp" "$tx.result"; }}
phase() {{ printf '%s\\n' "$1" >"$tx.phase"; }}
health() {{
  for ((i=0; i<{c['health_attempts']}; i++)); do
    code=$(curl --silent --show-error --max-time 10 --output "$tx.body" --write-out '%{{http_code}}' {q(c['health_url'])}) || code=000
    if [[ "$code" =~ ^2[0-9][0-9]$ ]] && grep -Fq -- {q(c['health_keyword'])} "$tx.body"; then return 0; fi
    sleep {c['health_interval']}
  done
  return 1
}}
restart() {{ timeout {c['command_timeout']} {c['restart_command']}; }}
switch_to() {{ ln -s "$1" "$base/.current-$id"; mv -Tf "$base/.current-$id" "$base/current"; }}
switched=0
finish() {{ rm -f "$base/.upload-lock/owner"; rmdir "$base/.upload-lock"; }}
restore() {{
  trap - ERR HUP INT TERM
  if test "$(readlink "$base/current")" = "$old"; then result failed_before_switch; finish; exit 1; fi
  phase restoring
  rm -f "$base/.current-$id"
  if switch_to "$old" && restart && health; then result rolled_back; else result rollback_failed; fi
  echo '告警：发布失败，已尝试回滚；查看持久 result/log' >&2
  finish
  exit 1
}}
# ERR 捕获未预期失败，HUP/TERM 也恢复。nohup 防 SSH 断线 HUP。
trap restore ERR INT TERM
phase verifying
'''
    if mode == 'deploy':
        s += '''test -d "$base/$target" && test ! -L "$base/$target"
(cd "$base/$target"; sha256sum -c .remote-dev-manifest)
rm "$base/$target/.remote-dev-manifest"
for p in uploads logs .env; do
  test ! -e "$base/$target/$p" && test ! -L "$base/$target/$p"
  ln -s "../../shared/$p" "$base/$target/$p"
done
'''
    else:
        s += '''test -d "$base/$target" && test ! -L "$base/$target"
for p in uploads logs .env; do test "$(readlink "$base/$target/$p")" = "../../shared/$p"; done
'''
    s += '''test -f "$tx.backup-complete"
phase switching
switched=1
switch_to "$target"
phase restarting
restart
phase health
health
# 只清理备份；永不删除 release，避免删除 current 或并发读取中的版本。
phase retention
mapfile -t backups < <(printf '%s\\n' "$base"/backups/* | sort -r)
for ((i=5; i<${#backups[@]}; i++)); do test -d "${backups[$i]}" && rm -rf -- "${backups[$i]}"; done
phase complete
result success
trap - ERR INT TERM
finish
'''
    return s

def read_remote(c, ident):
    return ssh(c, f'''set -eu
p={shlex.quote(c['remote_path'] + '/.transactions/' + ident)}
if test -f "$p.result"; then cat "$p.result"; elif test -f "$p.phase"; then printf 'running:'; cat "$p.phase"; else printf 'pending\\n'; fi
''').strip()

def upload(c, cp, state):
    snap = state / 'snapshot'
    if tree_hash(snap, c['excludes']) != cp['snapshot_hash'] or tree_hash(c['local_path'], c['excludes']) != cp['source_hash']:
        raise Failure('源码或已验证快照发生变化：拒绝上线，使用新的 checkpoint')
    if reserve(c, cp['id'], cp['old'], cp['baseline']) != cp['old'] + '|' + cp['baseline']:
        raise Failure('远端 current 内容已改变，拒绝冲突')
    # mkdir 是持久上传阶段：中断后同一 checkpoint 可再次 rsync。
    ssh(c, f'mkdir -p {shlex.quote(c["remote_path"] + "/" + cp["target"])}\n')
    manifest = []
    for p in sorted(snap.rglob('*')):
        if p.is_file() and not any(x in c['excludes'] for x in p.relative_to(snap).parts) and p.name != '.remote-dev-manifest':
            rel = str(p.relative_to(snap))
            if '\n' in rel or '\\' in rel:
                raise Failure('文件名禁止换行和反斜线')
            manifest.append(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + rel)
    (snap / '.remote-dev-manifest').write_text('\n'.join(manifest) + '\n')
    argv = ['rsync', '-a', '--checksum', '--delete', '--safe-links', '-e', 'ssh -o BatchMode=yes -o ConnectTimeout=10']
    for x in sorted(c['excludes']):
        argv += ['--exclude=' + x]
    # copy-dest 实体复制未改文件，禁止 link-dest；后续 rsync 不会修改旧 release。
    argv += ['--copy-dest=' + c['remote_path'] + '/' + cp['old'], str(snap) + '/', c['host'] + ':' + c['remote_path'] + '/' + cp['target'] + '/']
    try:
        run(argv, timeout=c['transaction_timeout'])
    finally:
        (snap / '.remote-dev-manifest').unlink(missing_ok=True)
    cp['stage'] = 'uploaded'
    save(state / 'checkpoint.json', cp)

def launch(c, cp, state, mode):
    script = transaction(c, cp, mode)
    p = c['remote_path'] + '/.transactions/' + cp['id']
    # 事务脚本通过 stdin 送入；启动器独立执行，SSH 中断可重发，flock/result 保证幂等。
    cp['stage'] = 'launched'
    save(state / 'checkpoint.json', cp)
    ssh(c, f'''set -eu
p={shlex.quote(p)}
cat >"$p.sh.tmp" <<'REMOTE_DEV_SCRIPT_END'
{script}
REMOTE_DEV_SCRIPT_END
mv -f "$p.sh.tmp" "$p.sh"
nohup bash "$p.sh" >>"$p.log" 2>&1 </dev/null &
''')
    cp['stage'] = 'launched'
    save(state / 'checkpoint.json', cp)

def wait_result(c, cp, state):
    end = time.monotonic() + c['transaction_timeout']
    while time.monotonic() < end:
        result = read_remote(c, cp['id'])
        if result in {'success', 'rolled_back', 'rollback_failed', 'failed_before_switch'}:
            cp['stage'] = result
            save(state / 'checkpoint.json', cp)
            if result != 'success':
                raise Failure(f'告警：远端事务 {result}；日志 {c["remote_path"]}/.transactions/{cp["id"]}.log')
            current = ssh(c, 'readlink ' + shlex.quote(c['remote_path'] + '/current') + '\n').strip()
            if current != cp['target']:
                raise Failure('事务成功后 current 被其他操作改变，拒绝声明成功')
            publish_tag(c, cp, state)
            print('发布事务成功，已完成重启和 HTTP/关键词验证')
            return
        time.sleep(0.2)
    raise Failure('等待超时；远端仍可独立完成，用 --status/--resume 查询，不能直接重发新部署')

def prepare(c, state, cp):
    git_preflight(c, cp)
    source_hash = tree_hash(c['local_path'], c['excludes'])
    snap = state / 'snapshot'
    shutil.copytree(c['local_path'], snap, ignore=shutil.ignore_patterns(*c['excludes']))
    for k in ('build_command', 'test_command'):
        before = tree_hash(snap, c['excludes']) if k == 'test_command' else None
        out = run(['bash', '-euo', 'pipefail', '-c', c[k]], cwd=snap, timeout=c['transaction_timeout'])
        with (state / 'local.log').open('a') as f:
            f.write(k + '\n' + out)
        if before is not None and before != tree_hash(snap, c['excludes']):
            raise Failure('测试修改了发布快照，拒绝未验证文件上线')
    if tree_hash(c['local_path'], c['excludes']) != source_hash:
        raise Failure('本地构建测试期间源目录发生变化')
    git_preflight(c, cp)
    secret_check(snap, [str(p.relative_to(snap)) for p in snap.rglob('*') if p.is_file() and not any(x in c['excludes'] for x in p.relative_to(snap).parts)])
    return source_hash, tree_hash(snap, c['excludes'])

def pull(c, state, digest, args):
    """Pull-only checkpoint; staging is on the destination filesystem for atomic publish."""
    cpfile = state / 'pull-checkpoint.json'
    dest = Path(c['local_path'])
    if args.resume or args.status:
        cp = json.loads(cpfile.read_text())
        if cp['config_hash'] != digest or cp['action'] != 'pull':
            raise Failure('拉取配置或 checkpoint 操作类型不符')
        if args.status:
            print(json.dumps(cp, ensure_ascii=False)); return
        if cp['stage'] == 'success':
            if not dest.is_dir() or tree_hash(dest, c['excludes']) != cp['hash']:
                raise Failure('已完成拉取的本地目录发生变化')
            print('拉取已完成'); return
    else:
        if cpfile.exists() or (state / 'checkpoint.json').exists():
            raise Failure('checkpoint 已存在，必须 --resume 或指定新目录')
        if dest.is_symlink() or (dest.exists() and (not dest.is_dir() or any(dest.iterdir()))):
            raise Failure('local_path 非空或不是安全目录，拒绝覆盖')
        ident = uuid.uuid4().hex
        cp = dict(id=ident, action='pull', config_hash=digest, stage='pulling',
                  stage_path=str(dest.parent / ('.' + dest.name + '.pull-' + ident)))
        save(cpfile, cp)
    stage = dest.parent / ('.' + dest.name + '.pull-' + cp['id'])
    if str(stage) != cp['stage_path'] or stage.is_symlink():
        raise Failure('拉取 stage 不安全')
    if cp['stage'] == 'ready' and not stage.exists() and dest.is_dir():
        if tree_hash(dest, c['excludes']) != cp['hash']:
            raise Failure('原子发布后的本地内容不符')
        cp['stage'] = 'success'; save(cpfile, cp); return
    if dest.is_symlink() or (dest.exists() and (not dest.is_dir() or any(dest.iterdir()))):
        raise Failure('local_path 非空，拒绝覆盖')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if cp['stage'] != 'ready':
        if c.get('git_url'):
            github_private(c)
            # A failed git clone never falls back to rsync. Retry only our owned stage.
            if stage.exists(): shutil.rmtree(stage)
            stage.mkdir()
            run(['git', '-c', 'credential.helper=!gh auth git-credential', 'clone', '--', c['git_url'], str(stage)], timeout=c['transaction_timeout'])
        else:
            stage.mkdir(exist_ok=True)
            argv = ['rsync', '-a', '--checksum', '--safe-links', '--partial',
                    '-e', 'ssh -o BatchMode=yes -o ConnectTimeout=10']
            argv += ['--exclude=' + x for x in c['excludes']]
            argv += [c['host'] + ':' + c['remote_path'] + '/current/', str(stage) + '/']
            run(argv, timeout=c['transaction_timeout'])
        cp['hash'] = tree_hash(stage, c['excludes'])
        cp['stage'] = 'ready'; save(cpfile, cp)
    if dest.exists(): dest.rmdir()  # succeeds only for an empty directory
    if tree_hash(stage, c['excludes']) != cp['hash']:
        raise Failure('拉取 stage 内容发生变化，拒绝发布')
    # RENAME_NOREPLACE closes the concurrent creator race; never overwrite local work.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.renameat2(-100, os.fsencode(stage), -100, os.fsencode(dest), 1):
        raise Failure('原子拉取发布失败: ' + os.strerror(ctypes.get_errno()))
    cp['stage'] = 'success'; save(cpfile, cp)
    print('已拉取到本地；未构建、上传或重启远端')


def main(argv=None):
    a = argparse.ArgumentParser(description='本地优先发布：共享数据不覆盖，失败自动回滚；首次迁移须独立审批')
    a.add_argument('action', choices=['sync', 'deploy', 'rollback'])
    a.add_argument('--config', required=True, help='YAML 配置路径')
    a.add_argument('--checkpoint', required=True, help='独立持久状态目录，必须在 /home/hatch，且在项目之外')
    g = a.add_mutually_exclusive_group()
    g.add_argument('--resume', action='store_true', help='恢复同一 checkpoint；不会重复构建已验证快照')
    g.add_argument('--status', action='store_true', help='只读本地 checkpoint 和远端 result/phase')
    g.add_argument('--check', action='store_true', help='仅本地检查配置、路径和源文件，不建立 SSH')
    a.add_argument('--release', help='rollback 必需：目标 release ID（不会自动删除版本）')
    args = a.parse_args(argv)
    c = load_config(args.config, allow_missing=args.action in {'sync', 'rollback'} or args.check)
    state = Path(safe_path(args.checkpoint, True))
    if state.resolve().is_relative_to(Path(c['local_path']).resolve()) or Path(c['local_path']).resolve().is_relative_to(state.resolve()):
        raise Failure('checkpoint 和项目路径必须互不包含')
    if args.check:
        if args.action == 'deploy':
            git_preflight(c)
        elif args.action == 'sync' and c.get('git_url'):
            github_private(c)
        if Path(c['local_path']).exists():
            tree_hash(c['local_path'], c['excludes'])
        print('配置和本地路径检查通过；未连接远端')
        return
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
    with local_lock(state / 'lock'):
        if args.action == 'sync':
            pull(c, state, digest, args)
            return
        cpfile = state / 'checkpoint.json'
        if args.resume or args.status:
            cp = json.loads(cpfile.read_text())
            if cp['config_hash'] != digest:
                raise Failure('配置已改变，不能恢复旧 checkpoint')
            if args.status:
                print(json.dumps(cp, ensure_ascii=False))
                print(read_remote(c, cp['id']))
                return
            if cp['action'] != args.action:
                raise Failure('checkpoint 操作类型不符')
            if cp['stage'] == 'success' and args.action == 'deploy':
                publish_tag(c, cp, state)
                print('线上批次已成功；GitHub tag 已验证，不重新构建或部署')
                return
            if cp['stage'] in {'success', 'rolled_back', 'rollback_failed', 'failed_before_switch', 'launched'}:
                if cp['stage'] == 'launched' and read_remote(c, cp['id']) == 'pending':
                    launch(c, cp, state, args.action)
                wait_result(c, cp, state)
                return
        else:
            if cpfile.exists() or (state / 'snapshot').exists() or (state / 'pull-checkpoint.json').exists():
                raise Failure('checkpoint 已存在，必须 --resume 或指定新目录')
            cp = {'id': time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '-' + uuid.uuid4().hex[:12],
                  'config_hash': digest, 'action': args.action, 'stage': 'validated'}
            cp['target'] = 'releases/' + cp['id']
            if args.action == 'rollback':
                if not args.release or not re.fullmatch('[A-Za-z0-9_-]+', args.release):
                    raise Failure('rollback 需要安全的 --release ID')
                cp['target'] = 'releases/' + args.release
            else:
                cp.update(git_preflight(c))
                cp['stage'] = 'building'
                save(cpfile, cp)
                cp['source_hash'], cp['snapshot_hash'] = prepare(c, state, cp)
                cp['stage'] = 'validated'
            save(cpfile, cp)
        if cp['stage'] == 'building':
            if (state / 'snapshot').is_symlink():
                raise Failure('snapshot 不允许 symlink')
            shutil.rmtree(state / 'snapshot', ignore_errors=True)
            cp['source_hash'], cp['snapshot_hash'] = prepare(c, state, cp)
            cp['stage'] = 'validated'
            save(cpfile, cp)
        if args.action == 'deploy':
            git_preflight(c, cp)
        if 'old' not in cp:
            cp['old'], cp['baseline'] = reserve(c, cp['id']).split('|')
            save(cpfile, cp)
        if args.action != 'rollback' and cp['stage'] != 'uploaded':
            upload(c, cp, state)

        # uploaded 恢复必须再次验证指纹，不能绕过源目录修改检测。
        if args.action == 'deploy':
            if tree_hash(state / 'snapshot', c['excludes']) != cp['snapshot_hash'] or tree_hash(c['local_path'], c['excludes']) != cp['source_hash']:
                raise Failure('源码或快照改变，拒绝恢复发布')
        if reserve(c, cp['id'], cp['old'], cp['baseline']) != cp['old'] + '|' + cp['baseline']:
            raise Failure('远端 current 指纹冲突')
        launch(c, cp, state, args.action)
        wait_result(c, cp, state)

if __name__ == '__main__':
    try:
        main()
    except (Failure, OSError, subprocess.TimeoutExpired, ValueError, KeyError) as e:
        message = '告警：' + str(e)
        print(message, file=sys.stderr)
        # 每次失败持久写入指定 checkpoint（不泄露凭据，配置已先经过校验）。
        try:
            i = sys.argv.index('--checkpoint')
            p = Path(safe_path(sys.argv[i + 1], True))
            if p.is_dir():
                with (p / 'errors.log').open('a') as f:
                    f.write(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ' ' + message + '\n')
        except Exception:
            pass
        sys.exit(1)
