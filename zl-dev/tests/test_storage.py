import json
import io
from contextlib import redirect_stdout, redirect_stderr
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

    def cli(self, *args):
        out = io.StringIO()
        with patch.object(sys, 'argv', ['reviewable.py', *args]), redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = reviewable.main()
        return code, out.getvalue()

    def tree(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() else None
                for p in self.root.rglob('*')}

    def test_locate_and_status_never_write_or_render(self):
        folder, data = self.task()
        for report_exists in (False, True):
            if report_exists:
                (folder / 'report.html').write_text('existing report')
            for command in ('locate', 'status'):
                before = self.tree()
                code, out = self.cli(command, '--project', str(self.repo))
                self.assertEqual(code, 0)
                self.assertEqual(before, self.tree())
                if command == 'locate':
                    result = json.loads(out)
                    self.assertEqual(result['task_revision'], reviewable.task_revision((folder / 'task.json').read_bytes()))
                    self.assertEqual(result['report'], str(folder / 'report.html') if report_exists else None)

    def test_locate_and_status_missing_tasks_never_create_directories(self):
        for command in ('locate', 'status'):
            before = self.tree()
            code, out = self.cli(command, '--project', str(self.repo))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)['tasks'], [])
            self.assertEqual(before, self.tree())
            code, out = self.cli(command, 'missing', '--project', str(self.repo))
            self.assertEqual(code, 1)
            self.assertEqual(before, self.tree())

    def test_handoff_freshness_checks_task_and_real_git_source_without_writes(self):
        folder, data = self.task()
        subprocess.run(['git', 'add', 'code.txt'], cwd=self.repo, check=True)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'baseline'], cwd=self.repo, check=True)
        def check(expected):
            before = self.tree()
            state = reviewable.locate(folder)
            self.assertEqual(state['handoff']['freshness'], expected)
            self.assertEqual(state['handoff']['path'], None if expected == 'missing' else str(folder / 'HANDOFF.md'))
            code, output = self.cli('status', str(folder), '--project', str(self.repo))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)['handoff'], state['handoff'])
            self.assertEqual(before, self.tree())
        check('missing')
        handoff = reviewable.export_handoff(folder)
        self.assertIn('task_revision: ' + reviewable.locate(folder)['task_revision'], handoff.read_text())
        check('current')
        original = (folder / 'task.json').read_bytes()
        data['summary'] = 'metadata changed without code change'
        (folder / 'task.json').write_text(json.dumps(data))
        check('stale')
        (folder / 'task.json').write_bytes(original)
        check('current')
        (self.repo / 'code.txt').write_text('changed after export')
        check('stale')
        handoff.write_text('# Legacy handoff with human notes\nKeep this text.\n')
        check('unknown')
        self.assertEqual(handoff.read_text(), '# Legacy handoff with human notes\nKeep this text.\n')

    def test_update_validates_and_rejects_lost_updates(self):
        folder, data = self.task()
        revision = reviewable.locate(folder)['task_revision']
        source = self.root / 'replacement.json'
        source.write_text(json.dumps(dict(data, summary='first update')))
        result = reviewable.update_task(folder, source, self.repo, revision)
        self.assertTrue(result['updated'])
        self.assertEqual(reviewable.load(folder)['summary'], 'first update')
        saved = (folder / 'task.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '版本冲突'):
            reviewable.update_task(folder, source, self.repo, revision)
        self.assertEqual(saved, (folder / 'task.json').read_bytes())
        self.assertFalse((folder / 'report.html').exists())

    def test_update_rejects_schema_binding_identity_and_code_conflicts(self):
        folder, data = self.task()
        raw = (folder / 'task.json').read_bytes()
        revision = reviewable.task_revision(raw)
        source = self.root / 'replacement.json'
        for changes in ({'id':'other'}, {'project_path':str(self.root)}, {'kind':'unknown'}):
            source.write_text(json.dumps(dict(data, **changes)))
            with self.assertRaises(ValueError):
                reviewable.update_task(folder, source, self.repo, revision)
            self.assertEqual(raw, (folder / 'task.json').read_bytes())
        source.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, '绑定项目'):
            reviewable.update_task(folder, source, self.root, revision)
        current = reviewable.fingerprint(folder)
        (self.repo / 'code.txt').write_text('concurrent code change')
        with self.assertRaisesRegex(ValueError, '指纹冲突'):
            reviewable.update_task(folder, source, self.repo, revision, current)
        with self.assertRaisesRegex(ValueError, 'expect-revision'):
            reviewable.update_task(folder, source, self.repo, None)
        self.assertEqual(raw, (folder / 'task.json').read_bytes())

    def evidence_task(self, revision='run-one'):
        folder, data = self.task()
        data['evidence'] = [dict(id='E1', status='passed', revision=revision)]
        (folder / 'task.json').write_text(json.dumps(data))
        return folder, data

    def replace_data(self, folder, data):
        source = self.root / 'replacement.json'
        source.write_text(json.dumps(data))
        return reviewable.update_task(folder, source, self.repo, reviewable.locate(folder)['task_revision'])

    def test_evidence_rebinding_or_renaming_rejected_without_touching_task(self):
        folder, data = self.evidence_task()
        target = folder / 'task.json'
        before = (target.read_bytes(), target.stat().st_mtime_ns)
        for evidence in ([dict(id='E1', status='passed', revision='run-two')],
                         [dict(id='E2', status='passed', revision='run-two')], []):
            candidate = dict(data, evidence=evidence)
            with self.assertRaisesRegex(ValueError, '保留旧证据并新增本次重跑证据'):
                self.replace_data(folder, candidate)
            self.assertEqual(before, (target.read_bytes(), target.stat().st_mtime_ns))

    def test_evidence_rerun_preserves_old_and_adds_new(self):
        folder, data = self.evidence_task()
        data['evidence'].append(dict(id='E2', status='passed', revision='run-two'))
        self.replace_data(folder, data)
        self.assertEqual(reviewable.load(folder)['evidence'], data['evidence'])

    def test_evidence_empty_revision_can_bind_and_existing_can_invalidate(self):
        folder, data = self.evidence_task('')
        data['evidence'][0]['revision'] = 'first-real-run'
        self.replace_data(folder, data)
        self.assertEqual(reviewable.load(folder)['evidence'][0]['revision'], 'first-real-run')
        data['evidence'][0]['revision'] = ''
        self.replace_data(folder, data)
        self.assertEqual(reviewable.load(folder)['evidence'][0]['revision'], '')

    def test_evidence_ids_must_be_nonempty_and_unique(self):
        folder, data = self.evidence_task()
        for evidence in ([dict(id='E1', status='passed'), dict(id='E1', status='failed')],
                         [dict(status='passed')], [dict(id='', status='passed')]):
            with self.assertRaisesRegex(ValueError, '证据 id 必须唯一且非空'):
                reviewable.validate(dict(data, evidence=evidence))
        duplicate = dict(data, evidence=[dict(id='E1', status='passed', revision='run-one'),
                                       dict(id='E1', status='passed', revision='run-two')])
        before = (folder / 'task.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '证据 id'):
            self.replace_data(folder, duplicate)
        self.assertEqual(before, (folder / 'task.json').read_bytes())

    def test_update_cli_succeeds_without_rendering(self):
        folder, data = self.task()
        state = reviewable.locate(folder)
        source = self.root / 'replacement.json'
        source.write_text(json.dumps(dict(data, summary='saved through CLI')))
        code, out = self.cli('update', str(folder), '--project', str(self.repo), '--from-file', str(source), '--expect-revision', state['task_revision'], '--expect-fingerprint', state['fingerprint'])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)['updated'])
        self.assertEqual(reviewable.load(folder)['summary'], 'saved through CLI')
        self.assertFalse((folder / 'report.html').exists())

    def test_update_unsupported_lock_platform_never_writes(self):
        folder, data = self.task()
        source = self.root / 'replacement.json'
        source.write_text(json.dumps(dict(data, summary='new')))
        raw = (folder / 'task.json').read_bytes()
        before = self.tree()
        import builtins
        original_import = builtins.__import__
        def missing_lock(name, *args, **kwargs):
            if name == 'fcntl':
                raise ImportError('not available on this platform')
            return original_import(name, *args, **kwargs)
        with patch.object(builtins, '__import__', side_effect=missing_lock):
            with self.assertRaisesRegex(ValueError, '不支持任务写锁；未写入'):
                reviewable.update_task(folder, source, self.repo, reviewable.task_revision(raw))
            code, _ = self.cli('update', str(folder), '--project', str(self.repo), '--from-file', str(source), '--expect-revision', reviewable.task_revision(raw))
        self.assertEqual(code, 1)
        self.assertEqual(before, self.tree())

    def test_update_cli_permission_failure_preserves_original(self):
        folder, data = self.task()
        raw = (folder / 'task.json').read_bytes()
        source = self.root / 'replacement.json'
        source.write_text(json.dumps(dict(data, summary='new')))
        with patch.object(reviewable.os, 'replace', side_effect=PermissionError('denied')):
            code, _ = self.cli('update', str(folder), '--project', str(self.repo), '--from-file', str(source), '--expect-revision', reviewable.task_revision(raw))
        self.assertEqual(code, 1)
        self.assertEqual(raw, (folder / 'task.json').read_bytes())
        self.assertEqual(list(folder.glob('.task-update-*')), [])

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
