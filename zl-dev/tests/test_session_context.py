"""Session focus is recoverable metadata, never a task or permission owner."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reviewable
import session_context as contexts


class SessionContextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.home = self.root / 'home'
        mock = patch.object(Path, 'home', return_value=self.home)
        mock.start()
        self.addCleanup(mock.stop)
        self.project = self.root / 'repo'
        self.project.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        self.a = self.task('a')
        self.b = self.task('b')

    def task(self, identity, project=None):
        project = project or self.project
        with patch.object(sys, 'argv', ['reviewable.py', 'init', identity, '--project', str(project), '--no-render']), redirect_stdout(io.StringIO()):
            self.assertEqual(reviewable.main(), 0)
        return contexts.Path.home() / '.claude/zl-dev/projects' / contexts.project_key(project) / 'tasks' / identity

    def resolve(self, session='S-A', project=None, host='claude-code'):
        return contexts.resolve(host, session, project or self.project)

    def bind(self, folder, session='S-A', project=None, kind='task', expected=None, host='claude-code'):
        project = project or self.project
        if expected is None:
            expected = self.resolve(session, project, host)['context_revision']
        return contexts.bind(host, session, project, kind, folder, expected)

    def bytes_tree(self, folder):
        return {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in folder.rglob('*') if p.is_file()}

    def test_unbound_resolve_never_guesses_even_with_existing_tasks_or_creates_index(self):
        before = self.bytes_tree(self.root)
        result = self.resolve()
        self.assertEqual(result['state'], 'unbound')
        self.assertEqual(result['action'], 'choose_or_start')
        self.assertIsNone(result['target'])
        self.assertEqual(result['context_revision'], 'missing')
        self.assertFalse((self.home / '.claude/zl-dev/contexts').exists())
        self.assertEqual(before, self.bytes_tree(self.root))
        (self.b / 'task.json').unlink()
        self.assertEqual(self.resolve()['state'], 'unbound')

    def test_two_sessions_continue_their_own_task_and_host_namespace_isolated(self):
        self.bind(self.a)
        self.bind(self.b, 'S-B')
        self.bind(self.b, host='codex')
        self.assertEqual(self.resolve()['target']['id'], 'a')
        self.assertEqual(self.resolve('S-B')['target']['id'], 'b')
        self.assertEqual(self.resolve(host='codex')['target']['id'], 'b')

    def test_same_session_switches_explicitly_and_saves_bounded_history(self):
        first = self.bind(self.a)
        second = self.bind(self.b, expected=first['context_revision'])
        record = json.loads(Path(second['context_path']).read_bytes())
        self.assertEqual(second['target']['id'], 'b')
        self.assertEqual(record['history'][0]['target']['id'], 'a')
        for index in range(15):
            self.bind(self.a if index % 2 else self.b)
        data = json.loads(Path(second['context_path']).read_bytes())
        self.assertEqual(len(data['history']), contexts.HISTORY_LIMIT)

    def test_binding_same_target_is_idempotent_and_does_not_touch_fact_or_report(self):
        before = self.bytes_tree(self.a)
        first = self.bind(self.a)
        index = Path(first['context_path'])
        raw, mtime = index.read_bytes(), index.stat().st_mtime_ns
        again = self.bind(self.a)
        self.assertFalse(again['changed'])
        self.assertEqual(again['context_revision'], first['context_revision'])
        self.assertEqual((raw, mtime), (index.read_bytes(), index.stat().st_mtime_ns))
        self.assertEqual(before, self.bytes_tree(self.a))
        self.assertFalse((self.a / 'report.html').exists())

    def test_many_sessions_can_reference_same_task_without_altering_it(self):
        before = self.bytes_tree(self.a)
        for session in ('S-A', 'S-B', 'S-review'):
            self.bind(self.a, session)
            self.assertEqual(self.resolve(session)['target']['path'], str(self.a))
        self.assertEqual(before, self.bytes_tree(self.a))

    def test_same_session_different_project_isolated_and_aliases_normalized(self):
        other = self.root / 'second-repo'
        other.mkdir()
        subprocess.run(['git', 'init', '-q', str(other)], check=True)
        c = self.task('c', other)
        self.bind(self.a)
        self.bind(c, project=other)
        self.assertEqual(self.resolve()['target']['id'], 'a')
        self.assertEqual(self.resolve(project=other)['target']['id'], 'c')
        alias = self.root / 'alias'
        alias.symlink_to(self.project, target_is_directory=True)
        self.assertEqual(self.resolve(project=alias)['target']['id'], 'a')
        self.assertEqual(self.resolve()['context_path'], self.resolve(project=alias)['context_path'])

    def test_feature_binding_uses_workspace_identity_not_child_project(self):
        folder = self.root / 'feature-artifact'
        folder.mkdir()
        data = dict(version=1, id='feature-a', title='Overall feature', workspace_path=str(self.root),
                    projects=[], contracts=[], allocations=[], integration=[])
        (folder / 'feature.json').write_text(json.dumps(data), encoding='utf-8')
        result = self.bind(folder, project=self.root, kind='feature')
        self.assertEqual(result['target']['kind'], 'feature')
        self.assertEqual(self.resolve(project=self.root)['target']['id'], 'feature-a')
        with self.assertRaisesRegex(ValueError, '不匹配'):
            self.bind(folder, kind='feature')

    def test_old_revision_cannot_replace_or_clear_new_focus(self):
        first = self.bind(self.a)
        self.bind(self.b)
        before = self.bytes_tree(self.home)
        with self.assertRaisesRegex(ValueError, '版本冲突'):
            self.bind(self.a, expected=first['context_revision'])
        with self.assertRaisesRegex(ValueError, '版本冲突'):
            contexts.clear('claude-code', 'S-A', self.project, first['context_revision'])
        self.assertEqual(before, self.bytes_tree(self.home))
        self.assertEqual(self.resolve()['target']['id'], 'b')

    def test_missing_revision_cannot_overwrite_new_binding(self):
        self.bind(self.a)
        with self.assertRaisesRegex(ValueError, '版本冲突'):
            self.bind(self.b, expected='missing')
        self.assertEqual(self.resolve()['target']['id'], 'a')

    def test_target_replaced_or_deleted_never_falls_back_to_another_task(self):
        self.bind(self.a)
        source = self.a / 'task.json'
        data = json.loads(source.read_bytes())
        data['id'] = 'replacement'
        source.write_text(json.dumps(data), encoding='utf-8')
        result = self.resolve()
        self.assertEqual((result['state'], result['action']), ('invalid_target', 'repair_binding'))
        self.assertIsNone(result['target'])
        source.unlink()
        self.assertEqual(self.resolve()['state'], 'invalid_target')
        self.assertTrue((self.b / 'task.json').exists())

    def test_bound_project_change_is_invalid_and_cannot_be_silently_rebound(self):
        self.bind(self.a)
        source = self.a / 'task.json'
        data = json.loads(source.read_bytes()); data['project_path'] = str(self.root)
        source.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.resolve()['state'], 'invalid_target')
        before = self.bytes_tree(self.home)
        with self.assertRaisesRegex(ValueError, '不匹配'):
            self.bind(self.a)
        self.assertEqual(before, self.bytes_tree(self.home))

    def test_corrupt_index_is_readonly_and_explicit_cas_repair_preserves_bytes(self):
        first = self.bind(self.a)
        path = Path(first['context_path'])
        raw = b'{this is not JSON'
        path.write_bytes(raw)
        before = self.bytes_tree(self.home)
        result = self.resolve()
        self.assertEqual((result['state'], result['action']), ('invalid_index', 'repair_binding'))
        self.assertEqual(result['context_revision'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(before, self.bytes_tree(self.home))
        fixed = self.bind(self.b, expected=result['context_revision'])
        self.assertEqual(fixed['target']['id'], 'b')
        self.assertEqual(path.with_name(path.name + '.invalid-' + result['context_revision']).read_bytes(), raw)

    def test_wrong_record_identity_is_invalid_not_another_sessions_focus(self):
        result = self.bind(self.a)
        path = Path(result['context_path']);data=json.loads(path.read_bytes());data['session_id']='S-B'
        path.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.resolve()['state'], 'invalid_index')
        self.assertEqual(self.resolve('S-B')['state'], 'unbound')

    def test_clear_only_clears_context_and_can_be_rebound(self):
        first = self.bind(self.a)
        before = self.bytes_tree(self.a)
        result = contexts.clear('claude-code', 'S-A', self.project, first['context_revision'])
        self.assertEqual(result['state'], 'unbound')
        self.assertTrue(result['changed'])
        self.assertEqual(before, self.bytes_tree(self.a))
        self.bind(self.b, expected=result['context_revision'])
        self.assertEqual(self.resolve()['target']['id'], 'b')

    def test_clear_missing_is_noop_without_creating_directories(self):
        before = self.bytes_tree(self.root)
        result = contexts.clear('claude-code', 'S-A', self.project, 'missing')
        self.assertFalse(result['changed'])
        self.assertEqual(before, self.bytes_tree(self.root))
        self.assertFalse((self.home / '.claude/zl-dev/contexts').exists())

    def test_invalid_target_and_ambiguous_artifacts_refuse_before_index_write(self):
        before = self.bytes_tree(self.home)
        with self.assertRaisesRegex(ValueError, '不存在'):
            self.bind(self.root / 'absent')
        with self.assertRaisesRegex(ValueError, '绝对'):
            self.bind('relative')
        with self.assertRaisesRegex(ValueError, '不匹配'):
            self.bind(self.a, project=self.root)
        self.assertEqual(before, self.bytes_tree(self.home))
        (self.a / 'feature.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '同时包含'):
            self.bind(self.a)
        self.assertFalse((self.home / '.claude/zl-dev/contexts').exists())

    def test_unreliable_sessions_and_unsafe_namespaces_are_rejected_without_write(self):
        before = self.bytes_tree(self.root)
        for session in ('', 'unknown', 'undefined', '${CLAUDE_SESSION_ID}', '../escape', 'with space', 'a\nb'):
            with self.subTest(session=session), self.assertRaises(ValueError):
                self.resolve(session)
        for host in ('', '../host', '/host', 'a/b'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.resolve(host=host)
        self.assertEqual(before, self.bytes_tree(self.root))

    def test_target_and_context_symlinks_are_rejected(self):
        original = self.a / 'task.json'; moved=self.root/'task-original.json';original.rename(moved);original.symlink_to(moved)
        with self.assertRaisesRegex(ValueError, '普通文件'):
            self.bind(self.a)
        index = contexts.context_path('claude-code', 'S-A', self.project)
        index.parent.mkdir(parents=True)
        index.symlink_to(moved)
        with self.assertRaisesRegex(ValueError, '符号链接'):
            self.resolve()
        with self.assertRaisesRegex(ValueError, '符号链接'):
            contexts.clear('claude-code', 'S-A', self.project, 'missing')

    def test_target_replaced_during_bind_does_not_silently_select_replacement(self):
        first = self.bind(self.a)
        before = self.bytes_tree(self.home)
        original = contexts.inspect_target
        calls = []
        def changed(kind, target, project):
            value = original(kind, target, project)
            calls.append(value)
            if len(calls) == 2:
                value = dict(value, id='replaced-during-bind')
            return value
        with patch.object(contexts, 'inspect_target', side_effect=changed):
            with self.assertRaisesRegex(ValueError, '绑定期间变化'):
                self.bind(self.b, expected=first['context_revision'])
        self.assertEqual(before, self.bytes_tree(self.home))
        self.assertEqual(self.resolve()['target']['id'], 'a')

    def test_cli_bind_resolve_clear_and_invalid_flags(self):
        def cli(*args):
            out,err=io.StringIO(),io.StringIO()
            with patch.object(sys,'argv',['session_context.py',*args,'--host','claude-code','--session','S-A','--project',str(self.project)]),redirect_stdout(out),redirect_stderr(err):
                code=contexts.main()
            return code,out.getvalue(),err.getvalue()
        code,out,err=cli('resolve');self.assertEqual(code,0,err)
        revision=json.loads(out)['context_revision']
        code,out,err=cli('bind','--target-kind','task','--target',str(self.a),'--expect-revision',revision)
        self.assertEqual(code,0,err);revision=json.loads(out)['context_revision']
        code,out,err=cli('resolve','--target',str(self.b))
        self.assertEqual(code,1);self.assertIn('只读',err)
        code,out,err=cli('clear','--expect-revision',revision)
        self.assertEqual(code,0,err);self.assertEqual(json.loads(out)['state'],'unbound')


if __name__ == '__main__':
    unittest.main()
