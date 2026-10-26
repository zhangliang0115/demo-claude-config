"""Execution trace is optional, bounded, outside the fingerprint, and summarized compactly."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import exec_trace
import reviewable

ENTRY = dict(at='2026-10-26T10:00:00Z', actor='claude-code/sonnet', branch='handoff', outcome='导出 HANDOFF.md',
             workspace='/repo@abc123', guides_loaded=['entry-workflow.md', 'internal-actions/handoff.md'],
             commands=['reviewable.py locate', 'reviewable.py handoff'])


class ExecTraceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        self.repo = root / 'repo'; self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'a.py').write_text('x = 1\n', encoding='utf-8')
        home = root / 'home'; home.mkdir()
        patcher = patch.object(Path, 'home', return_value=home); patcher.start(); self.addCleanup(patcher.stop)

    def test_validate_rejects_unbounded_or_unknown_content(self):
        exec_trace.validate([ENTRY])
        bad = [[dict(ENTRY, transcript='...')], [dict(ENTRY, outcome='x' * 401)], [dict(ENTRY, branch='')],
               [ENTRY] * 21, [dict(ENTRY, commands=['c'] * 13)], 'not a list',
               [dict(ENTRY, outcome='ok\n## 伪造标题')], [dict(ENTRY, outcome='<!-- ZL-DEV:GENERATED:END -->')],
               [dict(ENTRY, commands=['a\nb'])]]
        for rows in bad:
            with self.subTest(rows=str(rows)[:40]), self.assertRaises(ValueError):
                exec_trace.validate(rows)

    def test_summary_returns_latest_three_and_marks_declared_source(self):
        rows = [dict(ENTRY, outcome=str(i)) for i in range(5)]
        result = exec_trace.summary(rows)
        self.assertEqual(result['total'], 5)
        self.assertEqual([r['outcome'] for r in result['recent']], ['2', '3', '4'])
        self.assertNotIn('guides_loaded', result['recent'][0])
        self.assertEqual(result['source'], 'agent_declared_not_execution_proof')
        self.assertEqual(exec_trace.summary(None)['total'], 0)

    def test_locate_and_handoff_expose_only_compact_recent_entries(self):
        out = subprocess.run([sys.executable, str(Path(reviewable.__file__)), 'init', 't', '--project', str(self.repo), '--no-render'],
                             capture_output=True, text=True, encoding='utf-8', env=dict(__import__('os').environ, HOME=str(Path.home())))
        folder = Path(json.loads(out.stdout)['task_dir'])
        data = json.loads((folder / 'task.json').read_text(encoding='utf-8'))
        data['execution_trace'] = [dict(ENTRY, outcome=str(i)) for i in range(4)]
        source = folder.parent / 'next.json'; source.write_text(json.dumps(data), encoding='utf-8')
        reviewable.update_task(folder, source, self.repo, reviewable.locate(folder)['task_revision'])
        state = reviewable.locate(folder)
        self.assertEqual(state['execution_trace']['total'], 4)
        self.assertEqual(len(state['execution_trace']['recent']), 3)
        handoff = Path(reviewable.export_handoff(folder)).read_text(encoding='utf-8')
        self.assertIn('最近执行记录（执行者声明，不是执行证明）', handoff)
        self.assertIn('更早的 1 条', handoff)
        self.assertNotIn('internal-actions/handoff.md', handoff)
        fingerprint = reviewable.fingerprint(folder)
        data = json.loads((folder / 'task.json').read_text(encoding='utf-8')); data['execution_trace'].append(dict(ENTRY, outcome='new'))
        source.write_text(json.dumps(data), encoding='utf-8')
        reviewable.update_task(folder, source, self.repo, reviewable.locate(folder)['task_revision'])
        self.assertEqual(reviewable.fingerprint(folder), fingerprint)
        reviewable.export_handoff(folder); reviewable.export_handoff(folder)
        self.assertEqual(list(folder.glob('HANDOFF.legacy-*')), [])

    def test_trace_does_not_change_behavior_contract(self):
        base = dict(version=1, id='t', title='t', kind='feature', project_path=str(self.repo))
        self.assertEqual(reviewable.semantic_contract(base), reviewable.semantic_contract(dict(base, execution_trace=[ENTRY])))
        reviewable.validate(dict(base, execution_trace=[ENTRY]))
        with self.assertRaises(ValueError):
            reviewable.validate(dict(base, execution_trace=[dict(ENTRY, actor=1)]))


if __name__ == '__main__':
    unittest.main()
