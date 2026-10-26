"""CLI report deferral preserves facts and never silently refreshes a snapshot."""
from contextlib import redirect_stderr, redirect_stdout
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
import storage


class OptionalReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / 'project'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'code.py').write_text('value = 1\n', encoding='utf-8')
        mocked_home = patch.object(Path, 'home', return_value=self.root / 'home')
        mocked_home.start()
        self.addCleanup(mocked_home.stop)
        self.folder = storage.resolve_output('one', 'tasks', self.repo)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['reviewable.py', *args]), redirect_stdout(out), redirect_stderr(err):
            code = reviewable.main()
        return code, out.getvalue(), err.getvalue()

    def call(self, *args):
        code, out, err = self.cli(*args, '--project', str(self.repo))
        self.assertEqual(code, 0, err)
        return out

    def tree(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def test_init_without_report_returns_versions_and_missing_state(self):
        result = json.loads(self.call('init', 'one', '--title', '只保存任务', '--no-render'))
        self.assertTrue((self.folder / 'task.json').is_file())
        self.assertFalse((self.folder / 'report.html').exists())
        self.assertEqual(result['task_dir'], str(self.folder))
        self.assertIsNone(result['report'])
        self.assertEqual(result['report_state']['freshness'], 'missing')
        expected = reviewable.locate(self.folder)
        for field in ('task_revision', 'assessment_revision', 'fingerprint'):
            self.assertEqual(result[field], expected[field])

    def test_deferred_continue_does_not_create_missing_report(self):
        self.call('init', 'one', '--no-render')
        before = self.tree()
        result = json.loads(self.call('continue', 'one', '--no-render'))
        self.assertEqual(before, self.tree())
        self.assertIsNone(result['report'])
        self.assertEqual(result['report_state']['freshness'], 'missing')
        self.assertEqual(result['next_action'], reviewable.locate(self.folder)['next_action'])

    def test_deferred_continue_preserves_existing_report_bytes_and_mtime(self):
        self.call('init', 'one')
        before = self.tree()
        result = json.loads(self.call('continue', 'one', '--no-render'))
        self.assertEqual(before, self.tree())
        self.assertEqual(result['report'], str(self.folder / 'report.html'))
        self.assertEqual(result['report_state']['freshness'], 'current')

    def test_changed_facts_leave_old_report_stale_until_explicit_render(self):
        self.call('init', 'one')
        data = reviewable.load(self.folder)
        data['summary'] = '已有新事实，但不需要立即出页面'
        source = self.root / 'next.json'
        source.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        reviewable.update_task(self.folder, source, self.repo, reviewable.locate(self.folder)['task_revision'])
        before = self.tree()
        deferred = json.loads(self.call('continue', 'one', '--no-render'))
        self.assertEqual(before, self.tree())
        self.assertEqual(deferred['report_state']['freshness'], 'stale')
        current = reviewable.locate(self.folder)
        for field in ('task_revision', 'assessment_revision', 'fingerprint'):
            self.assertEqual(deferred[field], current[field])
        self.assertEqual(self.call('render', 'one').strip(), str(self.folder / 'report.html'))
        self.assertEqual(reviewable.locate(self.folder)['report_state']['freshness'], 'current')

    def test_legacy_init_and_continue_still_generate_reports(self):
        self.assertEqual(self.call('init', 'one').strip(), str(self.folder / 'report.html'))
        report = self.folder / 'report.html'
        report.unlink()
        restored = json.loads(self.call('continue', 'one'))
        self.assertTrue(report.is_file())
        self.assertEqual(restored['report'], str(report))
        self.assertEqual(restored['report_state']['freshness'], 'current')

    def test_flag_on_other_commands_is_rejected_before_side_effects(self):
        self.call('init', 'one', '--no-render')
        for command in ('render', 'index', 'handoff', 'update', 'verify', 'status', 'locate', 'fingerprint'):
            with self.subTest(command=command):
                before = self.tree()
                code, out, err = self.cli(command, 'one', '--project', str(self.repo), '--no-render')
                self.assertEqual(code, 1)
                self.assertIn('--no-render 只适用于 init/continue', err)
                self.assertEqual(out, '')
                self.assertEqual(before, self.tree())

    def test_deferred_continue_with_multiple_candidates_does_not_pick_or_render(self):
        self.call('init', 'one', '--no-render')
        self.call('init', 'two', '--no-render')
        before = self.tree()
        result = json.loads(self.call('continue', '--no-render'))
        self.assertEqual(result['action'], 'choose_or_start')
        self.assertEqual(len(result['tasks']), 2)
        self.assertEqual(before, self.tree())


if __name__ == '__main__':
    unittest.main()
