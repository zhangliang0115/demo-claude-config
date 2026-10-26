"""relate compares checkouts read-only and never moves tasks or evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workspace

GIT = ['git', '-c', 'user.name=T', '-c', 'user.email=t@example.invalid']


class RelateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.origin = self.root / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(self.origin)], check=True)
        self.main = self.root / 'main'
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(self.main)], check=True, capture_output=True)
        (self.main / 'a.py').write_text('x = 1\n', encoding='utf-8')
        subprocess.run(GIT + ['-C', str(self.main), 'add', '.'], check=True)
        subprocess.run(GIT + ['-C', str(self.main), 'commit', '-qm', 'init'], check=True)
        subprocess.run(['git', '-C', str(self.main), 'push', '-q', 'origin', 'HEAD'], check=True, capture_output=True)
        self.task = self.root / 'task'; self.task.mkdir()
        self.data = dict(version=1, id='t1', title='t', kind='feature', project_path=str(self.main),
                         evidence=[dict(id='E1', status='passed', revision='abc', behavior_ids=[])])
        (self.task / 'task.json').write_text(json.dumps(self.data), encoding='utf-8')

    def snapshot(self):
        return (self.task / 'task.json').read_bytes()

    def test_worktree_is_same_local_family_and_task_is_untouched(self):
        wt = self.root / 'wt'
        subprocess.run(['git', '-C', str(self.main), 'worktree', 'add', '-q', '--detach', str(wt)], check=True, capture_output=True)
        before = self.snapshot()
        result = workspace.relate(self.task, wt)
        self.assertEqual(result['state'], 'same_local_family')
        self.assertTrue(result['bound_head_known_in_candidate'])
        self.assertEqual(result['evidence_bound_revisions'], 1)
        self.assertIn('不把旧证据改绑', result['notice'])
        self.assertEqual(self.snapshot(), before)

    def test_separate_clone_is_shared_remote_not_same_project_claim(self):
        clone = self.root / 'other-machine'
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(clone)], check=True, capture_output=True)
        result = workspace.relate(self.task, clone)
        self.assertEqual(result['state'], 'shared_remote')
        self.assertEqual(result['shared_remote_urls'], [str(self.origin)])
        self.assertIn('不证明', result['reason'])

    def test_unrelated_repo_and_missing_binding(self):
        other = self.root / 'other'; other.mkdir()
        subprocess.run(['git', 'init', '-q', str(other)], check=True)
        subprocess.run(GIT + ['-C', str(other), 'commit', '--allow-empty', '-qm', 'x'], check=True)
        self.assertEqual(workspace.relate(self.task, other)['state'], 'unrelated_or_unknown')
        self.assertEqual(workspace.relate(self.task, self.main)['state'], 'same_checkout')
        (self.task / 'task.json').write_text(json.dumps(dict(self.data, project_path=None)), encoding='utf-8')
        with self.assertRaises(ValueError):
            workspace.relate(self.task, other)

    def test_subdirectory_is_same_checkout_and_remote_credentials_are_redacted(self):
        sub = self.main / 'pkg'; sub.mkdir()
        self.assertEqual(workspace.relate(self.task, sub)['state'], 'same_checkout')
        self.assertEqual(workspace._redact('https://user:tok@example.com/r.git'), 'https://example.com/r.git')
        self.assertEqual(workspace._redact('git@github.com:o/r.git'), 'git@github.com:o/r.git')
        (self.task / 'task.json').write_text(json.dumps(dict(self.data, evidence=['bad', 3])), encoding='utf-8')
        self.assertEqual(workspace.relate(self.task, self.main)['evidence_bound_revisions'], 0)
        (self.task / 'task.json').write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            workspace.relate(self.task, self.main)

    def test_cli_rejects_write_arguments(self):
        script = Path(workspace.__file__)
        result = subprocess.run([sys.executable, str(script), 'relate', '--task', str(self.task), '--other', str(self.main),
                                 '--mode', 'write'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        for extra in (['--resource', 'db'], ['--project', str(self.main)]):
            bad = subprocess.run([sys.executable, str(script), 'relate', '--task', str(self.task), '--other', str(self.main), *extra],
                                 capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(bad.returncode, 1)
        ok = subprocess.run([sys.executable, str(script), 'relate', '--task', str(self.task), '--other', str(self.main)],
                            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(json.loads(ok.stdout)['state'], 'same_checkout')


if __name__ == '__main__':
    unittest.main()
