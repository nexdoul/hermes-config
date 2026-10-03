#!/usr/bin/env python3
"""持久 fixture + PATH 假工具；绝不连接真实 VPS/服务。"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid
import yaml

HERE = Path(__file__).resolve().parent
ENGINE = HERE / 'remote_dev.py'
ROOT = Path('/home/hatch/workspace/remote-dev-tests')
FAKE = r'''#!/usr/bin/python3
import os,sys,subprocess,pathlib,shutil
p=pathlib.Path
name=p(sys.argv[0]).name
root=p(os.environ['FIXTURE'])
if name=='gh':
 import json
 if (root/'gh-fail').exists(): sys.exit(1)
 print(json.dumps(dict(nameWithOwner='fixture/private',isPrivate=not (root/'public').exists())))
 sys.exit(0)
if name=='ssh':
 if sys.argv[-1] != 'bash -s':
  assert 'krvps' in sys.argv
  start=sys.argv.index('krvps')+1
  sys.exit(subprocess.run(sys.argv[start:]).returncode)
 assert 'krvps' in sys.argv and sys.argv[-1]=='bash -s'
 script=sys.stdin.read()
 if (root/'disconnect').exists() and 'nohup bash' in script:
  (root/'disconnect').unlink()
  subprocess.run(['bash','-s'],input=script,text=True)
  sys.exit(255)
 sys.exit(subprocess.run(['bash','-s'],input=script,text=True).returncode)
if name=='rsync':
 if (root/'interrupt').exists():
  (root/'interrupt').unlink(); sys.exit(12)
 pulling=':' in sys.argv[-2]
 src=p(sys.argv[-2].split(':',1)[-1]); dst=p(sys.argv[-1].split(':',1)[-1])
 if not pulling:
  assert list((root/'remote/backups').iterdir()), 'backup must precede upload'
 excludes={s.split('=',1)[1] for s in sys.argv if s.startswith('--exclude=')}
 assert (pulling or '--copy-dest=' in ' '.join(sys.argv)) and '--link-dest' not in ' '.join(sys.argv)
 for x in dst.iterdir():
  if x.name not in excludes:
   if x.is_dir() and not x.is_symlink(): shutil.rmtree(x)
   else:x.unlink()
 for x in src.iterdir():
  if x.name in excludes: continue
  if x.is_dir(): shutil.copytree(x,dst/x.name)
  else: shutil.copy2(x,dst/x.name)
 sys.exit(0)
if name=='curl':
 out=p(sys.argv[sys.argv.index('--output')+1])
 current=(root/'remote/current').resolve()
 text=(current/'app').read_text()
 out.write_text('WRONG' if text=='bad-keyword' else 'OK')
 print('503' if text=='bad-http' else '200',end='')
 sys.exit(0)
if name=='systemctl':
 text=(root/'remote/current/app').read_text()
 with (root/'restart-log').open('a') as f:f.write(text+'\n')
 sys.exit(1 if text=='bad-restart' else 0)
'''

class Integration(unittest.TestCase):
    def setUp(self):
        ROOT.mkdir(exist_ok=True)
        self.root = ROOT / uuid.uuid4().hex
        self.root.mkdir()
        self.source = self.root / 'source'; self.source.mkdir()
        (self.source / 'app').write_text('good')
        self.remote = self.root / 'remote'; self.remote.mkdir()
        for d in ('releases/seed', 'shared/uploads', 'shared/logs', 'backups', '.transactions'):
            (self.remote / d).mkdir(parents=True, exist_ok=True)
        (self.remote / 'shared/.env').write_text('persistent-no-secret')
        (self.remote / 'shared/uploads/data').write_text('persistent-upload')
        (self.remote / 'releases/seed/app').write_text('seed')
        for x in ('uploads', 'logs', '.env'):
            (self.remote / 'releases/seed' / x).symlink_to('../../shared/' + x)
        (self.remote / 'current').symlink_to('releases/seed')
        self.bin = self.root / 'bin'; self.bin.mkdir()
        for name in ('ssh','rsync','curl','systemctl','gh'):
            f=self.bin/name; f.write_text(FAKE); f.chmod(0o700)
        self.env = dict(os.environ, PATH=str(self.bin)+':'+os.environ['PATH'], FIXTURE=str(self.root))
        self.repo_url='https://github.com/fixture/private.git'
        self.bare=self.root/'bare.git'
        subprocess.run(['git','init','--bare',str(self.bare)],check=True,capture_output=True)
        self.env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='url.'+str(self.bare)+'.insteadOf', GIT_CONFIG_VALUE_0=self.repo_url, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
        self.git('init','-b','main')
        self.git('config','user.name','Fixture'); self.git('config','user.email','fixture@example.org')
        (self.source/'.gitignore').write_text('uploads/\nlogs/\n.env\ndata/\ncache/\nmedia/\n')
        self.git('remote','add','origin',self.repo_url)
        self.commit()
        subprocess.run(['git','--git-dir='+str(self.bare),'symbolic-ref','HEAD','refs/heads/main'],env=self.env,check=True,capture_output=True)
        self.config = dict(github_repo='fixture/private',host='krvps', remote_path=str(self.remote), local_path=str(self.source),
                           build_command='printf built > artifact', test_command='test -f artifact',
                           restart_command='systemctl restart fixture.service',health_url='http://127.0.0.1/health',
                           health_keyword='OK', health_attempts=1,health_interval=1,transaction_timeout=20)
        self.cfg=self.root/'config.yaml'; self.write_config()
    def git(self,*args):
        return subprocess.run(['git',*args],cwd=self.source,env=self.env,check=True,capture_output=True,text=True).stdout
    def commit(self):
        self.git('add','-A'); self.git('commit','--allow-empty','-m','fixture'); self.git('push','origin','main')
    def write_config(self): self.cfg.write_text(yaml.safe_dump(self.config))
    def call(self, action='deploy', state='state', extra=(), ok=True):
        p=subprocess.run(['/usr/bin/python3',str(ENGINE),action,'--config',str(self.cfg),'--checkpoint',str(self.root/state),*extra],env=self.env,text=True,capture_output=True,timeout=35)
        self.assertEqual(p.returncode==0,ok,p.stderr+p.stdout)
        return p
    def current(self): return os.readlink(self.remote/'current')
    def cp(self,state='state'): return json.loads((self.root/state/'checkpoint.json').read_text())
    def test_success_and_shared(self):
        for name in ('uploads','logs'):
            (self.source/name).mkdir(); (self.source/name/'bad').write_text('must-not-upload')
        (self.source/'.env').write_text('must-not-upload')
        self.call()
        target=self.remote/self.current()
        self.assertEqual((target/'app').read_text(),'good')
        self.assertTrue((target/'artifact').exists())
        self.assertEqual((target/'.env').read_text(),'persistent-no-secret')
        self.assertFalse((target/'uploads/bad').exists())
        self.assertFalse((target/'.git').exists())
        self.assertEqual((self.remote/'releases/seed/app').read_text(),'seed')
        self.assertEqual(self.cp()['stage'],'success')
    def test_http_failure_restores(self):
        (self.source/'app').write_text('bad-http'); self.commit(); self.call(ok=False)
        self.assertEqual(self.current(),'releases/seed')
        self.assertEqual(self.cp()['stage'],'rolled_back')
        self.assertTrue((self.root/'state/errors.log').exists())
    def test_restart_failure_restores(self):
        (self.source/'app').write_text('bad-restart'); self.commit(); self.call(ok=False)
        self.assertEqual(self.current(),'releases/seed')
        self.assertEqual((self.root/'restart-log').read_text().splitlines(),['bad-restart','seed'])
    def test_keyword_failure_restores(self):
        (self.source/'app').write_text('bad-keyword'); self.commit(); self.call(ok=False)
        self.assertEqual(self.current(),'releases/seed')
    def test_five_backups_and_rollback(self):
        for i in range(7):
            (self.source/'app').write_text('good-'+str(i)); self.commit(); self.call(state='state-'+str(i))
        self.assertEqual(len(list((self.remote/'backups').iterdir())),5)
        self.call('rollback','rollback',('--release','seed'))
        self.assertEqual(self.current(),'releases/seed')
        self.assertEqual(len(list((self.remote/'backups').iterdir())),5)
        self.assertEqual(len(list((self.remote/'releases').iterdir())),8)
    def test_reject_real_docroot_and_missing_current(self):
        (self.remote/'current').unlink(); (self.remote/'current').mkdir()
        self.call(ok=False)
        (self.remote/'current').rmdir()
        self.call(state='another',ok=False)
    def test_local_test_failure_no_remote(self):
        self.config['test_command']='exit 3'; self.write_config(); self.call(ok=False)
        self.assertEqual(self.current(),'releases/seed')
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_resume_upload_and_source_change(self):
        (self.root/'interrupt').touch(); self.call(ok=False)
        self.call(extra=('--resume',))
        self.assertEqual(self.cp()['stage'],'success')
    def test_sync_rejects_nonempty(self):
        self.call('sync',ok=False)
        self.assertEqual((self.source/'app').read_text(),'good')
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_sync_rsync_pull_resume(self):
        shutil.rmtree(self.source)
        self.call('sync',extra=('--check',))
        self.call('deploy',extra=('--check',),ok=False)
        (self.root/'interrupt').touch(); self.call('sync',ok=False)
        cp=json.loads((self.root/'state/pull-checkpoint.json').read_text())
        stage=Path(cp['stage_path']); self.assertTrue(stage.is_dir())
        self.assertFalse(self.source.exists())
        self.call('sync',extra=('--resume',))
        self.assertEqual((self.source/'app').read_text(),'seed')
        self.assertFalse(stage.exists())
        for x in ('uploads','logs','.env'): self.assertFalse((self.source/x).exists())
        self.assertEqual(self.current(),'releases/seed')
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_sync_real_git_clone(self):
        self.config['git_url']=self.repo_url
        destination=self.root/'clone'; self.config['local_path']=str(destination);self.write_config()
        self.call('sync')
        self.assertEqual((destination/'app').read_text(),'good')
        self.assertTrue((destination/'.git').is_dir())
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_sync_git_failure_no_fallback(self):
        shutil.rmtree(self.source)
        self.config['git_url']=self.repo_url;self.write_config()
        shutil.rmtree(self.bare)
        self.call('sync',ok=False)
        self.assertFalse(self.source.exists())
        self.assertTrue((self.root/'state/pull-checkpoint.json').exists())
    def test_remote_and_local_locks(self):
        (self.root/'interrupt').touch(); self.call(ok=False)
        self.call(state='competitor',ok=False)
        locked=self.root/'locked'; locked.mkdir()
        with (locked/'lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.call(state='locked',ok=False)
        self.call('deploy',extra=('--resume',))
    def test_ssh_disconnect_after_launch(self):
        (self.root/'disconnect').touch(); self.call(ok=False)
        self.call(extra=('--resume',))
        self.assertEqual(self.cp()['stage'],'success')
    def test_check_rejects_bad_config(self):
        self.call(extra=('--check',))
        self.assertFalse((self.remote/'.upload-lock').exists())
        for key,value in [('host','104'),('restart_command','npm install'),('local_backend',True),('remote_path','/etc/x'),('health_url','http://user:pass@x/')]:
            saved=dict(self.config);self.config[key]=value;self.write_config()
            self.call(extra=('--check',),ok=False)
            self.config=saved
        self.write_config()
    def test_custom_excludes(self):
        self.config['excludes']=['data','cache','media']; self.write_config()
        for name in self.config['excludes']:
            (self.source/name).mkdir();(self.source/name/'big').write_text('excluded')
        self.call()
        for name in self.config['excludes']:
            self.assertFalse((self.remote/self.current()/name).exists())
        self.config['excludes']=['../shared'];self.write_config();self.call(state='unsafe',ok=False)
    def test_failed_build_resume(self):
        once=self.root/'build-once'
        self.config['build_command']=f'if test ! -f {once}; then touch {once}; printf partial > artifact; exit 1; fi; printf built > artifact'
        self.write_config();self.call(ok=False)
        self.assertEqual(self.cp()['stage'],'building')
        self.call(extra=('--resume',))
        self.assertEqual((self.remote/self.current()/'artifact').read_text(),'built')
    def test_pre_switch_failure_does_not_restart(self):
        self.call('rollback',extra=('--release','missing'),ok=False)
        self.assertEqual(self.current(),'releases/seed')
        self.assertFalse((self.root/'restart-log').exists())
        self.assertEqual(self.cp()['stage'],'failed_before_switch')
    def test_backup_before_upload_idempotent_and_conflict_no_owner(self):
        (self.root/'interrupt').touch();self.call(ok=False)
        cp=self.cp(); backup=self.remote/'backups'/cp['id']
        self.assertEqual((backup/'app').read_text(),'seed')
        self.assertTrue((backup/'uploads').is_symlink())
        self.assertTrue((self.remote/'.transactions'/ (cp['id']+'.backup-complete')).exists())
        self.call(extra=('--resume',))
        self.assertEqual(len(list((self.remote/'backups').iterdir())),1)
        (self.source/'app').write_text('next'); self.commit()
        (self.root/'interrupt').touch();self.call(state='conflict',ok=False)
        shutil.rmtree(self.remote/'.upload-lock')
        (self.remote/self.current()/'app').write_text('external-edit')
        self.call(state='conflict',extra=('--resume',),ok=False)
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_test_cannot_modify_snapshot(self):
        self.config['test_command']='printf untested > artifact';self.write_config()
        self.call(ok=False)
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_real_rsync_incremental_and_shared(self):
        real = shutil.which('rsync', path=os.environ['PATH'])
        (self.bin/'rsync').unlink()
        self.call()
        self.assertEqual((self.remote/self.current()/'app').read_text(), 'good')
        self.assertEqual((self.remote/self.current()/'.env').read_text(), 'persistent-no-secret')
        self.assertEqual((self.remote/'releases/seed/app').read_text(), 'seed')
        shutil.rmtree(self.source)
        self.call('sync', state='real-pull')
        self.assertEqual((self.source/'app').read_text(), 'good')
        self.assertFalse((self.source/'.env').exists())
    def test_protected_alias_rejected(self):
        alias = self.root/'alias'
        # 仅构造不存在的目标，不读取/创建生产红线目录。
        alias.symlink_to('/home/hatch/ssh-infra/never-read-fixture')
        self.config['local_path'] = str(alias); self.write_config()
        self.call('sync', extra=('--check',), ok=False)

    def test_github_schema_and_public(self):
        for key, value in [('github_repo','bad'), ('git_url','https://user:secret@github.com/fixture/private.git'), ('git_url','https://github.com/other/repo.git')]:
            saved=dict(self.config); self.config[key]=value; self.write_config()
            self.call(extra=('--check',),ok=False); self.config=saved
        self.write_config(); (self.root/'public').touch()
        self.call(ok=False)
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_dirty_untracked_ignored_and_unpushed(self):
        (self.source/'app').write_text('changed'); self.call(state='dirty',ok=False)
        self.git('checkout','--','app')
        (self.source/'new').write_text('new'); self.call(state='untracked',ok=False)
        (self.source/'new').unlink()
        (self.source/'.git/info/exclude').write_text('ignored\n')
        (self.source/'ignored').write_text('ignored'); self.call(state='ignored',ok=False)
        (self.source/'ignored').unlink()
        self.git('commit','--allow-empty','-m','not-pushed'); self.call(state='unpushed',ok=False)
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_detached_and_origin_and_nested_root(self):
        sha=self.git('rev-parse','HEAD').strip(); self.git('checkout','--detach',sha)
        self.call(state='detached',ok=False); self.git('checkout','main')
        self.git('remote','set-url','origin','https://github.com/other/repo.git')
        self.call(state='origin',ok=False); self.git('remote','set-url','origin',self.repo_url)
        (self.source/'sub').mkdir(); self.config['local_path']=str(self.source/'sub');self.write_config()
        self.call(state='nested',ok=False)
    def test_secret_checks(self):
        for i,name in enumerate(('.env','.env.local','server.pem','id_fixture','token-file')):
            f=self.source/name
            f.write_text('ghp_'+'x'*30 if name=='token-file' else 'fixture')
            self.git('add','-f',name);self.git('commit','-m','fixture');self.git('push','origin','main')
            self.call(state='secret-'+str(i),ok=False)
            self.git('rm',name); self.commit()
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_commit_change_during_build_and_before_resume(self):
        self.config['build_command']=f"printf changed > {self.source}/app; printf built > artifact"
        self.write_config(); self.call(ok=False)
        self.assertFalse((self.remote/'.upload-lock').exists())
    def test_tag_success_readback(self):
        self.call(); cp=self.cp()
        self.assertEqual(cp['github_repo'],'fixture/private')
        self.assertEqual(cp['git_commit'],self.git('rev-parse','HEAD').strip())
        self.assertEqual(cp['git_branch'],'main')
        self.assertEqual(cp['github_tag_status'],'success')
        remote=self.git('ls-remote','origin','refs/tags/'+cp['github_tag']).split()[0]
        self.assertEqual(remote,cp['git_commit'])
    def test_tag_failure_retry_original_sha_no_redeploy(self):
        hook=self.bare/'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nwhile read old new ref; do case "$ref" in refs/tags/*) exit 1;; esac; done\n')
        hook.chmod(0o700)
        result=self.call(ok=False);cp=self.cp()
        self.assertIn('线上发布已成功',result.stderr)
        self.assertEqual(cp['stage'],'success');self.assertEqual(cp['github_tag_status'],'pending')
        original=cp['git_commit']; current=self.current(); restarts=(self.root/'restart-log').read_text()
        hook.unlink();(self.source/'app').write_text('later');self.commit()
        self.call(extra=('--resume',))
        self.assertEqual(self.cp()['git_commit'],original)
        self.assertEqual(self.git('ls-remote','origin','refs/tags/'+cp['github_tag']).split()[0],original)
        self.assertEqual(self.current(),current); self.assertEqual((self.root/'restart-log').read_text(),restarts)
    def test_tag_conflict_not_overwritten(self):
        (self.root/'interrupt').touch();self.call(ok=False);cp=self.cp()
        tag='deploy/krvps/'+cp['id']
        self.git('commit','--allow-empty','-m','different')
        wrong=self.git('rev-parse','HEAD').strip();self.git('tag',tag,wrong);self.git('push','origin','refs/tags/'+tag)
        self.git('reset','--hard',cp['git_commit'])
        self.call(extra=('--resume',),ok=False)
        self.assertEqual(self.cp()['stage'],'success')
        self.assertEqual(self.git('ls-remote','origin','refs/tags/'+tag).split()[0],wrong)
    def test_rollback_without_git_or_gh(self):
        shutil.rmtree(self.source);(self.root/'gh-fail').touch()
        self.call('rollback',extra=('--release','seed'))
        self.assertNotIn('github_tag',self.cp())
    def test_pull_public_repository_rejected(self):
        shutil.rmtree(self.source);self.config['git_url']=self.repo_url;self.write_config()
        (self.root/'public').touch();self.call('sync',ok=False)
        self.assertFalse(self.source.exists())

    def test_resume_rejects_new_commit_even_same_source(self):
        (self.root/'interrupt').touch();self.call(ok=False)
        self.git('commit','--allow-empty','-m','new-head');self.git('push','origin','main')
        self.call(extra=('--resume',),ok=False)
        self.assertEqual(self.current(),'releases/seed')
    def test_existing_annotated_tag_readback(self):
        (self.root/'interrupt').touch();self.call(ok=False);cp=self.cp()
        tag='deploy/krvps/'+cp['id']
        self.git('tag','-a',tag,'-m','deployment',cp['git_commit']);self.git('push','origin','refs/tags/'+tag)
        self.call(extra=('--resume',))
        self.assertEqual(self.cp()['github_tag_status'],'success')
        self.assertEqual(self.git('ls-remote','origin','refs/tags/'+tag+'^{}').split()[0],cp['git_commit'])
    def test_tag_readback_failure_persists_success(self):
        import importlib.util
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('engine_fixture',ENGINE)
        engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
        cp=dict(action='deploy',id='readback-fixture',stage='success',github_repo='fixture/private',git_commit='a'*40)
        state=self.root/'tag-unit';state.mkdir()
        def fake_git(c,*args):
            if args[0]=='rev-parse': return cp['git_commit']+'\n'
            if args[0]=='ls-remote': return ''
            if args[0] in {'tag','push'}: return ''
            raise AssertionError(args)
        with patch.object(engine,'github_private'),patch.object(engine,'origin_urls',return_value=[self.repo_url]),patch.object(engine,'git',side_effect=fake_git):
            with self.assertRaisesRegex(engine.Failure,'线上发布已成功'):
                engine.publish_tag(self.config,cp,state)
        recorded=json.loads((state/'checkpoint.json').read_text())
        self.assertEqual(recorded['stage'],'success');self.assertEqual(recorded['github_tag_status'],'pending')
    def test_missing_github_schema(self):
        del self.config['github_repo'];self.write_config()
        self.call(extra=('--check',),ok=False)

if __name__ == '__main__': unittest.main(verbosity=2)
