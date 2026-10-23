import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

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
    def test_reporting_handoff_does_not_invalidate(self):
        before=m.fingerprint(self.task)
        self.data['handoffs']=[dict(id='H1',status='pending',readback='new scope')];self.save()
        self.assertEqual(before,m.fingerprint(self.task))
    def test_invalid_handoff_state(self):
        self.data['handoffs']=[dict(status='auto-approved')]
        with self.assertRaises(ValueError):m.validate(self.data)

    def test_template_tokens_in_user_data(self):
        self.data['title']='" __TASK_DATA__ __PAGE_TITLE__'
        self.save()
        out=m.render(self.task).read_text()
        payload=out.split('<script id="task-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(payload)['title'],self.data['title'])

    def test_stage_unknown_fields_rejected(self):
        self.data['stage_details']={'unknown': {}}
        with self.assertRaises(ValueError):m.validate(self.data)
        self.data['stage_details']={'requirements': {'custom_html':'<p>hi</p>'}}
        with self.assertRaises(ValueError):m.validate(self.data)
        self.data['stage_details']={'requirements': {'items':[{'id':'R1','status':'done','custom_css':'red'}]}}
        with self.assertRaises(ValueError):m.validate(self.data)
    def test_stage_reference_and_mode(self):
        self.data['stage_details']={'testing': {'items':[dict(id='T1',status='pending',mode='simulation',evidence_ids=['missing'])]}}
        with self.assertRaises(ValueError):m.validate(self.data)
        self.data['stage_details']['testing']['items'][0]['evidence_ids']=[]
        self.assertIs(m.validate(self.data),self.data)
        self.data['stage_details']['testing']['items'][0]['mode']='executed-for-sure'
        with self.assertRaises(ValueError):m.validate(self.data)
    def test_stage_contract_invalidates_and_escapes(self):
        before=m.fingerprint(self.task)
        self.data['stage_details']={'requirements': {'summary':'report','items':[dict(id='R1',status='pending',interpretation='</script><img onerror=alert(1)>')]}}
        self.save()
        self.assertNotEqual(before,m.fingerprint(self.task))
        out=m.render(self.task).read_text()
        self.assertNotIn('</script><img',out)
        self.assertIn('stage-workspace',out)
        self.assertNotIn('// STAGE_SCRIPT',out)
    def test_stage_duplicates_and_steps(self):
        row=dict(id='T1',status='pending',mode='simulation')
        self.data['stage_details']={'testing': {'items':[row,row.copy()]}}
        with self.assertRaises(ValueError):m.validate(self.data)
        self.data['stage_details']['testing']['items']=[dict(row,steps=[dict(action=123)])]
        with self.assertRaises(ValueError):m.validate(self.data)
    def test_all_stage_skeletons(self):
        self.data['stage_details']=m.stage_skeleton()
        self.assertEqual(9,len(self.data['stage_details']))
        m.validate(self.data)

    def test_shared_contract_version_invalidates(self):
        self.data['feature']={'id':'F1','contract_version':'v1'}
        self.save()
        before=m.fingerprint(self.task)
        self.data['feature']['contract_version']='v2'
        self.save()
        self.assertNotEqual(before,m.fingerprint(self.task))

    def test_test_reporting_keeps_evidence_current(self):
        before=m.fingerprint(self.task)
        self.data['stage_details']={'testing':{'items':[dict(id='T1',status='done',mode='recorded',actual='passed',source='logs')]}}
        self.save()
        self.assertEqual(before,m.fingerprint(self.task))
    def test_workflow_routing(self):
        self.assertEqual('understand',m.assessed(self.data,None)['workflow_summary']['step'])
        self.data.update(summary='change',implementation=[{'title':'code'}])
        self.assertEqual('verify',m.assessed(self.data,None)['workflow_summary']['step'])
        self.data['evidence']=[dict(id='E1',status='passed',behavior_ids=['B1'],revision='rev')]
        self.assertEqual('accept',m.assessed(self.data,'rev')['workflow_summary']['step'])
        self.assertEqual('verify',m.assessed(self.data,'other')['workflow_summary']['step'])

    def test_current_action_is_specific(self):
        self.data.update(summary='取消订单',decisions=[dict(id='D1',question='历史订单能取消吗？',recommendation='先只支持新订单',status='pending')])
        result=m.assessed(self.data,None)['workflow_summary']
        self.assertIn('历史订单能取消吗',result['next_action'])
        self.assertEqual('你',result['action_owner'])
        self.assertEqual('solution',result['focus_stage'])
    def test_incident_focus(self):
        self.data['kind']='incident'
        self.assertEqual('operations',m.assessed(self.data,None)['workflow_summary']['focus_stage'])

    def test_all_scenario_renderers_are_embedded(self):
        for kind in m.KINDS:
            self.data['kind']=kind
            self.save()
            output=m.render(self.task).read_text()
            self.assertNotIn('// VIEW_SCRIPT',output)
            for renderer in ['renderFeatureView','renderBugfixView','renderIncidentView','renderOperationsView','renderEngineeringView']:
                self.assertIn('function '+renderer,output)

if __name__=='__main__':unittest.main()
