"""Local execution metadata is cooperative, not a process lock or source isolation."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reviewable
import workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve();self.home = self.root/'home'
        mocked = patch.object(Path, 'home', return_value=self.home);mocked.start();self.addCleanup(mocked.stop)
        self.repo = self.root/'repo';self.repo.mkdir()
        self.git(self.repo, 'init', '-q')
        (self.repo/'file.txt').write_text('one\n')
        self.git(self.repo, 'add', 'file.txt')
        self.git(self.repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'initial')
        self.a = self.task('a');self.b = self.task('b')

    def git(self, project, *args):
        return subprocess.run(['git','-C',str(project),*args],check=True,capture_output=True,text=True).stdout.strip()

    def task(self, name, project=None, kind='feature'):
        project = project or self.repo
        with patch.object(sys,'argv',['reviewable.py','init',name,'--project',str(project),'--kind',kind,'--no-render']),redirect_stdout(io.StringIO()):
            self.assertEqual(reviewable.main(),0)
        from storage import project_key
        return self.home / '.claude/zl-dev/projects' / project_key(project) / 'tasks' / name

    def revision(self, project=None):
        return workspace.status(project or self.repo)['registry_revision']

    def begin(self, session='A', task=None, mode='write', project=None, resources=None):
        project = project or self.repo
        return workspace.begin('claude-code',session,project,task or self.a,mode,self.revision(project),resources)

    def tree(self):
        return {str(p.relative_to(self.home)):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}

    def test_inspect_and_missing_status_are_pure_reads(self):
        before=self.tree();result=workspace.inspect(self.repo,self.a);status=workspace.status(self.repo)
        self.assertEqual(result['identity_state'],'git');self.assertEqual(status['registry_revision'],'missing')
        self.assertIn('没有登记不代表',status['reason']);self.assertEqual(before,self.tree())
        self.assertFalse(workspace.registry_path().parent.exists())

    def test_git_subdirectory_identifies_same_checkout(self):
        sub=self.repo/'src';sub.mkdir()
        self.assertEqual(workspace.inspect(sub)['checkout_id'],workspace.inspect(self.repo)['checkout_id'])
        self.assertEqual(workspace.inspect(sub)['root_path'],str(self.repo))

    def test_environment_git_overrides_cannot_redirect_identity(self):
        with patch.dict(os.environ,{'GIT_DIR':'/missing','GIT_WORK_TREE':'/elsewhere','GIT_COMMON_DIR':'/missing','GIT_INDEX_FILE':'/missing/index'}):
            self.assertEqual(workspace.inspect(self.repo)['root_path'],str(self.repo))

    def test_worktrees_have_family_but_distinct_checkouts(self):
        other=self.root/'worktree';self.git(self.repo,'worktree','add','-q','--detach',str(other))
        one=workspace.inspect(self.repo);two=workspace.inspect(other)
        self.assertNotEqual(one['checkout_id'],two['checkout_id']);self.assertEqual(one['repository_family'],two['repository_family'])
        self.assertIsNone(two['branch']);self.assertEqual(two['branch_state'],'detached')
        task=self.task('wt',other);self.begin();result=self.begin('B',task,project=other)
        self.assertEqual(result['state'],'active');self.assertTrue(result['warnings'])

    def test_non_git_ancestor_paths_overlap(self):
        plain=self.root/'plain';sub=plain/'sub';sub.mkdir(parents=True)
        ta=self.task('plain',plain);tb=self.task('sub',sub)
        self.begin('A',ta,project=plain)
        self.assertEqual(self.begin('B',tb,project=sub)['state'],'conflict')

    def test_two_write_tasks_same_checkout_conflict_without_change(self):
        self.begin();before=self.tree();r=self.begin('B',self.b)
        self.assertEqual(r['state'],'conflict');self.assertEqual(before,self.tree())

    def test_read_tasks_parallel_and_writer_warning(self):
        self.begin(mode='read');self.assertEqual(self.begin('B',self.b,mode='read')['state'],'active')
        result=self.begin('C',self.b,mode='write');self.assertEqual(result['state'],'active');self.assertTrue(result['warnings'])

    def test_verify_conflicts_with_writer(self):
        self.begin();self.assertEqual(self.begin('B',self.b,mode='verify')['state'],'conflict')

    def test_explicit_shared_resource_conflicts_across_unrelated_repos(self):
        other=self.root/'other';other.mkdir();t=self.task('other',other)
        self.begin(resources=['tcp:127.0.0.1:3000'])
        result=self.begin('B',t,project=other,resources=['tcp:127.0.0.1:3000'])
        self.assertEqual(result['state'],'conflict')

    def test_begin_cas_rejects_old_read(self):
        old=self.revision();self.begin();before=self.tree()
        with self.assertRaises(ValueError):workspace.begin('claude-code','B',self.repo,self.b,'read',old)
        self.assertEqual(before,self.tree())

    def test_same_activity_is_idempotent(self):
        first=self.begin();before=self.tree();second=self.begin()
        self.assertFalse(second['changed']);self.assertEqual(first['activity']['token'],second['activity']['token']);self.assertEqual(before,self.tree())

    def test_analysis_only_read_and_no_business_side_effects(self):
        task=self.task('analysis',kind='analysis');before=self.tree()
        with self.assertRaises(ValueError):self.begin(task=task)
        self.assertEqual(before,self.tree());self.assertEqual(self.begin(task=task,mode='read')['state'],'active')

    def test_task_project_mismatch_and_missing_id_rejected(self):
        other=self.root/'other';other.mkdir()
        with self.assertRaises(ValueError):self.begin(project=other)
        for identity in ('','unknown','${CLAUDE_SESSION_ID}'):
            with self.assertRaises(ValueError):self.begin(session=identity)

    def test_end_removes_only_own_activity_and_keeps_history(self):
        first=self.begin(mode='read');second=self.begin('B',self.b,mode='read')
        ended=workspace.end('claude-code','A',first['activity']['token'],self.revision())
        self.assertEqual(ended['state'],'ended');data=json.loads(workspace.registry_path().read_bytes())
        self.assertEqual([x['token'] for x in data['active']],[second['activity']['token']]);self.assertEqual(len(data['history']),1)

    def test_other_actor_cannot_end_or_use_old_revision(self):
        a=self.begin();token=a['activity']['token'];rev=a['registry_revision'];self.begin('B',self.b,mode='read');before=self.tree()
        with self.assertRaises(ValueError):workspace.end('claude-code','A',token,rev)
        with self.assertRaises(ValueError):workspace.end('claude-code','B',token,self.revision())
        self.assertEqual(before,self.tree())

    def test_missing_token_is_not_success_and_tokens_never_reused(self):
        a=self.begin();token=a['activity']['token'];workspace.end('claude-code','A',token,self.revision())
        self.assertEqual(workspace.end('claude-code','A',token,self.revision())['state'],'not_found')
        self.assertNotEqual(self.begin()['activity']['token'],token)

    def test_abandoned_record_never_auto_expires(self):
        self.begin();path=workspace.registry_path();data=json.loads(path.read_bytes());data['active'][0]['started_at']='1900-01-01T00:00:00+00:00';path.write_text(json.dumps(data))
        self.assertEqual(self.begin('B',self.b)['state'],'conflict')

    def test_invalid_registry_is_unknown_and_not_overwritten(self):
        path=workspace.registry_path();path.parent.mkdir(parents=True);path.write_text('{broken')
        self.assertEqual(workspace.status(self.repo)['state'],'unknown');before=path.read_bytes()
        with self.assertRaises(ValueError):workspace.begin('claude-code','A',self.repo,self.a,'write','missing')
        self.assertEqual(path.read_bytes(),before)

    def test_git_unavailable_unknown_not_non_git_and_no_begin(self):
        with patch.object(workspace,'_git',side_effect=FileNotFoundError('missing git')):
            self.assertEqual(workspace.inspect(self.repo)['identity_state'],'unknown')
            with self.assertRaises(ValueError):self.begin()

    def test_non_git_observation_does_not_claim_family(self):
        plain=self.root/'plain';plain.mkdir();result=workspace.inspect(plain)
        self.assertEqual(result['identity_state'],'non_git');self.assertIsNone(result['repository_family'])


    def test_idempotent_reader_keeps_other_writer_warning(self):
        self.begin(mode='read');self.begin('B',self.b,mode='write')
        repeated=self.begin(mode='read')
        self.assertFalse(repeated['changed']);self.assertTrue(repeated['warnings'])
        self.assertTrue(workspace.status(self.repo)['observation_unstable'])

    def test_idempotent_activity_does_not_rebind_head_snapshot(self):
        first=self.begin();before=first['activity']['checkout']['head']
        (self.repo/'file.txt').write_text('second\n');self.git(self.repo,'add','file.txt')
        self.git(self.repo,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','second')
        repeated=self.begin();self.assertFalse(repeated['changed']);self.assertTrue(repeated['warnings'])
        self.assertEqual(repeated['activity']['checkout']['head'],before)

    def test_unborn_repo_is_explicit(self):
        empty=self.root/'empty';empty.mkdir();self.git(empty,'init','-q')
        result=workspace.inspect(empty)
        self.assertEqual(result['head_state'],'unborn');self.assertIsNone(result['head'])
        self.assertEqual(result['branch_state'],'branch')

    def test_permission_denial_status_unknown_not_empty_stable(self):
        with patch.object(workspace,'_read',side_effect=PermissionError('denied')):
            result=workspace.status(self.repo)
        self.assertEqual(result['state'],'unknown');self.assertIsNone(result['registry_revision'])
        self.assertIsNone(result['observation_unstable'])

    def test_real_processes_same_revision_have_one_winner(self):
        code = """from pathlib import Path
import json,sys
import workspace
workspace.registry_path=lambda:Path(sys.argv[1])
try:
 r=workspace.begin('claude-code',sys.argv[2],Path(sys.argv[3]),Path(sys.argv[4]),'write','missing')
 print(json.dumps({'state':r['state']}))
except ValueError as e:print(json.dumps({'state':'rejected','reason':str(e)}))
"""
        env=dict(os.environ,PYTHONPATH=str(Path(workspace.__file__).parent))
        argv=[sys.executable,'-c',code,str(workspace.registry_path())]
        a=subprocess.Popen(argv+['A',str(self.repo),str(self.a)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        b=subprocess.Popen(argv+['B',str(self.repo),str(self.b)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        results=[]
        for process in (a,b):
            out,err=process.communicate(timeout=20);self.assertEqual(process.returncode,0,err);results.append(json.loads(out))
        self.assertEqual(sum(x['state']=='active' for x in results),1)
        self.assertEqual(len(workspace.status(self.repo)['active']),1)


    def test_task_kind_changed_while_waiting_for_registry_lock_is_rejected(self):
        from contextlib import contextmanager
        original_lock=workspace._lock
        @contextmanager
        def changed_lock():
            path=self.a/'task.json';data=json.loads(path.read_bytes())
            data['kind']='analysis';data['focus_stage']='analysis'
            path.write_text(json.dumps(data))
            with original_lock():yield
        with patch.object(workspace,'_lock',changed_lock):
            with self.assertRaises(ValueError):self.begin()
        self.assertFalse(workspace.registry_path().exists())


    def test_truncated_or_inconsistent_checkout_cannot_hide_writer(self):
        self.begin();path=workspace.registry_path();original=path.read_bytes()
        variants=[{'identity_state':'non_git','root_path':'/tmp/unrelated','checkout_id':'x'}]
        data=json.loads(original);full=data['active'][0]['checkout']
        for key,value in [('checkout_id','0'*64),('repository_family','0'*64),('project_path','/tmp/unrelated'),('root_path','/tmp/unrelated')]:
            changed=dict(full);changed[key]=value;variants.append(changed)
        changed=dict(full);changed['target']=dict(changed['target'],id='another-task');variants.append(changed)
        for checkout in variants:
            with self.subTest(checkout=checkout):
                data=json.loads(original);data['active'][0]['checkout']=checkout;path.write_text(json.dumps(data));before=path.read_bytes()
                self.assertEqual(workspace.status(self.repo)['state'],'unknown')
                with self.assertRaises(ValueError):self.begin('B',self.b)
                self.assertEqual(path.read_bytes(),before)


    def test_historical_paths_are_lexical_snapshots_after_repo_move(self):
        first=self.begin();workspace.end('claude-code','A',first['activity']['token'],self.revision())
        path=workspace.registry_path();before=path.read_bytes()
        moved=self.root/'repo-moved';self.repo.rename(moved);self.repo.symlink_to(moved,target_is_directory=True)
        unrelated=self.root/'unrelated';unrelated.mkdir()
        result=workspace.status(unrelated)
        self.assertEqual(result['state'],'observed');self.assertEqual(result['active'],[])
        self.assertEqual(path.read_bytes(),before)
        history=json.loads(before)['history'][0]
        self.assertEqual(history['checkout']['root_path'],str(self.repo))
        # Current observation resolves the new physical checkout, without rewriting history.
        self.assertEqual(workspace.inspect(self.repo)['root_path'],str(moved))
        self.assertEqual(path.read_bytes(),before)

    def test_active_observation_paths_are_not_rebound_by_later_symlink(self):
        self.begin();path=workspace.registry_path();before=path.read_bytes()
        moved=self.root/'repo-moved';self.repo.rename(moved);self.repo.symlink_to(moved,target_is_directory=True)
        unrelated=self.root/'unrelated';unrelated.mkdir()
        self.assertEqual(workspace.status(unrelated)['state'],'observed')
        self.assertEqual(path.read_bytes(),before)


if __name__ == '__main__':unittest.main()
