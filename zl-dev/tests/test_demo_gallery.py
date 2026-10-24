import json
import re
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_demo_gallery

class GalleryTests(unittest.TestCase):
    def test_gallery_links_and_escaping(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            task=root/'example';task.mkdir()
            (task/'task.json').write_text(json.dumps(dict(version=1,id='example',title='</script><img onerror=bad()>',kind='bugfix',demo=dict(category='排障',purpose='找原因',simulation=True,read_order=['现象','复现']))))
            out=build_demo_gallery.build(root).read_text()
            self.assertTrue((task/'report.html').exists())
            self.assertNotIn('</script><img',out)
            self.assertIn('example/report.html',out)
            self.assertNotIn('__DEMO_DATA__',out)
    def test_gallery_uses_derived_review_when_raw_stage_requests_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);task=root/'blocked';task.mkdir()
            data=dict(version=1,id='blocked',title='权限修复',kind='feature',summary='客户导出',focus_stage='acceptance',behaviors=[dict(id='B1',after='仅本人客户')],implementation=[dict(title='模拟记录')],stage_details={'review':{'items':[dict(id='R1',status='pending',severity='P1',finding='权限绕过')]}})
            (task/'task.json').write_text(json.dumps(data))
            out=build_demo_gallery.build(root).read_text()
            payload=re.search(r'<script type="application/json" id="data">(.*?)</script>',out,re.S).group(1)
            entry=json.loads(payload)[0]
            self.assertEqual('review',entry['stage'])
            self.assertEqual('审查中',entry['phase'])
            report=(task/'report.html').read_text()
            embedded=re.search(r'<script id="task-data" type="application/json">(.*?)</script>',report,re.S).group(1)
            self.assertEqual(entry['stage'],json.loads(embedded)['workflow_summary']['focus_stage'])

    def test_guidance_by_type_and_phase(self):
        from workflow import reading_guide
        self.assertNotEqual(reading_guide('feature','requirements'),reading_guide('feature','acceptance'))
        self.assertNotEqual(reading_guide('incident','operations'),reading_guide('bugfix','testing'))

    def test_phase_entry_has_no_all_stages_view(self):
        """Demo navigation defaults to solution; reports are opened separately."""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name, stage, kind in [('design', 'solution', 'feature'), ('build', 'implementation', 'feature'), ('incident', None, 'incident')]:
                folder=root/name; folder.mkdir()
                task=dict(version=1,id=name,title=name,kind=kind)
                if stage:
                    task['focus_stage']=stage
                (folder/'task.json').write_text(json.dumps(task))
            out=build_demo_gallery.build(root).read_text()
            payload=re.search(r'<script type="application/json" id="data">(.*?)</script>',out,re.S).group(1)
            entries=json.loads(payload)
            self.assertEqual({entry['stage'] for entry in entries}, {'solution','implementation','operations'})
            self.assertIn("?'solution':stages[0]?.[0]",out)
            self.assertIn('item.stage===selected',out)
            self.assertNotIn("selected='全部'",out)
            self.assertNotIn('recommendations',out)
            self.assertNotIn('<iframe',out)
            self.assertIn("a.setAttribute('target','_blank')",out)
            self.assertIn('它不是某个真实任务的报告',out)
            for entry in entries:
                self.assertTrue((root/entry['href']).is_file())
