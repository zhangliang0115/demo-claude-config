"""Read-only analysis has source provenance, not a development/acceptance lifecycle."""
from contextlib import redirect_stdout, redirect_stderr
import copy
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
import analysis
import feature
import reviewable
import verification
from workflow import summarize


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.repo = self.root/'repo';self.repo.mkdir()
        subprocess.run(['git','init','-q',str(self.repo)],check=True)
        (self.repo/'service.py').write_text('def cancel(order):\n    return order.amount\n')
        self.other=self.root/'other';self.other.mkdir()
        (self.other/'view.py').write_text('amount = response["amount"]\n')
        self.folder=self.root/'task';self.folder.mkdir()
        self.data=dict(version=1,id='a',title='金额来源',kind='analysis',project_path=str(self.repo),summary='解释金额来源',behaviors=[],implementation=[],evidence=[],analysis=dict(mode='data_flow',question='金额从何而来？',conclusion='源码把订单金额直接返回。',project_paths=[],sources=[analysis.source(self.repo,'service.py')],steps=[dict(id='P1',title='金额读取',description='读取并返回',source_ids=['S1'])],mappings=[dict(id='M1',**{'from':'order.amount','to':'response.amount'},transformation='直接返回',source_ids=['S1'])],findings=[dict(id='F1',classification='fact',statement='直接返回金额',source_ids=['S1'])],gaps=[]))
        self.save()

    def save(self):
        (self.folder/'task.json').write_text(json.dumps(self.data,ensure_ascii=False))

    def tree(self):
        return {str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

    def state(self):
        return reviewable.snapshot(self.folder)

    def test_documented_without_behavior_implementation_or_acceptance(self):
        result=self.state()['workflow_summary']
        self.assertEqual(result['step'],'analysis_documented')
        self.assertEqual(result['focus_stage'],'analysis')
        self.assertEqual(result['action_owner'],'none')
        self.assertEqual(result['missing_verification_count'],0)
        self.assertNotIn('请亲自核验',result['next_action'])

    def test_analysis_stage_cannot_disguise_development_kind(self):
        data=copy.deepcopy(self.data);data['kind']='feature';data['focus_stage']='analysis'
        with self.assertRaises(ValueError):reviewable.validate(data)
        for stage in ('implementation','acceptance','testing'):
            data=copy.deepcopy(self.data);data['focus_stage']=stage
            with self.assertRaises(ValueError):reviewable.validate(data)

    def test_missing_question_material_and_conclusion_stay_readonly(self):
        for key,expected in [('question','analysis_scope'),('conclusion','analyze'),('sources','analyze'),('steps','analyze')]:
            with self.subTest(key=key):
                task=copy.deepcopy(self.data)
                task['analysis'][key]='' if key in {'question','conclusion'} else []
                if key=='sources':
                    for group in ('steps','mappings','findings'):task['analysis'][group]=[]
                result=analysis.summarize(task)
                self.assertEqual(result['step'],expected)
                self.assertNotIn(result['step'],{'implement','verify','accept'})

    def test_source_cli_and_assessment_are_readonly(self):
        before=self.tree();out=io.StringIO()
        with patch.object(sys,'argv',['analysis.py','source','--id','S2','--project',str(self.repo),'--path','service.py','--line-start','2','--line-end','2']),redirect_stdout(out):
            self.assertEqual(analysis.main(),0)
        self.assertEqual(json.loads(out.getvalue())['sha256'],hashlib.sha256((self.repo/'service.py').read_bytes()).hexdigest())
        self.state();self.assertEqual(before,self.tree())

    def test_invalid_shapes_references_and_fact_without_source_rejected(self):
        mutations=[lambda a:a.update(mode=[]),lambda a:a['findings'][0].update(source_ids=[]),lambda a:a['steps'][0].update(source_ids=['missing']),lambda a:a['mappings'][0].update(source_ids=[{}]),lambda a:a['sources'][0].update(sha256='bad'),lambda a:a['sources'][0].update(line_start=True),lambda a:a['sources'][0].update(status='current')]
        for change in mutations:
            data=copy.deepcopy(self.data);change(data['analysis'])
            with self.subTest(data=data):
                with self.assertRaises(ValueError):reviewable.validate(data)

    def test_inference_and_unknown_do_not_become_fact(self):
        self.data['analysis']['findings']=[dict(id='I1',classification='inference',statement='可能由旧系统维护',source_ids=[]),dict(id='U1',classification='unknown',statement='实际生产值未知',source_ids=[])]
        self.save();state=self.state()
        self.assertEqual(state['analysis_assessment']['inference_count'],1)
        self.assertEqual(state['analysis_assessment']['unknown_count'],1)
        self.assertEqual(state['workflow_summary']['step'],'analysis_investigate')
        self.assertEqual(state['analysis']['findings'][0]['classification'],'inference')

    def test_only_inference_and_unknown_cannot_be_documented(self):
        self.data['analysis'].update(sources=[],steps=[],mappings=[],findings=[dict(id='I1',classification='inference',statement='只是推测',source_ids=[])])
        self.save();self.assertFalse(self.state()['analysis_assessment']['documented'])
        self.assertEqual(self.state()['workflow_summary']['step'],'analyze')

    def test_gap_is_partial_not_user_acceptance(self):
        self.data['analysis']['gaps']=[dict(id='G1',description='下游不在本次范围',next_action='后续扩大范围时另行追踪',disposition='out_of_scope')]
        self.save();state=self.state()
        self.assertEqual(state['workflow_summary']['step'],'analysis_partial')
        self.assertEqual(state['workflow_summary']['action_owner'],'none')
        self.assertEqual(state['analysis_assessment']['gap_count'],1)

    def test_gap_dispositions_choose_readonly_work_or_concrete_material(self):
        for disposition,expected,owner in [('investigate','analysis_investigate','AI'),('needs_input','analysis_input','你')]:
            self.data['analysis']['gaps']=[dict(id='G1',description='需追踪下游',next_action='提供下游源代码目录',disposition=disposition)];self.save()
            state=self.state()
            self.assertEqual((state['workflow_summary']['step'],state['workflow_summary']['action_owner']),(expected,owner))
            self.assertNotIn(state['workflow_summary']['step'],{'accept','implement','verify'})
        self.data['analysis']['gaps'][0].pop('disposition');self.save()
        self.assertEqual(self.state()['workflow_summary']['step'],'analysis_investigate')

    def test_input_gap_can_request_missing_material_before_full_trace_exists(self):
        self.data['analysis'].update(sources=[],steps=[],mappings=[],findings=[],gaps=[dict(id='G1',description='仓库尚未提供',next_action='提供已授权读取的仓库目录',disposition='needs_input')]);self.save()
        self.assertEqual(self.state()['workflow_summary']['step'],'analysis_input')

    def test_unavailable_source_with_explicit_input_gap_requests_material(self):
        (self.repo/'service.py').unlink()
        self.data['analysis']['gaps']=[dict(id='G1',description='源代码已不在可读路径',next_action='提供当前可读的代码副本',disposition='needs_input')];self.save()
        state=self.state()
        self.assertEqual(state['workflow_summary']['step'],'analysis_input')
        self.assertFalse(state['analysis_assessment']['documented'])
        self.assertEqual(state['workflow_summary']['blockers'][0]['type'],'analysis_source')

    def test_scope_gap_can_explain_unknown_but_unattributed_unknown_keeps_work(self):
        self.data['analysis']['findings'].append(dict(id='U1',classification='unknown',statement='生产实际数据未知',source_ids=[]))
        self.data['analysis']['gaps']=[dict(id='G1',description='本次不查询生产',next_action='仅在另行提供运行材料后补充',disposition='out_of_scope')];self.save()
        self.assertEqual(self.state()['workflow_summary']['step'],'analysis_partial')
        self.data['analysis']['gaps']=[];self.save()
        self.assertEqual(self.state()['workflow_summary']['step'],'analysis_investigate')

    def test_compact_locate_analysis_summary_has_counts_without_full_sources(self):
        summary=reviewable.locate(self.folder)['analysis_summary']
        self.assertEqual(summary['question'],'金额从何而来？')
        self.assertEqual(summary['source_counts']['current'],1)
        self.assertNotIn('sources',summary)

    def test_extra_project_non_git_source_changes_assessment_and_old_report(self):
        self.data['analysis']['project_paths']=[str(self.other)]
        self.data['analysis']['sources'].append(analysis.source(self.other,'view.py','S2'))
        self.save();reviewable.render(self.folder);before=self.state();primary=before['current_fingerprint']
        (self.other/'view.py').write_text('amount = response["net"]\n')
        after=self.state()
        self.assertEqual(primary,after['current_fingerprint'])
        self.assertNotEqual(before['assessment_revision'],after['assessment_revision'])
        self.assertEqual(after['analysis_assessment']['sources'][1]['status'],'stale')
        self.assertEqual(reviewable.report_state(self.folder)['freshness'],'stale')
        html=(self.folder/'report.html').read_bytes()
        with self.assertRaises(ValueError):reviewable.render(self.folder,before)
        self.assertEqual(html,(self.folder/'report.html').read_bytes())

    def test_already_stale_source_changes_remain_visible(self):
        (self.repo/'service.py').write_text('first change\nsecond line\n');one=self.state()
        (self.repo/'service.py').write_text('other change\nsecond line\n');two=self.state()
        self.assertEqual(one['analysis_assessment']['sources'][0]['status'],'stale')
        self.assertEqual(two['analysis_assessment']['sources'][0]['status'],'stale')
        self.assertNotEqual(one['assessment_revision'],two['assessment_revision'])
        self.assertEqual(self.data['analysis']['sources'][0]['sha256'],two['analysis']['sources'][0]['sha256'])

    def test_invalid_but_readable_source_changes_keep_observed_hash(self):
        for first,second in [(b'\x00binary-1',b'\x00binary-2'),(b'\xffinvalid-1',b'\xffinvalid-2')]:
            (self.repo/'service.py').write_bytes(first);one=self.state()
            (self.repo/'service.py').write_bytes(second);two=self.state()
            self.assertEqual(one['analysis_assessment']['sources'][0]['status'],'invalid')
            self.assertEqual(two['analysis_assessment']['sources'][0]['status'],'invalid')
            self.assertNotEqual(one['analysis_assessment']['sources'][0]['current_sha256'],two['analysis_assessment']['sources'][0]['current_sha256'])
            self.assertNotEqual(one['assessment_revision'],two['assessment_revision'])

    def test_ignored_source_change_visible_even_when_git_fingerprint_stable(self):
        (self.repo/'.gitignore').write_text('ignored.py\n');(self.repo/'ignored.py').write_text('secret = 1\n')
        self.data['analysis']['sources']=[analysis.source(self.repo,'ignored.py')]
        self.save();before=self.state();(self.repo/'ignored.py').write_text('secret = 2\n');after=self.state()
        self.assertEqual(before['current_fingerprint'],after['current_fingerprint'])
        self.assertNotEqual(before['assessment_revision'],after['assessment_revision'])
        self.assertEqual(after['workflow_summary']['step'],'analysis_refresh')

    def test_non_git_primary_can_inspect_source_without_claiming_git_current(self):
        self.data['project_path']=str(self.other);self.data['analysis']['sources']=[analysis.source(self.other,'view.py')]
        self.save();state=self.state();self.assertIsNone(state['current_fingerprint'])
        self.assertEqual(state['analysis_assessment']['sources'][0]['status'],'current')
        reviewable.render(self.folder);self.assertEqual(reviewable.report_state(self.folder)['freshness'],'unknown')

    def test_missing_range_invalid_and_traversal_symlink_escape(self):
        (self.repo/'escape.py').symlink_to(self.other/'view.py')
        for value in ('../other/view.py','/etc/passwd','escape.py'):
            with self.subTest(path=value):
                with self.assertRaises(ValueError):analysis.source(self.repo,value)
        with self.assertRaises(ValueError):analysis.source(self.repo,'service.py',line_end=9)
        (self.repo/'service.py').unlink();self.assertEqual(self.state()['analysis_assessment']['sources'][0]['status'],'unavailable')
        (self.repo/'service.py').write_text('one\n');self.assertEqual(self.state()['analysis_assessment']['sources'][0]['status'],'invalid')

    def test_undeclared_external_project_rejected(self):
        self.data['analysis']['sources'].append(analysis.source(self.other,'view.py','S2'))
        with self.assertRaises(ValueError):reviewable.validate(self.data)

    def test_analysis_observations_do_not_invalidate_own_code_contract(self):
        first=reviewable.fingerprint(self.folder)
        self.data['analysis']['conclusion']='补充说明';self.data['analysis']['sources'][0]['sha256']='0'*64;self.save()
        self.assertEqual(first,reviewable.fingerprint(self.folder))
        self.data['analysis']['question']='新问题';self.save();self.assertNotEqual(first,reviewable.fingerprint(self.folder))

    def test_old_kind_contract_has_no_analysis_key(self):
        old=copy.deepcopy(self.data);old['kind']='feature'
        self.assertNotIn('analysis',reviewable.semantic_contract(old))
        before=reviewable.semantic_contract(old);old['analysis']['question']='different'
        self.assertEqual(before,reviewable.semantic_contract(old))

    def test_fake_assessment_cannot_override_snapshot(self):
        self.data['analysis_assessment']={'documented':True,'sources':[]}
        (self.repo/'service.py').write_text('changed\nsecond\n');self.save()
        self.assertEqual(self.state()['workflow_summary']['step'],'analysis_refresh')

    def test_analysis_rejects_verify_before_starting_or_writing_runs(self):
        marker=self.root/'executed';before=self.tree()
        with self.assertRaises(ValueError):verification.execute(self.folder,self.repo,'unittest',['B1'],[sys.executable,'-c',f'open({str(marker)!r},"w").write("bad")'])
        self.assertFalse(marker.exists());self.assertEqual(before,self.tree())

    def test_analysis_child_never_counts_as_implementation_ready(self):
        self.data.update(contract_version='v1',behaviors=[dict(id='B1',after='claimed behavior')],implementation=[dict(title='claimed implementation')]);self.save()
        self.data['evidence']=[dict(id='E1',status='passed',revision=reviewable.fingerprint(self.folder),behavior_ids=['B1'])];self.save()
        coord=self.root/'feature';feature.init(coord,'整体',['app='+str(self.repo)],self.root)
        data=feature.load(coord);data['projects'][0].update(task_path=str(self.folder),contract_version='v1');data['contract_version']='v1';feature.save(coord,data)
        snap=feature.project_snapshot(data['projects'][0])
        self.assertEqual(snap['evidence_counts']['passed_current'],1)
        self.assertEqual(snap['missing_behaviors'],0)
        self.assertTrue(any('只读分析' in value for value in snap['issues']))

    def test_init_analysis_without_html_creates_analysis_skeleton(self):
        new=self.root/'new';out=io.StringIO()
        with patch.object(sys,'argv',['reviewable.py','init',str(new),'--project',str(self.repo),'--kind','analysis','--no-render']),redirect_stdout(out):self.assertEqual(reviewable.main(),0)
        data=reviewable.load(new)
        self.assertEqual(data['focus_stage'],'analysis');self.assertEqual(data['analysis']['mode'],'business_logic')
        self.assertFalse((new/'report.html').exists())


if __name__=='__main__':unittest.main()
