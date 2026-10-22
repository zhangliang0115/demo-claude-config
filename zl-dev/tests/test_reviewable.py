import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('reviewable', Path(__file__).resolve().parents[1] / 'scripts/reviewable.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        self.task = self.root/'tasks'/'sample'; self.task.mkdir(parents=True)
        self.data = dict(version=1,id='sample',title='测试',kind='feature',behaviors=[dict(id='B1',after='safe')],scenarios=[],evidence=[])
        self.save()
    def tearDown(self): self.tmp.cleanup()
    def save(self): (self.task/'task.json').write_text(json.dumps(self.data),encoding='utf-8')
    def test_source_and_contract_invalidate(self):
        initial=m.fingerprint(self.task); self.assertIsNotNone(initial)
        (self.root/'source.py').write_text('a=1')
        changed=m.fingerprint(self.task); self.assertNotEqual(initial,changed)
        (self.root/'source.py').write_text('a=2')
        self.assertNotEqual(changed,m.fingerprint(self.task))
        before=m.fingerprint(self.task)
        self.data['behaviors'][0]['after']='changed';self.save()
        self.assertNotEqual(before,m.fingerprint(self.task))
    def test_report_and_evidence_do_not_invalidate(self):
        before=m.fingerprint(self.task)
        self.data['evidence']=[dict(id='E1',behavior_ids=['B1'],status='passed',revision=before)];self.save()
        m.render(self.task)
        self.assertEqual(before,m.fingerprint(self.task))
        self.assertEqual('当前',m.assessed(self.data,before)['evidence'][0]['freshness'])
        self.assertIn('未知',m.assessed(self.data,None)['evidence'][0]['freshness'])
    def test_xss_escape_and_no_html_sink(self):
        attack='</script><img src=x onerror=alert(1)>'
        self.data['title']=attack;self.data['summary']=attack;self.save()
        output=m.render(self.task).read_text()
        self.assertNotIn(attack,output)
        self.assertIn('\\u003c/script\\u003e',output)
        self.assertNotIn('innerHTML',output)
        self.assertNotIn('https://',output)
    def test_bad_evidence_reference_rejected(self):
        self.data['evidence']=[dict(behavior_ids=['missing'])]
        with self.assertRaises(ValueError):m.validate(self.data)
    def test_missing_simulation_label_rejected(self):
        self.data['scenarios']=[dict(title='bad')]
        with self.assertRaises(ValueError):m.validate(self.data)
    def test_index_escape(self):
        self.data['title']='<script>evil</script>';self.save()
        out=m.build_index(self.task.parent).read_text()
        self.assertNotIn('<script>',out)
        self.assertIn('sample/report.html',out)
    def test_tracked_deletion_invalidates(self):
        p=self.root/'tracked';p.write_text('tracked')
        subprocess.run(['git','add','tracked'],cwd=self.root,check=True)
        before=m.fingerprint(self.task);p.unlink()
        self.assertNotEqual(before,m.fingerprint(self.task))

    def test_handoff_no_implicit_approval(self):
        target=m.export_handoff(self.task)
        self.assertIn('只有接收人明确确认',target.read_text())
        self.assertIn('不会原生加载',target.read_text())
    def test_incident_and_operations_render(self):
        for kind in ['incident','operations']:
            self.data['kind']=kind
            self.data['operations']=[dict(id='O1',action='<script>bad</script>',status='planned')]
            self.save()
            out=m.render(self.task).read_text()
            self.assertNotIn('<script>bad</script>',out)
            self.assertIn('生产与运维',out)
    def test_handoff_change_invalidates(self):
        before=m.fingerprint(self.task)
        self.data['handoffs']=[dict(id='H1',status='pending',readback='new scope')];self.save()
        self.assertNotEqual(before,m.fingerprint(self.task))
    def test_invalid_handoff_state(self):
        self.data['handoffs']=[dict(status='auto-approved')]
        with self.assertRaises(ValueError):m.validate(self.data)

    def test_template_tokens_in_user_data(self):
        self.data['title']='" __TASK_DATA__ __PAGE_TITLE__'
        self.save()
        out=m.render(self.task).read_text()
        payload=out.split('<script id="task-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(payload)['title'],self.data['title'])

if __name__=='__main__':unittest.main()
