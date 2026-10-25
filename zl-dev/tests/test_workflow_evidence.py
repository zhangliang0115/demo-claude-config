import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from workflow import summarize

class CurrentEvidenceTests(unittest.TestCase):
    def task(self, evidence):
        return dict(title='capacity',summary='Adjust capacity',kind='change',behaviors=[dict(id='B1',after='confirmed capacity invariant')],implementation=[dict(title='transaction')],evidence=evidence)

    def test_current_failure_cannot_be_hidden_by_pass(self):
        evidence=[dict(id='ok',status='passed',freshness='当前',behavior_ids=['B1']),dict(id='bad',status='failed',freshness='当前',behavior_ids=['B1'])]
        result=summarize(self.task(evidence))
        self.assertEqual(result['step'],'verify')
        self.assertEqual(result['missing_verification_count'],1)
        self.assertEqual(result['action_owner'],'AI')

    def test_old_failure_does_not_override_current_coverage(self):
        evidence=[dict(id='old',status='failed',freshness='过期',behavior_ids=['B1']),dict(id='new',status='passed',freshness='当前',behavior_ids=['B1'])]
        result=summarize(self.task(evidence))
        self.assertEqual(result['step'],'accept')
        self.assertEqual(result['stale_evidence_count'],1)

    def test_unscoped_current_failure_still_blocks_acceptance(self):
        evidence=[dict(id='ok',status='passed',freshness='当前',behavior_ids=['B1']),dict(id='environment',status='blocked',freshness='当前',behavior_ids=[])]
        result=summarize(self.task(evidence))
        self.assertEqual(result['step'],'verify')
        self.assertEqual(result['unresolved_current_evidence_count'],1)

class CurrentActionTests(unittest.TestCase):
    task = CurrentEvidenceTests.task

    def passed_task(self):
        return self.task([dict(id='ok', status='passed', freshness='当前', behavior_ids=['B1'])])

    def review(self, status='pending', refs=None, severity='P0'):
        return dict(id='R1', finding='不能重复晋升', severity=severity, status=status, evidence_ids=refs or [])

    def with_review(self, finding):
        task = self.passed_task()
        task['stage_details'] = {'review': {'items': [finding]}}
        return task

    def test_passed_behavior_does_not_hide_pending_p0(self):
        result = summarize(self.with_review(self.review()))
        self.assertEqual((result['step'], result['focus_stage'], result['action_owner']), ('review', 'review', 'AI'))
        self.assertEqual(result['verification']['covered_behavior_ids'], ['B1'])
        self.assertEqual(result['blockers'][0]['id'], 'R1')

    def test_done_requires_current_successful_recheck(self):
        for refs, evidence in [([], []), (['missing'], []), (['old'], [dict(id='old', status='passed', freshness='过期', behavior_ids=['B1'])]), (['failed'], [dict(id='failed', status='failed', freshness='当前', behavior_ids=['B1'])])]:
            with self.subTest(refs=refs):
                task = self.with_review(self.review('done', refs))
                task['evidence'].extend(evidence)
                result = summarize(task)
                self.assertTrue(any(x['type'] == 'review' for x in result['blockers']))
                self.assertEqual(result['action_owner'], 'AI')

    def test_done_with_current_passed_recheck_allows_human_verification(self):
        result = summarize(self.with_review(self.review('done', ['ok'])))
        self.assertEqual(result['step'], 'accept')
        self.assertEqual(result['blockers'], [])

    def test_done_reference_cannot_hide_behavior_contradiction(self):
        task = self.with_review(self.review('done', ['ok']))
        task['evidence'].append(dict(id='bad', status='failed', freshness='当前', behavior_ids=['B1']))
        result = summarize(task)
        self.assertEqual(result['step'], 'verify')
        self.assertTrue(any(x['type'] == 'review' for x in result['blockers']))
        self.assertEqual(result['verification']['covered_behavior_ids'], [])

    def test_done_requires_every_referenced_evidence_to_be_current_passed(self):
        task = self.with_review(self.review('done', ['ok', 'old']))
        task['evidence'].append(dict(id='old', status='passed', freshness='过期', behavior_ids=['B1']))
        self.assertEqual(summarize(task)['step'], 'review')

    def test_low_risk_findings_are_visible_without_blocking(self):
        for severity in ('P2', 'P3'):
            task = self.with_review(self.review(severity=severity))
            result = summarize(task)
            self.assertEqual(result['step'], 'accept')
            self.assertEqual(result['review_warnings'][0]['severity'], severity)
            self.assertEqual(result['blockers'], [])

    def test_explicit_acceptance_cannot_hide_failed_current_evidence(self):
        task = self.passed_task()
        task['focus_stage'] = 'acceptance'
        task['evidence'].append(dict(id='bad', status='failed', freshness='当前', behavior_ids=[]))
        result = summarize(task)
        self.assertEqual(result['requested_focus_stage'], 'acceptance')
        self.assertEqual(result['focus_stage'], 'testing')
        self.assertEqual(result['primary_action']['owner'], 'AI')

    def test_business_decision_does_not_mask_ai_blocker(self):
        for failure in ('evidence', 'review'):
            task = self.with_review(self.review()) if failure == 'review' else self.passed_task()
            if failure == 'evidence':
                task['evidence'].append(dict(id='bad', status='blocked', freshness='当前', behavior_ids=[]))
            task['decisions'] = [dict(id='D1', status='pending', question='最多增加几个名额？')]
            result = summarize(task)
            self.assertEqual(result['action_owner'], 'AI')
            self.assertEqual(result['pending_decision_count'], 1)
            self.assertTrue(any(x['type'] == 'decision' for x in result['blockers']))

    def test_structured_acceptance_is_authoritative_over_old_string(self):
        task = self.passed_task()
        task['current_fingerprint'] = 'current'
        task['acceptance'] = ['旧规则点击取消']
        task['stage_details'] = {'acceptance': {'items': [dict(id='A1', status='done', scenario='已核验', reviewer_kind='human', reviewed_revision='current', result_status='pass'), dict(id='A2', status='pending', scenario='名额调整', instruction='增加3人并查看候补')]}}
        action = summarize(task)['next_action']
        self.assertIn('名额调整', action)
        self.assertIn('增加3人并查看候补', action)
        self.assertNotIn('旧规则', action)
        self.assertNotIn('已核验', action)

    def test_normal_legacy_paths_and_reading_preference(self):
        task = self.passed_task()
        task['acceptance'] = ['旧格式人工核验']
        self.assertIn('旧格式人工核验', summarize(task)['next_action'])
        task['focus_stage'] = 'handoff'
        self.assertEqual(summarize(task)['focus_stage'], 'handoff')
        task['decisions'] = [dict(status='pending', question='规则？')]
        self.assertEqual(summarize(task)['step'], 'decide')
        task.pop('decisions')
        task['implementation'] = []
        self.assertEqual(summarize(task)['step'], 'implement')
        task['summary'] = ''
        self.assertEqual(summarize(task)['step'], 'understand')

    def test_verification_counts_are_exclusive_and_historical_is_not_current(self):
        task = self.passed_task()
        task['evidence'].extend([
            dict(id='fail', status='failed', freshness='当前', behavior_ids=['B1']),
            dict(id='blocked', status='blocked', freshness='当前'),
            dict(id='not_run', status='not_run', freshness='当前'),
            dict(id='old', status='passed', freshness='过期'),
            dict(id='unknown', status='legacy', freshness='未知')])
        value = summarize(task)['verification']
        self.assertEqual(value['missing_behavior_ids'], ['B1'])
        self.assertEqual(value['current_unresolved_evidence_ids'], ['fail', 'blocked', 'not_run'])
        self.assertEqual(sum(value['current_status_counts'].values()), 4)
        self.assertEqual(sum(value['historical_status_counts'].values()), 2)
        self.assertEqual(value['historical_evidence_count'], 2)
        self.assertEqual(value['historical_status_counts']['unknown'], 1)


class HumanVerificationTests(unittest.TestCase):
    def task(self, items, stage='acceptance'):
        task = CurrentActionTests().passed_task()
        task.update(current_fingerprint='current', focus_stage=stage, stage_details={stage: {'items': items}})
        return task

    def item(self, identity='A1', result='pass', revision='current', reviewer='human'):
        return dict(id=identity, status='done', scenario='scenario '+identity, instruction='execute '+identity,
                    result_status=result, reviewed_revision=revision, reviewer_kind=reviewer)

    def test_current_human_failure_or_blocked_returns_to_ai(self):
        for stage in ('acceptance', 'release'):
            for status in ('fail', 'blocked'):
                with self.subTest(stage=stage, status=status):
                    result=summarize(self.task([self.item(result=status)],stage))
                    self.assertEqual((result['step'],result['action_owner'],result['focus_stage']),('human_feedback','AI',stage))
                    self.assertTrue(any(b['type']=='human_feedback' and b['result_status']==status for b in result['blockers']))
                    self.assertNotIn('请亲自核验',result['next_action'])
                    self.assertEqual(result['stage_label'],'人工反馈 · 待 AI 处理')

    def test_historical_human_failure_is_pending_not_current_blocker(self):
        result=summarize(self.task([self.item(result='fail',revision='old')]))
        human=result['human_verification']
        self.assertEqual(result['step'],'accept')
        self.assertEqual(human['historical_ids'],['A1'])
        self.assertEqual(human['pending_ids'],['A1'])
        self.assertEqual(human['current_fail_ids'],[])
        self.assertEqual(result['blockers'],[])

    def test_ai_unknown_or_missing_version_never_signs(self):
        for reviewer,revision in [('ai','current'),('unknown','current'),('human',''),('human',None)]:
            with self.subTest(reviewer=reviewer,revision=revision):
                result=summarize(self.task([self.item(reviewer=reviewer,revision=revision)]))
                self.assertEqual(result['step'],'accept')
                self.assertEqual(result['human_verification']['pending_ids'],['A1'])
        task=self.task([self.item()]);task['current_fingerprint']=None
        self.assertEqual(summarize(task)['step'],'accept')

    def test_done_or_free_text_result_without_enum_does_not_pass(self):
        item=self.item();item.pop('result_status');item['result']='通过';item['actual']='符合预期'
        result=summarize(self.task([item]))
        self.assertEqual(result['step'],'accept')
        self.assertEqual(result['human_verification']['current_pass_ids'],[])
        self.assertEqual(result['human_verification']['pending_ids'],['A1'])

    def test_all_current_human_pass_stops_repeated_verification(self):
        for stage in ('acceptance','release'):
            result=summarize(self.task([self.item(),self.item('A2')],stage))
            self.assertEqual((result['step'],result['action_owner']),('human_reviewed','none'))
            self.assertTrue(result['human_verification']['all_current_passed'])
            self.assertEqual(result['human_verification']['current_pass_ids'],['A1','A2'])
            self.assertIn('不自动发布',result['next_action'])
            self.assertNotIn('请亲自核验',result['next_action'])
            self.assertNotIn('亲自核验关键路径',result['human_action'])
            self.assertEqual(result['focus_stage'],stage)
            self.assertEqual(result['stage_label'],'发布核验已记录' if stage=='release' else '人工核验已记录')

    def test_partial_pass_selects_first_not_current_human_pass(self):
        items=[self.item(),self.item('A2',result='not_checked'),self.item('A3')]
        result=summarize(self.task(items))
        self.assertIn('scenario A2',result['next_action'])
        self.assertNotIn('scenario A1',result['next_action'])
        self.assertEqual(result['human_verification']['pending_ids'],['A2'])

    def test_current_evidence_and_p1_precede_human_feedback(self):
        task=self.task([self.item(result='fail')])
        task['evidence'].append(dict(id='bad',status='failed',freshness='当前',behavior_ids=[]))
        self.assertEqual(summarize(task)['step'],'verify')
        task['evidence'].pop()
        task['stage_details']['review']={'items':[dict(id='R1',status='pending',severity='P1',finding='broken')]}
        self.assertEqual(summarize(task)['step'],'review')
        self.assertTrue(any(b['type']=='human_feedback' for b in summarize(task)['blockers']))

    def test_other_stage_current_human_failure_still_blocks(self):
        task=self.task([self.item()])
        task['stage_details']['release']={'items':[self.item('L1',result='blocked')]}
        result=summarize(task)
        self.assertEqual(result['step'],'human_feedback')
        self.assertEqual(result['human_verification']['by_stage']['release']['current_blocked_ids'],['L1'])


    def test_explicit_enum_does_not_require_done_status(self):
        item=self.item();item['status']='pending'
        self.assertEqual(summarize(self.task([item]))['step'],'human_reviewed')

    def test_passes_do_not_override_technical_gap_or_business_decision(self):
        task=self.task([self.item()]);task['evidence']=[]
        self.assertEqual(summarize(task)['step'],'verify')
        task=self.task([self.item()]);task['decisions']=[dict(id='D1',status='pending',question='scope?')]
        self.assertEqual(summarize(task)['step'],'decide')


class DelegatedAcceptanceTests(unittest.TestCase):
    task = HumanVerificationTests.task
    item = HumanVerificationTests.item
    def grant(self, revision='current', kind='acceptance'):
        return dict(kind=kind, revision=revision, source='用户：请按这些标准代替我验收', criteria='保存后刷新仍保持名额，异常不写入')

    def delegated(self, result='pass'):
        item=self.item(reviewer='ai', result=result)
        item['acceptance_delegation']=self.grant()
        return item

    def test_delegated_completion_preserves_ai_source_and_needs_no_new_human_action(self):
        task=self.task([self.item(), self.delegated()]); task['stage_details']['acceptance']['items'][1]['id']='A2'
        task['focus_stage']='review'
        result=summarize(task)
        self.assertEqual((result['step'],result['action_owner'],result['focus_stage']),('delegated_reviewed','none','acceptance'))
        self.assertEqual(result['human_verification']['current_pass_ids'],['A1'])
        self.assertEqual(result['human_verification']['pending_ids'],['A2'])
        self.assertEqual(result['acceptance_verification']['delegated_pass_ids'],['A2'])
        self.assertIn('当前无需人',result['next_action'])
        self.assertNotIn('是否放行',result['next_action'])
        self.assertNotIn('亲自核验',result['human_action'])

    def test_current_grant_routes_missing_or_old_result_to_ai(self):
        for status, revision in [('not_checked','current'), ('pass','old'), ('pass','')]:
            item=self.delegated(status);item['reviewed_revision']=revision
            result=summarize(self.task([item]))
            self.assertEqual((result['step'],result['action_owner']),('delegated_accept','AI'))
            self.assertEqual(result['stage_label'],'AI 按委托验收')

    def test_testing_only_incomplete_or_stale_grants_do_not_accept(self):
        for grant in [self.grant(kind='testing'), dict(source='请测试'), dict(self.grant(),criteria='')]:
            item=self.delegated();item['acceptance_delegation']=grant
            result=summarize(self.task([item]))
            self.assertEqual(result['step'],'accept')
            self.assertFalse(result['acceptance_verification']['all_current_passed'])

    def test_release_cannot_reuse_acceptance_delegation(self):
        item=self.delegated()
        result=summarize(self.task([item],stage='release'))
        self.assertEqual((result['step'],result['action_owner']),('accept','你'))

    def test_delegated_failures_and_current_evidence_still_need_ai_repair(self):
        for status in ('fail','blocked'):
            result=summarize(self.task([self.delegated(status)]))
            self.assertEqual((result['step'],result['action_owner']),('delegated_feedback','AI'))
            self.assertTrue(any(b['type']=='delegated_feedback' for b in result['blockers']))
        task=self.task([self.delegated()]);task['evidence'].append(dict(id='bad',status='failed',freshness='当前'))
        self.assertEqual(summarize(task)['step'],'verify')
        task['evidence'].pop();task['stage_details']['review']={'items':[dict(id='R1',severity='P1',status='pending')]}
        self.assertEqual(summarize(task)['step'],'review')
        task['stage_details'].pop('review');task['decisions']=[dict(id='D1',status='pending',question='需求取舍？')]
        self.assertEqual(summarize(task)['step'],'decide')

    def test_old_grant_routes_scope_check_to_ai_without_accepting_old_result(self):
        item=self.delegated();item['acceptance_delegation']=self.grant('old')
        result=summarize(self.task([item]))
        self.assertEqual((result['step'],result['action_owner']),('delegation_review','AI'))
        self.assertEqual(result['stage_label'],'核对既有验收委托')
        self.assertEqual(result['acceptance_verification']['current_pass_ids'],[])
        self.assertIn('同范围',result['next_action'])
        self.assertNotIn('请亲自核验',result['next_action'])

    def test_mixed_current_delegation_does_not_misreport_other_human_item_as_stale(self):
        item=self.delegated();item['id']='A1'
        result=summarize(self.task([item,self.item('A2',result='not_checked')]))
        self.assertEqual((result['step'],result['action_owner']),('accept','你'))
        self.assertIn('scenario A2',result['next_action'])
        self.assertNotIn('原验收委托未绑定',result['next_action'])

    def test_current_ai_failure_without_acceptance_authority_is_still_actionable(self):
        for status in ('fail','blocked'):
            for grant in (None, self.grant('old')):
                item=self.item(result=status,reviewer='ai')
                if grant:item['acceptance_delegation']=grant
                result=summarize(self.task([item]))
                self.assertEqual(result['action_owner'],'AI')
                self.assertTrue(any(b['type']=='ai_feedback' for b in result['blockers']))
                self.assertFalse(result['acceptance_verification']['all_current_passed'])

    def test_release_ai_failure_is_actionable_without_granting_release_authority(self):
        result=summarize(self.task([self.item(result='fail',reviewer='ai')],stage='release'))
        self.assertEqual((result['step'],result['action_owner'],result['focus_stage']),('ai_feedback','AI','release'))
        self.assertTrue(any(b['type']=='ai_feedback' for b in result['blockers']))
