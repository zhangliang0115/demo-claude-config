"""Presentation versioning must not change business evidence or silently reuse damaged HTML."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import feature
import provenance
import reviewable as api


class RenderReuseTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve(); self.plugin = self.root / 'plugin'
        shutil.copytree(ROOT / 'assets', self.plugin / 'assets')
        self.repo = self.root / 'repo'; self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'app.py').write_text('total = 1\n')
        self.task = self.root / 'task'; self.task.mkdir()
        self.data = dict(version=1, id='task', title='Current work', kind='feature',
                         project_path=str(self.repo), summary='Current result',
                         behaviors=[dict(id='B1', after='Returns one')], evidence=[])
        self.save()
        self.data['evidence'] = [dict(id='E1', status='passed', revision=api.fingerprint(self.task), behavior_ids=['B1'])]
        self.save()
        self.coord = self.root / 'overall'
        feature.init(self.coord, 'Overall', ['api=' + str(self.repo)], self.root)
        overall = feature.load(self.coord); overall['projects'][0]['task_path'] = str(self.task)
        feature.save(self.coord, overall)
        for module in (api, feature):
            scope = patch.object(module, 'ROOT', self.plugin); scope.start(); self.addCleanup(scope.stop)

    def save(self):
        (self.task / 'task.json').write_text(json.dumps(self.data))

    def variants(self):
        return [(api, self.task, 'report.html', 'task-data'),
                (feature, self.coord, 'feature.html', 'feature-data')]

    def artifact(self, path):
        return path.read_bytes(), path.stat().st_mtime_ns

    def stable_artifact(self, module, folder, name):
        module.render(folder)
        path = folder / name
        os.utime(path, ns=(1234567890000000000, 1234567890000000000))
        return path, self.artifact(path)

    def change(self, name):
        path = self.plugin / 'assets' / name
        path.write_bytes(path.read_bytes() + b'\n/* next template */\n')

    def test_same_data_and_template_keep_exact_bytes_mtime_and_display_time(self):
        for module, folder, name, payload_id in self.variants():
            with self.subTest(name=name):
                path, before = self.stable_artifact(module, folder, name)
                stamp = provenance.read_payload(before[0].decode(), payload_id)['generated_at']
                self.assertEqual(module.render(folder), path)
                self.assertEqual(before, self.artifact(path))
                self.assertEqual(stamp, module.report_state(folder)['generated_at'])
                self.assertEqual(module.report_state(folder)['freshness'], 'current')

    def test_task_template_change_does_not_change_facts_or_evidence(self):
        api.render(self.task); before = api.snapshot(self.task)
        task_bytes = (self.task / 'task.json').read_bytes()
        api.export_handoff(self.task); handoff = (self.task / 'HANDOFF.md').read_bytes()
        self.change('views/feature.js')
        state = api.locate(self.task)
        self.assertEqual(state['report_state']['freshness'], 'stale')
        self.assertEqual(state['report_state']['template_freshness'], 'stale')
        after = api.snapshot(self.task)
        for field in ('assessment_revision', 'task_revision', 'current_fingerprint', 'evidence'):
            self.assertEqual(before[field], after[field])
        self.assertEqual(task_bytes, (self.task / 'task.json').read_bytes())
        self.assertEqual(handoff, (self.task / 'HANDOFF.md').read_bytes())
        api.render(self.task); self.assertEqual(api.report_state(self.task)['freshness'], 'current')

    def test_feature_template_change_does_not_change_parent_or_child_assessment(self):
        feature.render(self.coord); before = feature.snapshot(self.coord); child = api.snapshot(self.task)
        parent_bytes = (self.coord / 'feature.json').read_bytes()
        self.change('feature.html')
        self.assertEqual(feature.report_state(self.coord)['freshness'], 'stale')
        after = feature.snapshot(self.coord)
        self.assertEqual(before['assessment_revision'], after['assessment_revision'])
        self.assertEqual(before['assessment'], after['assessment'])
        self.assertEqual(child['assessment_revision'], api.snapshot(self.task)['assessment_revision'])
        self.assertEqual(parent_bytes, (self.coord / 'feature.json').read_bytes())

    def test_shared_theme_invalidates_both_reports_only_as_presentation(self):
        for module, folder, _, _ in self.variants(): module.render(folder)
        self.change('report-theme.css')
        for module, folder, _, _ in self.variants():
            self.assertEqual(module.report_state(folder)['template_freshness'], 'stale')

    def test_task_only_view_and_unrelated_files_do_not_invalidate_feature(self):
        feature.render(self.coord); path = self.coord / 'feature.html'; before = self.artifact(path)
        self.change('views/feature.js'); (self.plugin / 'README.md').write_text('unrelated docs')
        self.assertEqual(feature.report_state(self.coord)['freshness'], 'current')
        feature.render(self.coord); self.assertEqual(before, self.artifact(path))

    def test_legacy_report_missing_template_is_unknown_then_upgraded_once(self):
        for module, folder, name, payload_id in self.variants():
            module.render(folder); path = folder / name
            bundle = provenance.template_bundle(self.plugin, payload_id)
            data = provenance.read_payload(path.read_text(), payload_id)
            data['provenance'].pop('template_revision')
            path.write_bytes(provenance.render_report_bytes(data, bundle))
            self.assertEqual(module.report_state(folder)['freshness'], 'unknown')
            module.render(folder); self.assertEqual(module.report_state(folder)['freshness'], 'current')
            before = self.artifact(path); module.render(folder); self.assertEqual(before, self.artifact(path))

    def test_changed_outer_html_with_unchanged_payload_is_not_current_or_reused(self):
        for module, folder, name, _ in self.variants():
            module.render(folder); path = folder / name
            good = path.read_bytes(); path.write_bytes(good.replace(b'<body', b'<body data-edited="yes"', 1) if b'<body' in good else good + b'<!-- external change -->')
            self.assertEqual(module.report_state(folder)['freshness'], 'stale')
            bad = path.read_bytes(); module.render(folder)
            self.assertNotEqual(bad, path.read_bytes())
            self.assertEqual(module.report_state(folder)['freshness'], 'current')

    def test_renderer_protocol_is_separate_from_business_assessment(self):
        api.render(self.task); before = api.snapshot(self.task)
        with patch.dict(provenance.RENDERER_PROTOCOL, {'task-data': 2}):
            self.assertEqual(api.report_state(self.task)['template_freshness'], 'stale')
            self.assertEqual(before['assessment_revision'], api.snapshot(self.task)['assessment_revision'])
            api.render(self.task); self.assertEqual(api.report_state(self.task)['freshness'], 'current')

    def test_same_assets_installed_at_other_path_have_same_revision(self):
        other = self.root / 'installed'; shutil.copytree(self.plugin, other)
        for payload_id in ('task-data', 'feature-data'):
            self.assertEqual(provenance.template_bundle(self.plugin, payload_id)['revision'],
                             provenance.template_bundle(other, payload_id)['revision'])

    def test_template_change_during_capture_rejects_old_render_and_keeps_new_page(self):
        for module, folder, name, _ in self.variants():
            module.render(folder); template = self.plugin / 'assets' / name
            original = Path.read_bytes; newest = []
            def read(path):
                raw = original(path)
                if path == template and not newest:
                    newest.append(None)
                    path.write_bytes(raw + b'\n<!-- changed while reading -->')
                    module.render(folder)
                    newest[0] = self.artifact(folder / name)
                return raw
            with patch.object(Path, 'read_bytes', read):
                with self.assertRaisesRegex(ValueError, '模板已变化'):
                    module.render(folder)
            self.assertEqual(newest[0], self.artifact(folder / name))

    def test_template_change_before_atomic_replace_rejects_publication(self):
        path, before = self.stable_artifact(api, self.task, 'report.html')
        self.data['summary'] = 'A changed fact'; self.save()
        original = provenance.atomic_write
        def write(target, raw, before_replace=None):
            def check():
                self.change('report-theme.css'); before_replace()
            return original(target, raw, before_replace=check)
        with patch.object(provenance, 'atomic_write', write):
            with self.assertRaisesRegex(ValueError, '模板已变化'): api.render(self.task)
        self.assertEqual(before, self.artifact(path))
        self.assertFalse(list(self.task.glob('.zl-dev-*.tmp')))

    def test_reuse_rechecks_template_after_reading_existing_html(self):
        path, before = self.stable_artifact(api, self.task, 'report.html')
        original = provenance.report_bytes; calls = []
        def read(target):
            raw = original(target); calls.append(True)
            if len(calls) == 2: self.change('report-theme.css')
            return raw
        with patch.object(provenance, 'report_bytes', read):
            with self.assertRaisesRegex(ValueError, '模板已变化'): api.render(self.task)
        self.assertEqual(before, self.artifact(path))

    def test_reuse_rechecks_html_after_canonical_comparison(self):
        path, _ = self.stable_artifact(api, self.task, 'report.html')
        original = provenance.current_report_bytes; calls = []
        def matching(raw, expected, bundle):
            result = original(raw, expected, bundle); calls.append(True)
            if len(calls) == 2: path.write_bytes(b'External late edit')
            return result
        with patch.object(provenance, 'current_report_bytes', matching):
            with self.assertRaisesRegex(ValueError, '复用前报告已变化'): api.render(self.task)
        self.assertEqual(path.read_bytes(), b'External late edit')

    def test_unknown_code_can_render_but_cannot_be_reused_as_current(self):
        unknown = self.root / 'non-git'; unknown.mkdir()
        self.data['project_path'] = str(unknown); self.save()
        path, before = self.stable_artifact(api, self.task, 'report.html')
        self.assertEqual(api.report_state(self.task)['freshness'], 'unknown')
        api.render(self.task); self.assertNotEqual(before, self.artifact(path))
        self.assertEqual(api.report_state(self.task)['template_freshness'], 'current')

    def test_cached_business_snapshot_cannot_choose_a_forged_template_version(self):
        data = api.snapshot(self.task); data['provenance']['template_revision'] = '0' * 64
        api.render(self.task, data)
        actual = provenance.read_payload((self.task / 'report.html').read_text())
        self.assertEqual(actual['provenance']['template_revision'], provenance.template_bundle(self.plugin, 'task-data')['revision'])
        self.assertEqual(api.report_state(self.task)['freshness'], 'current')

    def test_cached_snapshot_template_upgrade_uses_actual_generation_time(self):
        for module, folder, name, payload_id in self.variants():
            cached = module.snapshot(folder)
            cached['generated_at'] = '2000-01-01T00:00:00+00:00'
            before_revision = cached['assessment_revision']
            filename = 'task.json' if module is api else 'feature.json'
            facts = (folder / filename).read_bytes()
            module.render(folder)
            self.change('report-theme.css')
            module.render(folder, cached)
            recorded = provenance.read_payload((folder / name).read_text(), payload_id)
            self.assertNotEqual(recorded['generated_at'], cached['generated_at'])
            self.assertEqual(recorded['assessment_revision'], before_revision)
            self.assertEqual(facts, (folder / filename).read_bytes())
            self.assertEqual(module.report_state(folder)['freshness'], 'current')

    def test_status_only_reads_even_when_template_is_stale_or_unreadable(self):
        api.render(self.task); self.change('report-theme.css')
        before = {str(p): self.artifact(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(api.locate(self.task)['report_state']['freshness'], 'stale')
        self.assertEqual(before, {str(p): self.artifact(p) for p in self.root.rglob('*') if p.is_file()})
        (self.plugin / 'assets/report-theme.css').unlink()
        self.assertEqual(api.report_state(self.task)['freshness'], 'unknown')


if __name__ == '__main__': unittest.main()
