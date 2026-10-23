import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import storage
import reviewable
import feature


class StorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.repo = self.root / 'source' / 'repo'
        self.repo.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'code.txt').write_text('before')
        self.home = self.root / 'home'
        self.home.mkdir()
        env = patch.object(Path, 'home', return_value=self.home)
        env.start()
        self.addCleanup(env.stop)

    def task(self):
        folder = storage.resolve_output('task', 'tasks', self.repo)
        folder.mkdir(parents=True)
        data = dict(version=1, id='task', title='task', kind='feature', project_path=str(self.repo), contract_version='v1')
        (folder / 'task.json').write_text(json.dumps(data))
        return folder, data

    def test_same_name_isolation_and_alias(self):
        other = self.root / 'other' / 'repo'
        self.assertNotEqual(storage.project_key(self.repo), storage.project_key(other))
        self.assertEqual(storage.project_key(self.repo), storage.project_key(self.repo / '..' / 'repo'))
        self.assertEqual(storage.resolve_output('test', 'tasks', self.repo), self.home / '.claude/zl-dev/projects' / storage.project_key(self.repo) / 'tasks/test')

    def test_bare_dot_rejected(self):
        for value in (".", ".."):
            with self.assertRaises(ValueError):
                storage.resolve_output(value, "tasks", self.repo)

    def test_explicit_path_legacy_compatible(self):
        self.assertEqual(storage.resolve_output('./old', 'tasks', self.repo), Path('./old').resolve())
        self.assertEqual(storage.resolve_output(self.root / 'old', 'tasks', self.repo), self.root / 'old')

    def test_external_evidence_tracks_source(self):
        folder, data = self.task()
        old = reviewable.fingerprint(folder)
        self.assertIsNotNone(old)
        data['evidence'] = [dict(id='e', status='passed', revision=old)]
        (folder / 'task.json').write_text(json.dumps(data))
        self.assertEqual(reviewable.fingerprint(folder), old)
        (self.repo / 'code.txt').write_text('after')
        self.assertNotEqual(reviewable.fingerprint(folder), old)
        snap = feature.project_snapshot(dict(path=str(self.repo), task_path=str(folder), contract_version='v1'))
        self.assertEqual(snap['evidence_counts']['stale'], 1)

    def test_binding_mismatch_rejected(self):
        folder, data = self.task()
        data['project_path'] = str(self.root)
        (folder / 'task.json').write_text(json.dumps(data))
        snap = feature.project_snapshot(dict(path=str(self.repo), task_path=str(folder)))
        self.assertTrue(any('不匹配' in issue for issue in snap['issues']))
        self.assertEqual(snap['evidence_counts']['total'], 0)

    def test_missing_bound_source_never_falls_back(self):
        folder, data = self.task()
        subprocess.run(['git', 'init', '-q', str(self.home)], check=True)
        data['project_path'] = str(self.root / 'missing')
        (folder / 'task.json').write_text(json.dumps(data))
        self.assertIsNone(reviewable.fingerprint(folder))

    def test_cli_default_locations(self):
        def cli(module, *args):
            with patch.object(sys, 'argv', [module.__file__, *args]), redirect_stdout(io.StringIO()):
                module.main()
        cli(reviewable, 'init', 'demo', '--project', str(self.repo))
        folder = storage.resolve_output('demo', 'tasks', self.repo)
        self.assertEqual(reviewable.load(folder)['project_path'], str(self.repo))
        cli(feature, 'init', 'demo', '--workspace', str(self.repo), '--title', 'Demo')
        self.assertEqual(feature.load(storage.resolve_output('demo', 'features', self.repo))['workspace_path'], str(self.repo))
        cli(reviewable, 'index', '--project', str(self.repo))
        self.assertTrue((folder.parent / 'index.html').exists())


if __name__ == '__main__':
    unittest.main()
