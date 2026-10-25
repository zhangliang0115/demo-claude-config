"""Publication protects current reports against late snapshots and competing writes."""
from contextlib import redirect_stdout
import builtins
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reviewable as api
import feature
import provenance


class ReportPublishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'app.py').write_text('capacity = 1\n')
        self.folder = self.root / 'task'
        self.folder.mkdir()
        self.data = dict(version=1, id='task', title='Capacity', kind='change',
                         project_path=str(self.repo), summary='Current capacity',
                         behaviors=[dict(id='B1', after='Capacity is one')],
                         implementation=[dict(title='Capacity update')], evidence=[])
        self.save_task()
        self.coord = self.root / 'feature'
        feature.init(self.coord, 'Capacity across projects', ['app=' + str(self.repo)], workspace=self.root)
        data = feature.load(self.coord)
        data['projects'][0]['task_path'] = str(self.folder)
        feature.save(self.coord, data)

    def save_task(self):
        (self.folder / 'task.json').write_text(json.dumps(self.data))

    def artifact(self, folder, name):
        p = folder / name
        return p.read_bytes(), p.stat().st_mtime_ns

    def task_update(self, summary):
        state = api.snapshot(self.folder)
        data = api.load(self.folder)
        data['summary'] = summary
        source = self.root / 'replacement.json'
        source.write_text(json.dumps(data))
        api.update_task(self.folder, source, self.repo, state['task_revision'])

    def during_template(self, template, action):
        original = Path.read_text
        fired = []
        def read(path, *args, **kwargs):
            text = original(path, *args, **kwargs)
            if path == template and not fired:
                fired.append(True)
                action()
            return text
        return patch.object(Path, 'read_text', read)

    def test_old_task_snapshot_cannot_replace_new_report(self):
        old = api.snapshot(self.folder)
        self.task_update('New delivery')
        api.render(self.folder)
        current = self.artifact(self.folder, 'report.html')
        facts = (self.folder / 'task.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '报告生成冲突'):
            api.render(self.folder, old)
        self.assertEqual(current, self.artifact(self.folder, 'report.html'))
        self.assertEqual(facts, (self.folder / 'task.json').read_bytes())
        self.assertEqual(api.report_state(self.folder)['freshness'], 'current')

    def test_feature_old_snapshot_cannot_replace_new_report(self):
        old = feature.snapshot(self.coord)
        data = feature.load(self.coord)
        data['design']['goal'] = 'Updated overall goal'
        feature.save(self.coord, data)
        feature.render(self.coord)
        current = self.artifact(self.coord, 'feature.html')
        facts = (self.coord / 'feature.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '报告生成冲突'):
            feature.render(self.coord, old)
        self.assertEqual(current, self.artifact(self.coord, 'feature.html'))
        self.assertEqual(facts, (self.coord / 'feature.json').read_bytes())

    def test_feature_child_change_rejects_old_state_without_parent_json_change(self):
        old = feature.snapshot(self.coord)
        parent_raw = (self.coord / 'feature.json').read_bytes()
        self.task_update('Child handoff details changed')
        feature.render(self.coord)
        current = self.artifact(self.coord, 'feature.html')
        with self.assertRaisesRegex(ValueError, '报告生成冲突'):
            feature.render(self.coord, old)
        self.assertEqual(parent_raw, (self.coord / 'feature.json').read_bytes())
        self.assertEqual(current, self.artifact(self.coord, 'feature.html'))

    def test_feature_child_code_change_rejects_old_assessment(self):
        old = feature.snapshot(self.coord)
        parent_raw = (self.coord / 'feature.json').read_bytes()
        (self.repo / 'app.py').write_text('capacity = 2\n')
        feature.render(self.coord)
        current = self.artifact(self.coord, 'feature.html')
        with self.assertRaisesRegex(ValueError, '报告生成冲突'):
            feature.render(self.coord, old)
        self.assertEqual(parent_raw, (self.coord / 'feature.json').read_bytes())
        self.assertEqual(current, self.artifact(self.coord, 'feature.html'))

    def test_source_update_during_task_preparation_preserves_new_report(self):
        api.render(self.folder)
        newest = []
        def action():
            self.task_update('New facts while old rendering')
            api.render(self.folder)
            newest.append(self.artifact(self.folder, 'report.html'))
        with self.during_template(api.ROOT / 'assets/report.html', action):
            with self.assertRaisesRegex(ValueError, '报告生成冲突'):
                api.render(self.folder)
        self.assertEqual(newest[0], self.artifact(self.folder, 'report.html'))
        self.assertEqual(api.load(self.folder)['summary'], 'New facts while old rendering')

    def test_source_update_during_feature_preparation_preserves_new_report(self):
        feature.render(self.coord)
        newest = []
        def action():
            data = feature.load(self.coord)
            data['design']['goal'] = 'New goal while old rendering'
            feature.save(self.coord, data)
            feature.render(self.coord)
            newest.append(self.artifact(self.coord, 'feature.html'))
        with self.during_template(feature.ROOT / 'assets/feature.html', action):
            with self.assertRaisesRegex(ValueError, '报告生成冲突'):
                feature.render(self.coord)
        self.assertEqual(newest[0], self.artifact(self.coord, 'feature.html'))

    def test_same_version_competing_task_render_reuses_latest_html(self):
        api.render(self.folder)
        newest = []
        def action():
            api.render(self.folder)
            newest.append(self.artifact(self.folder, 'report.html'))
        with self.during_template(api.ROOT / 'assets/report.html', action):
            self.assertEqual(api.render(self.folder), self.folder / 'report.html')
        self.assertEqual(newest[0], self.artifact(self.folder, 'report.html'))

    def test_same_version_competing_feature_render_reuses_latest_html(self):
        feature.render(self.coord)
        newest = []
        def action():
            feature.render(self.coord)
            newest.append(self.artifact(self.coord, 'feature.html'))
        with self.during_template(feature.ROOT / 'assets/feature.html', action):
            self.assertEqual(feature.render(self.coord), self.coord / 'feature.html')
        self.assertEqual(newest[0], self.artifact(self.coord, 'feature.html'))

    def test_same_version_cached_timestamp_cannot_move_report_backwards(self):
        for module, folder, name in ((api, self.folder, 'report.html'), (feature, self.coord, 'feature.html')):
            with self.subTest(name=name):
                cached = module.snapshot(folder)
                cached['generated_at'] = '2000-01-01T00:00:00+00:00'
                module.render(folder)
                current = self.artifact(folder, name)
                module.render(folder, cached)
                self.assertEqual(current, self.artifact(folder, name))

    def test_conflicting_html_write_during_preparation_is_not_overwritten(self):
        for module, folder, name in ((api, self.folder, 'report.html'), (feature, self.coord, 'feature.html')):
            with self.subTest(name=name):
                module.render(folder)
                changed = []
                def action():
                    (folder / name).write_text('Other writer content')
                    changed.append(self.artifact(folder, name))
                with self.during_template(module.ROOT / 'assets' / name, action):
                    with self.assertRaisesRegex(ValueError, '报告生成冲突'):
                        module.render(folder)
                self.assertEqual(changed[0], self.artifact(folder, name))

    def test_final_validator_observes_changes_after_temporary_write(self):
        api.render(self.folder)
        previous = self.artifact(self.folder, 'report.html')
        original = provenance.atomic_write
        observed = []
        def writing(target, raw, before_replace=None):
            def before():
                temps = list(self.folder.glob('.zl-dev-*.tmp'))
                self.assertEqual(len(temps), 1)
                self.assertEqual(temps[0].read_bytes(), raw)
                observed.append(True)
                self.data['summary'] = 'External edit after temporary output'
                self.save_task()
                before_replace()
            return original(target, raw, before_replace=before)
        with patch.object(provenance, 'atomic_write', side_effect=writing):
            with self.assertRaisesRegex(ValueError, '报告生成冲突'):
                api.render(self.folder)
        self.assertTrue(observed)
        self.assertEqual(previous, self.artifact(self.folder, 'report.html'))
        self.assertEqual(list(self.folder.glob('.zl-dev-*.tmp')), [])

    def test_html_change_before_replace_is_preserved(self):
        api.render(self.folder)
        original = provenance.atomic_write
        changed = []
        def writing(target, raw, before_replace=None):
            def before():
                target.write_text('External final write')
                changed.append(self.artifact(self.folder, 'report.html'))
                before_replace()
            return original(target, raw, before_replace=before)
        with patch.object(provenance, 'atomic_write', side_effect=writing):
            with self.assertRaisesRegex(ValueError, '报告生成冲突'):
                api.render(self.folder)
        self.assertEqual(changed[0], self.artifact(self.folder, 'report.html'))
        self.assertEqual(list(self.folder.glob('.zl-dev-*.tmp')), [])

    def test_forged_candidate_or_provenance_never_replaces_report(self):
        for module, folder, name in ((api, self.folder, 'report.html'), (feature, self.coord, 'feature.html')):
            module.render(folder)
            previous = self.artifact(folder, name)
            for field in ('title', 'assessment_revision', 'provenance'):
                with self.subTest(name=name, field=field):
                    candidate = module.snapshot(folder)
                    if field == 'provenance':
                        candidate[field]['assessment_revision'] = '0' * 64
                    else:
                        candidate[field] = 'forged'
                    with self.assertRaises(ValueError):
                        module.render(folder, candidate)
                    self.assertEqual(previous, self.artifact(folder, name))
            candidate = module.snapshot(folder)
            candidate['title'] = 'Changed with recomputed assessment'
            candidate['assessment_revision'] = provenance.assessment_revision(candidate)
            candidate['provenance']['assessment_revision'] = candidate['assessment_revision']
            with self.assertRaisesRegex(ValueError, '报告生成冲突'):
                module.render(folder, candidate)
            self.assertEqual(previous, self.artifact(folder, name))

    def test_atomic_replace_failure_preserves_existing_report_and_cleans_temp(self):
        for module, folder, name in ((api, self.folder, 'report.html'), (feature, self.coord, 'feature.html')):
            with self.subTest(name=name):
                module.render(folder)
                previous = self.artifact(folder, name)
                with patch('os.replace', side_effect=OSError('replace failed')):
                    with self.assertRaisesRegex(OSError, 'replace failed'):
                        module.render(folder)
                self.assertEqual(previous, self.artifact(folder, name))
                self.assertEqual(list(folder.glob('.zl-dev-*.tmp')), [])

    def test_unsupported_lock_platform_rejects_publish_but_reads_still_work(self):
        api.render(self.folder)
        feature.render(self.coord)
        previous_task = self.artifact(self.folder, 'report.html')
        previous_feature = self.artifact(self.coord, 'feature.html')
        original = builtins.__import__
        def importing(name, *args, **kwargs):
            if name == 'fcntl':
                raise ImportError('no fcntl')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=importing):
            with self.assertRaisesRegex(ValueError, '写锁'):
                api.render(self.folder)
            with self.assertRaisesRegex(ValueError, '写锁'):
                feature.render(self.coord)
            self.assertEqual(api.locate(self.folder)['report_state']['freshness'], 'current')
            feature.locate(self.coord)
            with patch.object(sys, 'argv', ['reviewable.py', 'continue', str(self.folder), '--project', str(self.repo), '--no-render']), redirect_stdout(io.StringIO()):
                self.assertEqual(api.main(), 0)
        self.assertEqual(previous_task, self.artifact(self.folder, 'report.html'))
        self.assertEqual(previous_feature, self.artifact(self.coord, 'feature.html'))

    def test_unknown_code_state_can_render_without_claiming_current(self):
        data = api.load(self.folder)
        unknown = self.root / 'not-a-git-repository'
        unknown.mkdir()
        data['project_path'] = str(unknown)
        (self.folder / 'task.json').write_text(json.dumps(data))
        api.render(self.folder)
        self.assertTrue((self.folder / 'report.html').is_file())
        self.assertEqual(api.report_state(self.folder)['freshness'], 'unknown')


if __name__ == '__main__':
    unittest.main()
