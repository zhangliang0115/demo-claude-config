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

    def tree(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

    def test_report_metadata_only_change_keeps_contract_but_invalidates_snapshot(self):
        feature.render(self.folder)
        first = feature.locate(self.folder)
        self.assertEqual(first['report_state']['freshness'], 'current')
        data = feature.load(self.folder)
        data['design']['goal'] = 'Changed business explanation, not a new API contract'
        feature.save(self.folder, data)
        before = self.tree()
        current = feature.locate(self.folder)
        self.assertEqual(first['contract_version'], current['contract_version'])
        self.assertNotEqual(first['feature_revision'], current['feature_revision'])
        self.assertEqual(current['report_state']['freshness'], 'stale')
        self.assertEqual(current['report'], current['report_state']['path'])
        self.assertEqual(before, self.tree())

    def test_current_child_state_changes_even_after_old_snapshot_is_already_stale(self):
        self.ready_feature()
        feature.sync(self.folder)
        feature.render(self.folder)
        raw = (self.folder / 'feature.json').read_bytes()
        (self.repo / 'package.json').write_text('{"change":1}')
        first = feature.locate(self.folder)
        self.assertEqual(first['report_state']['freshness'], 'stale')
        (self.repo / 'package.json').write_text('{"change":2}')
        second = feature.locate(self.folder)
        self.assertNotEqual(first['assessment_revision'], second['assessment_revision'])
        self.assertEqual(raw, (self.folder / 'feature.json').read_bytes())

    def test_child_metadata_only_change_is_visible_without_sync(self):
        task, child = self.ready_feature()
        feature.sync(self.folder)
        feature.render(self.folder)
        before = feature.locate(self.folder)
        fingerprint = feature.reviewable.fingerprint(task)
        child['title'] = 'Changed handoff title'
        (task / 'task.json').write_text(json.dumps(child))
        after = feature.locate(self.folder)
        self.assertEqual(fingerprint, feature.reviewable.fingerprint(task))
        self.assertEqual(before['feature_revision'], after['feature_revision'])
        self.assertNotEqual(before['assessment_revision'], after['assessment_revision'])
        self.assertEqual(after['report_state']['freshness'], 'stale')

    def test_child_receipt_log_tamper_invalidates_feature_report_readonly(self):
        import verification
        task, child = self.ready_feature()
        child['project_path'] = str(self.repo)
        (task / 'task.json').write_text(json.dumps(child))
        result, code = verification.execute(task, self.repo, 'unittest', ['B1'],
            [sys.executable, '-c', 'import unittest\nclass T(unittest.TestCase):\n def test_one(self): self.assertTrue(True)\nunittest.main()'])
        self.assertEqual(code, 0, result)
        feature.sync(self.folder)
        feature.render(self.folder)
        before_state = feature.locate(self.folder)
        self.assertEqual(before_state['report_state']['freshness'], 'current')
        self.assertEqual(before_state['assessment']['ready_for_integration'], True)
        fingerprint = feature.reviewable.fingerprint(task)
        task_raw = (task / 'task.json').read_bytes()
        (Path(result['receipt']).parent / 'stderr.log').write_text('modified runner output')
        before = self.tree()
        after = feature.locate(self.folder)
        self.assertEqual(fingerprint, feature.reviewable.fingerprint(task))
        self.assertEqual(task_raw, (task / 'task.json').read_bytes())
        self.assertNotEqual(before_state['assessment_revision'], after['assessment_revision'])
        self.assertEqual(after['report_state']['freshness'], 'stale')
        self.assertEqual(before, self.tree())

    def test_feature_report_missing_legacy_and_malformed_are_distinct(self):
        self.assertEqual(feature.locate(self.folder)['report_state']['freshness'], 'missing')
        target = self.folder / 'feature.html'
        for value in ('<h1>legacy</h1>', '<script id="feature-data">[]</script>',
                      '<script id="feature-data">{broken</script>',
                      '<script id="feature-data">{"id":"old"}</script>'):
            target.write_text(value)
            before = self.tree()
            self.assertEqual(feature.locate(self.folder)['report_state']['freshness'], 'unknown')
            self.assertEqual(before, self.tree())

    def test_report_top_level_versions_and_identity_cannot_diverge_from_provenance(self):
        from provenance import read_payload
        target = feature.render(self.folder)
        original = target.read_text()
        recorded = read_payload(original, 'feature-data')
        for field, value in [('feature_revision', '0'*64), ('assessment_revision', '0'*64),
                             ('id', 'different-feature'), ('workspace_path', '/different-workspace')]:
            changed = dict(recorded)
            changed[field] = value
            target.write_text('<script id="feature-data">'+json.dumps(changed)+'</script>')
            self.assertEqual(feature.locate(self.folder)['report_state']['freshness'], 'stale', field)
        target.write_text(original)
        self.assertEqual(feature.locate(self.folder)['report_state']['freshness'], 'current')

    def test_feature_cli_status_and_locate_return_comparable_versions_without_writes(self):
        from provenance import read_payload
        recorded = read_payload(feature.render(self.folder).read_text(), 'feature-data')
        before = self.tree()
        for command in ('status', 'locate'):
            output = subprocess.check_output([sys.executable, feature.__file__, command, str(self.folder)], text=True)
            value = json.loads(output)
            self.assertEqual(value['feature_revision'], recorded['feature_revision'])
            self.assertEqual(value['assessment_revision'], recorded['assessment_revision'])
            self.assertEqual(value['report_state']['freshness'], 'current')
            self.assertEqual(Path(value['report']).resolve(), (self.folder / 'feature.html').resolve())
        self.assertEqual(before, self.tree())

    def test_feature_render_replace_failure_preserves_existing_report(self):
        target = feature.render(self.folder)
        original = target.read_bytes()
        with patch('os.replace', side_effect=PermissionError('injected failure')):
            with self.assertRaises(PermissionError):
                feature.render(self.folder)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(self.folder.glob('.zl-dev-*.tmp')), [])

    def test_feature_feedback_copies_record_and_assessment_versions(self):
        import shutil
        if not shutil.which('node'):
            self.skipTest('Node required for actual feedback execution')
        source = (feature.ROOT / 'assets/feature.html').read_text()
        source = 'function feedback(' + source.split('function feedback(', 1)[1].split('\ntabs.forEach', 1)[0]
        program = r"""
const vm=require('vm'),fs=require('fs'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {constructor(tag,text){this.tag=tag;this.textContent=text||'';this.children=[];this.value='';}append(...xs){this.children.push(...xs);}setAttribute(){}focus(){}}
let copied='';const root=new Element('root');
const env={f:input.data,tabs:[['design','整体设计']],el:(tag,text)=>new Element(tag,text),text:x=>String(x??'尚未记录'),Option:function(t,v){this.textContent=t;this.value=v;},navigator:{clipboard:{writeText:async text=>{copied=text;}}}};
vm.createContext(env);vm.runInContext(input.source,env);env.feedback(root,'design');
const all=[];function walk(n){all.push(n);(n.children||[]).forEach(walk);}walk(root);
const choice=all.find(n=>n.tag==='select');choice.value='需要补充或修改';
const note=all.find(n=>n.tag==='textarea');note.value='QA-FEEDBACK';note.oninput();
(async()=>{await all.find(n=>n.tag==='button').onclick();process.stdout.write(copied);})();
"""
        for data in [dict(id='F1',contract_version='v1',feature_revision='record-version',assessment_revision='assessment-version'), dict(id='F1',contract_version='v1')]:
            copied = subprocess.check_output(['node', '-e', program], input=json.dumps(dict(source=source, data=data)), text=True)
            self.assertIn('共享契约版本：v1', copied)
            self.assertIn('功能记录版本：'+data.get('feature_revision','未知'), copied)
            self.assertIn('功能评估版本：'+data.get('assessment_revision','未知'), copied)
            self.assertIn('QA-FEEDBACK', copied)
            self.assertIn('契约版本相同也不代表本页最新', copied)

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

    def test_high_risk_review_gates_cross_project_readiness(self):
        task, child = self.ready_feature()
        finding = dict(id='R1', status='pending', severity='P0', finding='候补可能被重复晋升')
        child['stage_details'] = {'review': {'items': [finding]}}
        for status, refs, ready in [('pending', [], False), ('done', [], False),
                                     ('done', ['old-failure'], False), ('done', ['retest'], True)]:
            with self.subTest(status=status, refs=refs):
                finding.update(status=status, evidence_ids=refs)
                (task / 'task.json').write_text(json.dumps(child))
                synced = feature.sync(self.folder)
                state = feature.assessed(synced)
                self.assertEqual(state['assessment']['ready_for_integration'], ready)
                snapshot = synced['projects'][0]['snapshot']
                self.assertEqual(len(snapshot['technical_blockers']), 0 if ready else 1)
                if not ready:
                    self.assertIn('P0 R1: 候补可能被重复晋升', str(snapshot['issues']))

    def test_review_changes_invalidate_snapshot_even_when_evidence_counts_match(self):
        task, child = self.ready_feature()
        before = feature.sync(self.folder)
        self.assertTrue(feature.assessed(before)['assessment']['ready_for_integration'])
        finding = dict(id='R1', status='pending', severity='P1', finding='越权调整')
        child['stage_details'] = {'review': {'items': [finding]}}
        (task / 'task.json').write_text(json.dumps(child))
        state = feature.assessed(before)
        self.assertFalse(state['assessment']['ready_for_integration'])
        self.assertEqual(state['projects'][0]['snapshot_freshness'], 'stale')
        synced = feature.sync(self.folder)
        finding['finding'] = '新的越权成立条件'
        (task / 'task.json').write_text(json.dumps(child))
        self.assertEqual(feature.assessed(synced)['projects'][0]['snapshot_freshness'], 'stale')

    def human_ready_child(self, stage='acceptance', result='pass', revision='current', reviewer='human'):
        task, child = self.ready_feature()
        item = dict(id='A1', status='done', scenario='核对通知偏好', instruction='保存后刷新', expected='仍保持',
                    result_status=result, reviewer_kind=reviewer)
        if stage == 'release':
            for field in ('scenario','instruction','expected'):
                item.pop(field)
            item['check'] = '核对通知偏好发布条件'
        child['stage_details'] = {stage: {'items': [item]}}
        (task / 'task.json').write_text(json.dumps(child))
        current = feature.reviewable.fingerprint(task)
        child['evidence'][1]['revision'] = current
        item['reviewed_revision'] = current if revision == 'current' else revision
        (task / 'task.json').write_text(json.dumps(child))
        return task, child

    def test_current_human_return_blocks_cross_project_readiness(self):
        for stage in ('acceptance', 'release'):
            for status in ('fail', 'blocked'):
                with self.subTest(stage=stage, status=status):
                    # Reuse the already created fixture task between subcases.
                    if (self.repo / '.zl-dev/tasks/notification').exists():
                        import shutil
                        shutil.rmtree(self.repo / '.zl-dev/tasks/notification')
                    self.human_ready_child(stage=stage, result=status)
                    synced = feature.sync(self.folder)
                    snapshot = synced['projects'][0]['snapshot']
                    self.assertEqual(snapshot['evidence_counts']['unresolved_current'], 0)
                    self.assertEqual(snapshot['technical_blockers'][0]['type'], 'human_feedback')
                    self.assertIn('人工反馈', str(snapshot['issues']))
                    self.assertFalse(feature.assessed(synced)['assessment']['ready_for_integration'])
                    self.assertEqual(feature.assessed(synced)['projects'][0]['snapshot_freshness'], 'current')

    def test_historical_human_failure_does_not_block_current_integration(self):
        self.human_ready_child(result='fail', revision='old-version')
        synced = feature.sync(self.folder)
        self.assertEqual(synced['projects'][0]['snapshot']['technical_blockers'], [])
        self.assertEqual(synced['projects'][0]['snapshot']['issues'], [])
        self.assertTrue(feature.assessed(synced)['assessment']['ready_for_integration'])
        self.assertIn('不代表交付完成',feature.assessed(synced)['assessment']['delivery'])

    def test_human_feedback_changes_invalidate_snapshot_without_code_change(self):
        task, child = self.human_ready_child(result='not_checked')
        before = feature.sync(self.folder)
        old_fp = feature.reviewable.fingerprint(task)
        self.assertTrue(feature.assessed(before)['assessment']['ready_for_integration'])
        item = child['stage_details']['acceptance']['items'][0]
        item['result_status'] = 'fail'
        (task / 'task.json').write_text(json.dumps(child))
        self.assertEqual(feature.reviewable.fingerprint(task), old_fp)
        state = feature.assessed(before)
        self.assertEqual(state['projects'][0]['snapshot_freshness'], 'stale')
        self.assertFalse(state['assessment']['ready_for_integration'])
        rejected = feature.sync(self.folder)
        item['result_status'] = 'pass'
        (task / 'task.json').write_text(json.dumps(child))
        self.assertEqual(feature.assessed(rejected)['projects'][0]['snapshot_freshness'], 'stale')
        accepted = feature.assessed(feature.sync(self.folder))
        self.assertTrue(accepted['assessment']['ready_for_integration'])
        self.assertIn('不代表交付完成',accepted['assessment']['delivery'])

    def test_ai_or_pending_human_record_is_not_failed_technical_verification(self):
        task, child = self.human_ready_child(result='fail', reviewer='ai')
        self.assertTrue(feature.assessed(feature.sync(self.folder))['assessment']['ready_for_integration'])
        child['stage_details']['acceptance']['items'][0].update(reviewer_kind='human',result_status='not_checked')
        (task / 'task.json').write_text(json.dumps(child))
        self.assertTrue(feature.assessed(feature.sync(self.folder))['assessment']['ready_for_integration'])

    def test_pending_business_decision_is_not_failed_technical_verification(self):
        task, child = self.ready_feature()
        child['decisions'] = [dict(id='D1', status='pending', question='上线日期？')]
        (task / 'task.json').write_text(json.dumps(child))
        state = feature.assessed(feature.sync(self.folder))
        self.assertTrue(state['assessment']['ready_for_integration'])
        self.assertEqual(state['projects'][0]['snapshot']['technical_blockers'], [])

    def test_legacy_claim_source_is_visible_without_blocking_integration(self):
        task, child = self.ready_feature()
        assessed = feature.reviewable.assessed(child, feature.reviewable.fingerprint(task), task_dir=task)
        summary = assessed['workflow_summary']
        self.assertEqual(summary['verification']['current_source_counts'], {'claim': 1, 'parsed_result': 0, 'invalid': 0})
        self.assertIn('部分尚无脚本解析', summary['primary_action']['reason'])
        self.assertTrue(feature.assessed(feature.sync(self.folder))['assessment']['ready_for_integration'])

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
