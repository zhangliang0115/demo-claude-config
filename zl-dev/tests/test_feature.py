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

if __name__ == '__main__':
    unittest.main()
