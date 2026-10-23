import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import feature


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'package.json').write_text('{}')
        self.folder = self.root / 'coord'
        feature.init(self.folder, '退款', ['app=' + str(self.repo)])

    def test_discovery_no_allocation(self):
        data = feature.inspect(self.folder)
        self.assertEqual(data['phase'], 'discovery')
        self.assertEqual(data['allocations'], [])
        self.assertEqual(data['projects'][0]['responsibility'], '')
        self.assertIn('package.json', str(data['projects'][0]['observations']))

    def test_missing_path(self):
        data = feature.load(self.folder)
        data['projects'][0]['path'] = str(self.root / 'missing')
        feature.save(self.folder, data)
        self.assertEqual(feature.sync(self.folder)['projects'][0]['snapshot']['availability'], 'inaccessible')
        self.assertEqual(feature.assessed(feature.load(self.folder))['projects'][0]['snapshot_freshness'], 'unknown')

    def test_duplicate_and_self(self):
        with self.assertRaises(ValueError):
            feature.init(self.root / 'other', 'x', ['one=' + str(self.repo), 'two=' + str(self.repo)])
        with self.assertRaises(ValueError):
            feature.init(self.root / 'self', 'x', ['one=' + str(self.root / 'self')])

    def test_unknown_project_and_cycle(self):
        data = feature.load(self.folder)
        data['allocations'] = [dict(id='a', project_id='unknown', depends_on=[])]
        with self.assertRaises(ValueError):
            feature.validate(data)
        data['allocations'] = [dict(id='a', project_id='app', depends_on=['b']), dict(id='b', project_id='app', depends_on=['a'])]
        with self.assertRaises(ValueError):
            feature.validate(data)

    def test_contract_and_staleness(self):
        task = self.repo / '.zl-dev/tasks/test'
        task.mkdir(parents=True)
        child = dict(version=1, id='test', title='test', kind='feature', contract_version='v1')
        (task / 'task.json').write_text(json.dumps(child))
        data = feature.load(self.folder)
        data['projects'][0].update(task_path=str(task), contract_version='v2')
        feature.save(self.folder, data)
        snap = feature.sync(self.folder)['projects'][0]['snapshot']
        self.assertFalse(snap['contract_match'])
        data = feature.load(self.folder)
        self.assertEqual(feature.assessed(data)['projects'][0]['snapshot_freshness'], 'current')
        (self.repo / 'package.json').write_text('{"changed":true}')
        self.assertEqual(feature.assessed(data)['projects'][0]['snapshot_freshness'], 'stale')
        child['contract_version'] = 'v2'
        (task / 'task.json').write_text(json.dumps(child))
        self.assertTrue(feature.sync(self.folder)['projects'][0]['snapshot']['contract_match'])

    def test_render_injection(self):
        assets = self.root / 'assets'
        assets.mkdir()
        (assets / 'feature.html').write_text('<title>__FEATURE_TITLE__</title><script type="application/json">__FEATURE_DATA__</script>')
        data = feature.load(self.folder)
        data['title'] = '</script><img src=x onerror=alert(1)>'
        feature.save(self.folder, data)
        with patch.object(feature, 'ROOT', self.root):
            output = feature.render(self.folder).read_text()
        self.assertNotIn('<img', output)
        self.assertEqual(output.count('</script>'), 1)
        self.assertIn('\\u003c/script', output)

    def test_status_does_not_mutate(self):
        before = (self.folder / 'feature.json').read_bytes()
        feature.assessed(feature.load(self.folder))
        self.assertEqual(before, (self.folder / 'feature.json').read_bytes())


    def test_unassigned_project_dirty_changes(self):
        data=feature.sync(self.folder)
        (self.repo / 'package.json').write_text('{"changed":2}')
        self.assertEqual(feature.assessed(data)['projects'][0]['snapshot_freshness'],'stale')

    def test_global_contract_version_mismatch(self):
        data=feature.load(self.folder)
        data['contract_version']='v2'
        data['projects'][0]['contract_version']='v1'
        self.assertTrue(any('整体方案版本' in issue for issue in feature.assessed(data)['assessment']['issues']))

    def test_malformed_child_is_project_issue(self):
        task=self.repo / '.zl-dev/tasks/bad'
        task.mkdir(parents=True)
        (task / 'task.json').write_text('[]')
        data=feature.load(self.folder)
        data['projects'][0]['task_path']=str(task)
        feature.save(self.folder,data)
        self.assertTrue(any('子任务无法核对' in x for x in feature.sync(self.folder)['projects'][0]['snapshot']['issues']))

    def ready_feature(self):
        task = self.repo / '.zl-dev/tasks/notification'
        task.mkdir(parents=True)
        child = dict(version=1, id='notification', title='通知偏好', kind='feature',
                     summary='变更通知设置后刷新仍保持', contract_version='v1',
                     behaviors=[dict(id='B1', after='刷新保留通知偏好')], implementation=[dict(summary='持久化设置')], evidence=[])
        (task / 'task.json').write_text(json.dumps(child))
        revision = feature.reviewable.fingerprint(task)
        self.assertTrue(revision)
        child['evidence'] = [dict(id='old-failure', status='failed', revision='old-code', behavior_ids=['B1']),
                             dict(id='retest', status='passed', revision=revision, behavior_ids=['B1'])]
        (task / 'task.json').write_text(json.dumps(child))
        data = feature.load(self.folder)
        data.update(contract_version='v1', contracts=[dict(id='notification-api', version='v1', status='confirmed')],
                    allocations=[dict(id='persist', project_id='app', contract_version='v1', depends_on=[])])
        data['projects'][0].update(task_path=str(task), contract_version='v1')
        feature.save(self.folder, data)
        return task, child

    def test_retest_current_coverage_keeps_historical_failures_without_blocking(self):
        self.ready_feature()
        synced = feature.sync(self.folder)
        snap = synced['projects'][0]['snapshot']
        self.assertEqual(snap['evidence_counts']['stale'], 1)
        self.assertEqual(snap['evidence_counts']['failed'], 1)
        self.assertEqual(snap['issues'], [])
        self.assertTrue(feature.assessed(synced)['assessment']['ready_for_integration'])

    def test_current_failure_not_hidden_by_current_pass(self):
        task, child = self.ready_feature()
        child['evidence'].append(dict(id='edge-failure', status='failed', revision=child['evidence'][1]['revision'], behavior_ids=['B1']))
        (task / 'task.json').write_text(json.dumps(child))
        data = feature.sync(self.folder)
        self.assertEqual(data['projects'][0]['snapshot']['evidence_counts']['unresolved_current'], 1)
        self.assertFalse(feature.assessed(data)['assessment']['ready_for_integration'])

    def test_current_pass_does_not_cover_untested_behavior(self):
        task, child = self.ready_feature()
        child['behaviors'].append(dict(id='B2', after='其他用户不能修改设置'))
        (task / 'task.json').write_text(json.dumps(child))
        # Record one current result, still leave B2 untested.
        child['evidence'][1]['revision'] = feature.reviewable.fingerprint(task)
        (task / 'task.json').write_text(json.dumps(child))
        data = feature.sync(self.folder)
        self.assertEqual(data['projects'][0]['snapshot']['missing_behaviors'], 1)
        self.assertFalse(feature.assessed(data)['assessment']['ready_for_integration'])

    def test_preflight_read_only_and_contract_dependency_checks(self):
        self.ready_feature()
        before = (self.folder / 'feature.json').read_bytes()
        self.assertTrue(feature.preflight(self.folder)['ready_for_implementation'])
        self.assertEqual(before, (self.folder / 'feature.json').read_bytes())
        data = feature.load(self.folder)
        data['contracts'][0]['status'] = 'proposed'
        data['allocations'].append(dict(id='ui', project_id='app', contract_version='v1', depends_on=['persist']))
        data['allocations'][0]['contract_version'] = 'v0'
        feature.save(self.folder, data)
        result = feature.preflight(self.folder)
        self.assertFalse(result['ready_for_implementation'])
        self.assertTrue(any('尚未全部' in x for x in result['issues']))
        self.assertTrue(any('依赖 persist' in x for x in result['issues']))

    def test_render_binds_phase_goal_and_feedback_without_markup_injection(self):
        data = feature.load(self.folder)
        data.update(phase='implementation', design=dict(goal='保存通知偏好 </script>'))
        feature.save(self.folder, data)
        output = feature.render(self.folder).read_text()
        self.assertIn('const initialStage=phaseStage(f.phase)', output)
        self.assertIn('show(initialStage)', output)
        self.assertIn('navigator.clipboard.writeText(preview.textContent)', output)
        self.assertIn('selection.addRange(range)', output)
        self.assertNotIn('innerHTML', output)
        self.assertIn('保存通知偏好 \u005cu003c/script', output)

    def feature_replacement(self):
        data = feature.load(self.folder)
        source = self.root / 'replacement.json'
        source.write_text(json.dumps(data))
        return data, source

    def test_feature_update_success_and_locate_read_only(self):
        before = (self.folder / 'feature.json').read_bytes()
        location = feature.locate(self.folder)
        self.assertEqual(before, (self.folder / 'feature.json').read_bytes())
        data, source = self.feature_replacement()
        data['design']['goal'] = '通知偏好持久化'
        source.write_text(json.dumps(data))
        result = feature.update_feature(self.folder, source, data['workspace_path'], location['feature_revision'])
        self.assertTrue(result['updated'])
        self.assertNotEqual(result['feature_revision'], location['feature_revision'])
        self.assertEqual(feature.load(self.folder)['design']['goal'], '通知偏好持久化')
        self.assertFalse((self.folder / 'feature.html').exists())

    def test_feature_update_conflict_preserves_latest_bytes(self):
        data, source = self.feature_replacement()
        revision = feature.locate(self.folder)['feature_revision']
        data['phase'] = 'design'
        feature.save(self.folder, data)
        before = (self.folder / 'feature.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '版本冲突'):
            feature.update_feature(self.folder, source, data['workspace_path'], revision)
        self.assertEqual(before, (self.folder / 'feature.json').read_bytes())

    def test_feature_update_rejects_derived_snapshot_changes(self):
        feature.sync(self.folder)
        data, source = self.feature_replacement()
        revision = feature.locate(self.folder)['feature_revision']
        data['projects'][0]['snapshot']['issues'] = []
        source.write_text(json.dumps(data))
        before = (self.folder / 'feature.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '派生快照'):
            feature.update_feature(self.folder, source, data['workspace_path'], revision)
        self.assertEqual(before, (self.folder / 'feature.json').read_bytes())

    def test_feature_update_rejects_binding_replacement(self):
        for field in ('id', 'workspace_path', 'project_path', 'project_set'):
            data, source = self.feature_replacement()
            bound = data['workspace_path']
            if field == 'project_path':
                data['projects'][0]['path'] = str(self.root / 'other-repo')
            elif field == 'project_set':
                data['projects'] = []
            else:
                data[field] = str(self.root) if field == 'workspace_path' else 'other-id'
            source.write_text(json.dumps(data))
            before = (self.folder / 'feature.json').read_bytes()
            with self.assertRaises(ValueError):
                feature.update_feature(self.folder, source, bound, feature.locate(self.folder)['feature_revision'])
            self.assertEqual(before, (self.folder / 'feature.json').read_bytes())

    def test_feature_update_source_failure_does_not_create_or_overwrite(self):
        data, source = self.feature_replacement()
        before = (self.folder / 'feature.json').read_bytes()
        source.unlink()
        with self.assertRaises(OSError):
            feature.update_feature(self.folder, source, data['workspace_path'], feature.locate(self.folder)['feature_revision'])
        self.assertEqual(before, (self.folder / 'feature.json').read_bytes())
        self.assertFalse((self.folder / 'feature.html').exists())

    def test_rebinding_equivalent_task_requires_sync(self):
        (self.repo / '.gitignore').write_text('.zl-dev/\n')
        task, child = self.ready_feature()
        twin = task.parent / 'equivalent'
        twin.mkdir()
        child['id'] = 'equivalent'
        (twin / 'task.json').write_text(json.dumps(child))
        self.assertEqual(feature.reviewable.fingerprint(task), feature.reviewable.fingerprint(twin))
        data = feature.sync(self.folder)
        self.assertTrue(feature.assessed(data)['assessment']['ready_for_integration'])
        revision = feature.locate(self.folder)['feature_revision']
        data['projects'][0]['task_path'] = str(twin)
        source = self.root / 'rebound-feature.json'
        source.write_text(json.dumps(data))
        feature.update_feature(self.folder, source, data['workspace_path'], revision)
        state = feature.assessed(feature.load(self.folder))
        self.assertEqual(state['projects'][0]['snapshot_freshness'], 'stale')
        self.assertFalse(state['assessment']['ready_for_integration'])
        synced = feature.sync(self.folder)
        self.assertEqual(synced['projects'][0]['snapshot']['task_path'], str(twin.resolve()))
        self.assertEqual(synced['projects'][0]['snapshot']['task_id'], 'equivalent')
        self.assertTrue(feature.assessed(synced)['assessment']['ready_for_integration'])

    def test_same_path_with_changed_task_id_requires_sync(self):
        task, child = self.ready_feature()
        data = feature.sync(self.folder)
        child['id'] = 'replacement-task'
        (task / 'task.json').write_text(json.dumps(child))
        self.assertEqual(data['projects'][0]['snapshot']['current_fingerprint'], feature.reviewable.fingerprint(task))
        self.assertEqual(feature.assessed(data)['projects'][0]['snapshot_freshness'], 'stale')

    def test_legacy_snapshot_without_binding_is_stale(self):
        self.ready_feature()
        data = feature.sync(self.folder)
        del data['projects'][0]['snapshot']['task_path']
        self.assertEqual(feature.assessed(data)['projects'][0]['snapshot_freshness'], 'stale')

    def test_read_only_commands_import_without_fcntl(self):
        import builtins
        original_import = builtins.__import__
        def windows_import(name, *args, **kwargs):
            if name == 'fcntl':
                raise ImportError('Windows has no fcntl')
            return original_import(name, *args, **kwargs)
        before = (self.folder / 'feature.json').read_bytes()
        spec = importlib.util.spec_from_file_location('feature_windows_probe', Path(feature.__file__))
        module = importlib.util.module_from_spec(spec)
        with patch('builtins.__import__', side_effect=windows_import):
            spec.loader.exec_module(module)
            module.locate(self.folder)
            module.preflight(self.folder)
            module.assessed(module.load(self.folder))
            with self.assertRaisesRegex(ValueError, '不支持 feature 写锁'):
                module.save(self.folder, module.load(self.folder))
        self.assertEqual(before, (self.folder / 'feature.json').read_bytes())

if __name__ == '__main__':
    unittest.main()
