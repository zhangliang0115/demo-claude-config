import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import reviewable
import verification

class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.repo=self.root/'repo'; self.repo.mkdir()
        subprocess.run(['git','init','-q',str(self.repo)],check=True)
        (self.repo/'code.txt').write_text('baseline')
        self.task=self.root/'task'; self.task.mkdir()
        self.data=dict(version=1,id='t',title='test',kind='feature',project_path=str(self.repo),behaviors=[dict(id='B1',before='a',after='b')],evidence=[])
        self.save()
    def save(self):
        (self.task/'task.json').write_text(json.dumps(self.data))
    def run_code(self, code, **kwargs):
        return verification.execute(self.task,self.repo,'unittest',['B1'],[sys.executable,'-c',code],**kwargs)
    def make_code(self, assertion='self.assertEqual(1,1)', decorator=''):
        return "import unittest\nclass T(unittest.TestCase):\n "+decorator+("\n " if decorator else '')+"def test_one(self): "+assertion+"\nunittest.main()\n"
    def test_equivalent_absolute_project_alias_keeps_real_receipt_valid(self):
        alias = self.root/'project-alias'
        alias.symlink_to(self.repo, target_is_directory=True)
        self.data['project_path'] = str(alias)
        self.save()
        result, code = self.run_code(self.make_code())
        self.assertEqual(code, 0, result)
        state = reviewable.snapshot(self.task)
        self.assertEqual(state['evidence'][0]['verification_source'], 'parsed_result')
        self.assertEqual(state['evidence'][0]['status'], 'passed')
    def test_pass_receipt_reparse_and_readonly(self):
        result,code=self.run_code(self.make_code()); self.assertEqual(code,0,result)
        data=reviewable.load(self.task); before={str(p):(p.stat().st_mtime_ns,p.read_bytes()) for p in self.task.rglob('*') if p.is_file()}
        evidence=data['evidence'][0]
        receipt=json.loads(Path(result['receipt']).read_text())
        self.assertEqual(evidence['source'],result['receipt'])
        self.assertEqual(json.loads(evidence['command']),receipt['argv'])
        self.assertIn('非人工',evidence['actor'])
        self.assertEqual(evidence['executed_at'],receipt['finished_at'])
        self.assertIn(str(self.repo),evidence['environment'])
        self.assertIn('总计 1，通过 1，失败 0，错误 0，跳过 0',evidence['summary'])
        assessed=reviewable.assessed(data,reviewable.fingerprint(self.task),self.task)
        self.assertEqual(assessed['evidence'][0]['verification_source'],'parsed_result')
        self.assertEqual(assessed['evidence'][0]['parsed_result']['counts']['passed'],1)
        reviewable.locate(self.task)
        self.assertEqual(before,{str(p):(p.stat().st_mtime_ns,p.read_bytes()) for p in self.task.rglob('*') if p.is_file()})
    def test_failure_preserved(self):
        result,code=self.run_code(self.make_code('self.fail("broken")')); self.assertEqual(code,1)
        self.assertEqual(result['parsed_result']['status'],'failed'); self.assertTrue(result['evidence_appended'])
        self.assertIn('broken',(Path(result['receipt']).parent/'stderr.log').read_text())
    def test_zero_skipped_unknown(self):
        for code in ['import unittest; unittest.main()',self.make_code(decorator='@unittest.skip("skip")'),'print("all passed")']:
            with self.subTest(code=code):
                result,status=self.run_code(code); self.assertEqual(status,1)
                self.assertNotEqual((result['parsed_result'] or {}).get('status'),'passed')
                if result['parsed_result'] is None:
                    self.assertIn('未能解析测试结果',reviewable.load(self.task)['evidence'][-1]['summary'])
    def test_fingerprint_change_never_appends(self):
        result,status=self.run_code("from pathlib import Path; Path('code.txt').write_text('changed');\n"+self.make_code())
        self.assertEqual(status,1); self.assertFalse(result['evidence_appended']); self.assertTrue(Path(result['receipt']).exists())
        self.assertEqual(reviewable.load(self.task)['evidence'],[])
    def test_task_change_never_overwrites(self):
        code="from pathlib import Path; import json; p=Path("+repr(str(self.task/'task.json'))+"); d=json.loads(p.read_text()); d['title']='new'; p.write_text(json.dumps(d));\n"+self.make_code()
        result,status=self.run_code(code); self.assertEqual(status,1); self.assertEqual(reviewable.load(self.task)['title'],'new'); self.assertFalse(result['evidence_appended'])
    def test_cas_conflict_keeps_receipt(self):
        with patch.object(reviewable,'update_task',side_effect=ValueError('conflict')):
            result,status=self.run_code(self.make_code())
        self.assertEqual(status,1); self.assertFalse(result['evidence_appended']); self.assertTrue(Path(result['receipt']).exists())
    def test_argv_not_shell(self):
        marker=self.repo/'injected'
        code=self.make_code()
        result,status=verification.execute(self.task,self.repo,'unittest',['B1'],[sys.executable,'-c',code,'; touch '+str(marker)])
        self.assertFalse(marker.exists()); self.assertEqual(status,1) # unittest rejects the literal extra argument
    def test_tampered_log_and_model_field_cannot_green(self):
        result,status=self.run_code(self.make_code()); data=reviewable.load(self.task)
        (Path(result['receipt']).parent/'stderr.log').write_text('forged')
        data['evidence'][0]['parsed_result']=dict(status='passed')
        assessed=reviewable.assessed(data,reviewable.fingerprint(self.task),self.task)['evidence'][0]
        self.assertEqual(assessed['verification_source'],'invalid'); self.assertEqual(assessed['status'],'not_run'); self.assertNotIn('parsed_result',assessed)
    def test_tampered_receipt_identity(self):
        result,status=self.run_code(self.make_code()); data=reviewable.load(self.task); ref=data['evidence'][0]['verification_receipt']; p=Path(result['receipt']); r=json.loads(p.read_text()); r['task_id']='other'; raw=json.dumps(r).encode(); p.write_bytes(raw); ref['sha256']=verification.sha(raw)
        self.assertEqual(reviewable.assessed(data,reviewable.fingerprint(self.task),self.task)['evidence'][0]['verification_source'],'invalid')
    def test_deleted_task_preserves_receipt(self):
        code='from pathlib import Path; Path('+repr(str(self.task/'task.json'))+').unlink();\n'+self.make_code()
        result,status=self.run_code(code)
        self.assertEqual(status,1); self.assertFalse(result['evidence_appended']); self.assertTrue(Path(result['receipt']).exists())
    def test_timeout_retains_logs(self):
        result,status=self.run_code('import time; print("start",flush=True); time.sleep(10)',timeout=.1)
        self.assertEqual(status,1); self.assertTrue(Path(result['receipt']).exists()); self.assertTrue(json.loads(Path(result['receipt']).read_text())['timed_out'])
    def test_junit_subprocess_counts(self):
        result_path=self.root/'results.xml'
        code="from pathlib import Path; Path("+repr(str(result_path))+").write_text('<testsuite tests=\"2\"><testcase name=\"a\"/><testcase name=\"b\"/></testsuite>')"
        result,status=verification.execute(self.task,self.repo,'junit',['B1'],[sys.executable,'-c',code],result_path)
        self.assertEqual(status,0,result); self.assertEqual(result['parsed_result']['counts']['passed'],2)
        e=reviewable.assessed(reviewable.load(self.task),reviewable.fingerprint(self.task),self.task)['evidence'][0]
        self.assertEqual(e['verification_source'],'parsed_result')
    def test_junit_malformed_zero_skipped_and_conflict(self):
        for raw in [b'<x/>',b'<testsuite tests="0"/>',b'<testsuite><testcase><skipped/></testcase></testsuite>',b'<testsuite tests="3"><testcase/></testsuite>',b'<!DOCTYPE a><testsuite/>']:
            with self.subTest(raw=raw):
                try: result=verification.parse_result('junit',raw,0)
                except ValueError: continue
                self.assertNotEqual(result['status'],'passed')
    def test_oversized_log_streams_hash_and_never_greens(self):
        original=Path.read_bytes
        def guarded(path):
            if path.name in {'stdout.log','stderr.log'}:
                raise AssertionError('execution must hash logs without reading whole file')
            return original(path)
        with patch.object(verification,'CAP',128), patch.object(Path,'read_bytes',new=guarded):
            result,status=self.run_code('print("x"*12000)\n'+self.make_code())
        self.assertEqual(status,1); self.assertIsNone(result['parsed_result'])
        self.assertGreater((Path(result['receipt']).parent/'stdout.log').stat().st_size,12000)
        receipt=json.loads(Path(result['receipt']).read_text())
        self.assertIn('上限',receipt['parse_error'])
        self.assertEqual(receipt['logs']['stdout']['sha256'],verification.file_sha(Path(result['receipt']).parent/'stdout.log'))
    def test_cli_executes_without_render(self):
        script=Path(reviewable.__file__).resolve()
        proc=subprocess.run([sys.executable,str(script),'verify',str(self.task),'--project',str(self.repo),'--format','unittest','--behavior','B1','--',sys.executable,'-c',self.make_code()],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout)
        self.assertTrue(json.loads(proc.stdout)['evidence_appended'])
        self.assertFalse((self.task/'report.html').exists())
    def test_junit_aggregate_and_suite_failure_never_green(self):
        examples=[
            b'<testsuites tests="2" failures="1"><testsuite tests="1" failures="0"><testcase name="ok"/></testsuite></testsuites>',
            b'<testsuites><testsuite><testcase name="ok"/><error message="setup failed"/></testsuite></testsuites>',
            b'<testsuites><testcase name="ok"/><failure/></testsuites>',
            b'<testsuites><testsuites tests="1" errors="1"><testsuite tests="1"><testcase name="ok"/></testsuite></testsuites></testsuites>',
            b'<testsuites failures="1" tests="0"/>',
            b'<testsuite><testcase><error xmlns="urn:unknown"/></testcase></testsuite>',
        ]
        for raw in examples:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                verification.parse_result('junit',raw,0)
        valid=b'<testsuites tests="2" failures="0"><testsuites tests="1"><testsuite tests="1"><testcase name="a"/></testsuite></testsuites><testsuite tests="1"><testcase name="b"/></testsuite></testsuites>'
        self.assertEqual(verification.parse_result('junit',valid,0)['status'],'passed')
    def test_malformed_receipts_are_invalid_not_crashes(self):
        result,status=self.run_code(self.make_code()); data=reviewable.load(self.task); path=Path(result['receipt']); original=json.loads(path.read_text())
        variants=[[],None,True,42,'oops',{},dict(original,logs=[]),dict(original,logs={'stdout':[],'stderr':original['logs']['stderr']}),dict(original,logs={'stdout':{'path':[],'sha256':'x'},'stderr':original['logs']['stderr']}),dict(original,argv='python'),dict(original,started_at=[]),dict(original,exit_code=True),dict(original,fingerprint_before=[]),dict(original,format='junit',result_file=[]),dict(original,format='junit',result_file={'path':{},'sha256':None})]
        for variant in variants:
            with self.subTest(variant=variant):
                raw=json.dumps(variant).encode(); path.write_bytes(raw)
                data['evidence'][0]['verification_receipt']['sha256']=verification.sha(raw)
                e=reviewable.assessed(data,reviewable.fingerprint(self.task),self.task)['evidence'][0]
                self.assertEqual(e['verification_source'],'invalid'); self.assertEqual(e['status'],'not_run')
        for ref in [None,{},[],{'path':[],'sha256':'x'},{'path':None,'sha256':{}},['x']]:
            data['evidence'][0]['verification_receipt']=ref
            self.assertEqual(reviewable.assessed(data,reviewable.fingerprint(self.task),self.task)['evidence'][0]['verification_source'],'invalid')
    def test_schema_and_semantic_contract(self):
        self.data['acceptance_setup']=dict(environment='local',entry_url='https://localhost/test',prepare_command='do not run',baseline='seed',stop='ctrl-c',notes='')
        before=reviewable.semantic_contract(self.data); reviewable.validate(self.data)
        self.data['stage_details']={'acceptance':dict(items=[dict(id='a',status='done',reviewed_revision='abc',reviewer_kind='human',verification_mode='manual')])}
        reviewable.validate(self.data); original=json.loads(json.dumps(reviewable.semantic_contract(self.data)))
        self.data['stage_details']['acceptance']['items'][0]['reviewer_kind']='ai'
        self.assertEqual(original,reviewable.semantic_contract(self.data))
        self.data['acceptance_setup']['baseline']='other'; self.assertNotEqual(original,reviewable.semantic_contract(self.data))
        self.data['acceptance_setup']['entry_url']='javascript:evil()'
        with self.assertRaises(ValueError): reviewable.validate(self.data)

if __name__=='__main__': unittest.main()
