"""Diagnostic provenance must explain changes without weakening old validity rules."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reviewable as api
import verification
import evidence_context as context


class EvidenceContextTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve(); self.repo = self.root/'repo'; self.repo.mkdir()
        subprocess.run(['git','init','-q',str(self.repo)], check=True)
        (self.repo/'code.txt').write_text('baseline', encoding='utf-8')
        self.task = self.root/'task'; self.task.mkdir()
        self.data = dict(version=1,id='task',title='diagnostics',kind='feature',project_path=str(self.repo),
                         behaviors=[dict(id='B1',before='a',after='b')], evidence=[])
        self.save()
    def save(self):
        (self.task/'task.json').write_text(json.dumps(self.data,ensure_ascii=False), encoding='utf-8')
    def verify(self):
        code="import unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n def test_source(self): self.assertEqual(Path('code.txt').read_text(encoding='utf-8'),'baseline')\nunittest.main()\n"
        result, status = verification.execute(self.task,self.repo,'unittest',['B1'],[sys.executable,'-c',code])
        self.assertEqual(status,0,result); return result
    def detail(self):
        return api.snapshot(self.task)['evidence'][0]['freshness_details']
    def legacy(self):
        root=self.repo; head=b'UNBORN'
        try:head=api.git(['rev-parse','HEAD'],root).strip()
        except subprocess.CalledProcessError:pass
        digest=hashlib.sha256(head)
        digest.update(json.dumps(api.semantic_contract(json.loads((self.task/'task.json').read_text(encoding='utf-8'))),sort_keys=True,ensure_ascii=False).encode())
        for raw in sorted(set(api.git(['ls-files','-z','--cached','--others','--exclude-standard'],root).split(b'\0'))):
            if not raw:continue
            path=root/raw.decode('utf-8','surrogateescape');digest.update(raw+b'\0')
            if path.is_symlink():digest.update(b'LINK'+os.fsencode(os.readlink(path)))
            elif path.is_file():digest.update(b'FILE'+path.read_bytes())
            else:digest.update(b'MISSING')
        return digest.hexdigest()
    def test_legacy_fingerprint_bytes_are_unchanged(self):
        (self.repo/'link').symlink_to(self.root/'not-read')
        self.assertEqual(api.fingerprint(self.task),self.legacy())
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True)
        (self.repo/'code.txt').unlink()
        self.assertEqual(api.fingerprint(self.task),self.legacy())
    def test_new_receipt_current_and_full_context_never_enters_snapshot(self):
        result=self.verify();receipt=json.loads(Path(result['receipt']).read_text(encoding='utf-8'))
        self.assertTrue(context.valid_context(receipt['fingerprint_context'],receipt['fingerprint_before']))
        state=api.snapshot(self.task);self.assertEqual(state['evidence'][0]['freshness_details']['state'],'current')
        self.assertEqual(state['evidence'][0]['verification_source'],'parsed_result')
        self.assertNotIn('fingerprint_context',json.dumps(state));self.assertNotIn('path_bytes_hex',json.dumps(state))
    def test_source_change_names_path_and_preserves_conservative_staleness(self):
        self.verify();(self.repo/'code.txt').write_text('different', encoding='utf-8')
        state=api.snapshot(self.task);d=state['evidence'][0]['freshness_details']
        self.assertEqual(d['state'],'stale');self.assertIn('source_changed',d['reason_codes'])
        self.assertIn('code.txt（内容变化）',d['changed_paths']);self.assertEqual(d['behavior_ids'],['B1'])
        self.assertNotEqual(state['evidence'][0]['freshness'],'当前');self.assertEqual(d['attribution'],'unknown')
    def test_attribution_compares_changed_paths_with_declared_implementation_files(self):
        self.verify();(self.repo/'code.txt').write_text('different', encoding='utf-8')
        self.data=api.load(self.task);self.data['implementation']=[dict(title='edit',description='d',files=['code.txt'])];self.save()
        d=self.detail();self.assertEqual(d['attribution'],'declared_by_this_task');self.assertEqual(d['undeclared_paths'],[])
        self.assertEqual(d['state'],'stale');self.assertIn('source_changed',d['reason_codes'])
        self.data=api.load(self.task);self.data['implementation']=[dict(title='edit',description='d',files='other.txt')];self.save()
        d=self.detail();self.assertEqual(d['attribution'],'outside_declared');self.assertEqual(d['undeclared_paths'],['code.txt'])
        self.assertEqual(d['dependency_scope'],'whole_repository_conservative')
    def test_declared_path_normalization_and_directories(self):
        f = context.declared_files
        self.assertEqual(f([dict(files=['./.github/ci.yml', '.env'])]), {'.github/ci.yml', '.env'})
        self.assertEqual(f([dict(files=['../x.py', '/abs/b.py', 'C:\\a\\b.py', 5, None])]), set())
        self.assertEqual(f([dict(files='src\\c.py')]), {'src/c.py'})
        self.assertEqual(f([dict(files=5)]), set())
        self.assertEqual(f('not a list'), set())
        self.assertEqual(f([dict(files=['src/a.py'])], 'pkg'), {'src/a.py', 'pkg/src/a.py'})
        self.assertEqual(context.attribute(['src/x/y.py'], True, f([dict(files='src/')])), ('declared_by_this_task', []))
        self.assertEqual(context.attribute(['a.py'], False, {'a.py'}), ('unknown', []))
    def test_malformed_implementation_files_never_break_locate_or_receipts(self):
        self.verify();(self.repo/'code.txt').write_text('different', encoding='utf-8')
        self.data=api.load(self.task);self.data['implementation']=[dict(title='x',description='d',files=5)];self.save()
        state=api.snapshot(self.task);e=state['evidence'][0]
        self.assertEqual(e['verification_source'],'parsed_result');self.assertEqual(e['freshness_details']['attribution'],'unknown')
    def test_contract_change_is_separate_from_source(self):
        self.verify();self.data=api.load(self.task);self.data['scope']='changed scope';self.save()
        d=self.detail();self.assertIn('contract_changed',d['reason_codes']);self.assertNotIn('source_changed',d['reason_codes'])
    def test_head_change_is_separate_and_still_stale(self):
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(self.repo),'-c','user.name=Test','-c','user.email=t@example.invalid','commit','-qm','first'],check=True)
        self.verify();subprocess.run(['git','-C',str(self.repo),'-c','user.name=Test','-c','user.email=t@example.invalid','commit','--allow-empty','-qm','next'],check=True)
        d=self.detail();self.assertEqual(d['state'],'stale');self.assertIn('head_changed',d['reason_codes']);self.assertNotIn('source_changed',d['reason_codes'])
    def test_summary_edit_does_not_expire_evidence(self):
        self.verify();self.data=api.load(self.task);self.data['summary']='editorial change';self.save()
        self.assertEqual(self.detail()['state'],'current')
    def test_legacy_claim_cannot_guess_reason_or_actor(self):
        old=api.fingerprint(self.task);self.data['evidence']=[dict(id='E',status='passed',revision=old,behavior_ids=['B1'])];self.save();(self.repo/'code.txt').write_text('change', encoding='utf-8')
        d=self.detail();self.assertEqual(d['baseline'],'legacy_missing');self.assertEqual(d['reason_codes'],['unknown_change']);self.assertEqual(d['changed_paths'],[])
    def test_receipt_log_invalid_precedes_matching_code(self):
        result=self.verify();(Path(result['receipt']).parent/'stdout.log').write_text('altered log', encoding='utf-8')
        e=api.snapshot(self.task)['evidence'][0]
        self.assertEqual(e['freshness'],'当前');self.assertEqual(e['status'],'not_run');self.assertEqual(e['freshness_details']['state'],'invalid_receipt')
        self.assertIn('receipt_invalid',e['freshness_details']['reason_codes'])
    def test_truncated_manifests_do_not_misreport_shifted_paths_as_deleted(self):
        for n in range(4):(self.repo/f'z{n}').write_text(str(n), encoding='utf-8')
        with patch.object(context,'MAX_FILES',2):
            before=api.fingerprint_observation(self.task);(self.repo/'a0').write_text('new', encoding='utf-8');after=api.fingerprint_observation(self.task)
        e=dict(revision=before['fingerprint'],behavior_ids=['B1'])
        d=context.explain(e,after['fingerprint'],after,before)
        self.assertEqual(d['changed_paths'],[]);self.assertIsNone(d['changed_path_count']);self.assertTrue(d['paths_truncated'])
    def test_non_utf8_filename_context_serializes_and_preserves_old_hash(self):
        # macOS rejects such filenames; model Git's raw listing without claiming
        # this filesystem supports creating them.
        name = b'odd-\xff'
        bad_name = name.decode('utf-8', 'surrogateescape')
        original_git, original_link = api.git, Path.is_symlink
        original_file, original_read = Path.is_file, Path.read_bytes
        def observed_git(args, cwd):
            raw = original_git(args, cwd)
            return raw + name + b'\0' if args[0] == 'ls-files' else raw
        def bad(path): return path.name == bad_name
        with patch.object(api, 'git', observed_git), \
             patch.object(Path, 'is_symlink', lambda p: False if bad(p) else original_link(p)), \
             patch.object(Path, 'is_file', lambda p: True if bad(p) else original_file(p)), \
             patch.object(Path, 'read_bytes', lambda p: b'raw' if bad(p) else original_read(p)):
            observation = api.fingerprint_observation(self.task)
            json.dumps(observation,ensure_ascii=False).encode('utf-8')
            self.assertTrue(context.valid_context(observation))
            self.assertEqual(observation['fingerprint'],self.legacy())
            self.verify()
    def test_symlink_target_contents_are_not_read(self):
        external=self.root/'external';external.write_text('one', encoding='utf-8');(self.repo/'external-link').symlink_to(external)
        before=api.fingerprint_observation(self.task);external.write_text('two', encoding='utf-8');after=api.fingerprint_observation(self.task)
        self.assertEqual(before,after);self.assertTrue(any(x['kind']=='link' for x in before['files']))
    def test_unknown_current_and_unbound_do_not_claim_validity(self):
        e=dict(behavior_ids=['B1']);self.assertEqual(context.explain(e,None)['state'],'unknown')
        self.assertEqual(context.explain(e,'a'*64)['state'],'unbound')
        self.data['project_path']=str(self.root/'missing');self.save();self.assertIsNone(api.fingerprint_observation(self.task))
    def test_status_is_readonly_and_supplied_derived_explanation_is_ignored(self):
        self.verify();self.data=api.load(self.task);self.data['evidence'][0]['freshness_details']={'state':'invented'};self.save()
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        state=api.locate(self.task)
        self.assertEqual(state['evidence_freshness']['items'],[])
        self.assertEqual(state['evidence_freshness']['omitted_current_count'],1)
        self.assertEqual(api.snapshot(self.task)['evidence'][0]['freshness_details']['state'],'current')
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_invalid_optional_baseline_cannot_weaken_original_guard(self):
        result=self.verify();path=Path(result['receipt']);receipt=json.loads(path.read_text(encoding='utf-8'));receipt['fingerprint_context']['source_digest']='0'*64;raw=(json.dumps(receipt)+'\n').encode();path.write_bytes(raw)
        self.data=api.load(self.task);self.data['evidence'][0]['verification_receipt']['sha256']=hashlib.sha256(raw).hexdigest();self.save();(self.repo/'code.txt').write_text('change', encoding='utf-8')
        d=self.detail();self.assertEqual(d['state'],'stale');self.assertEqual(d['baseline'],'invalid');self.assertIn('unknown_change',d['reason_codes'])
    def test_historical_detail_does_not_reopen_currently_covered_behavior(self):
        self.verify()
        self.data=api.load(self.task);self.data['scope']='new agreed scope'
        self.data['implementation']=[dict(title='implementation recorded')];self.save()
        self.verify()
        state=api.snapshot(self.task)
        old=state['evidence'][0]['freshness_details']
        self.assertEqual(old['state'],'stale')
        self.assertIn('已有有效覆盖不因旧记录单独重跑',old['recheck'])
        self.assertEqual(state['workflow_summary']['verification']['missing_behavior_ids'],[])
        only_current=api.load(self.task);only_current['evidence']=only_current['evidence'][1:]
        expected=api.assessed(only_current,state['current_fingerprint'],self.task,api.fingerprint_observation(self.task))
        self.assertEqual(state['workflow_summary']['primary_action'],expected['workflow_summary']['primary_action'])
        self.assertIn('历史',api.locate(self.task)['evidence_freshness']['scope_notice'])

    def test_locate_detail_list_is_explicitly_bounded(self):
        self.data['evidence']=[dict(id='E'+str(n),status='passed',revision='a'*64,behavior_ids=['B1']) for n in range(7)];self.save()
        value=api.locate(self.task)['evidence_freshness'];self.assertEqual(value['total'],7);self.assertTrue(value['truncated']);self.assertEqual(len(value['items']),5)


if __name__=='__main__':unittest.main()
