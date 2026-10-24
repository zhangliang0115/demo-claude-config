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
        task['acceptance'] = ['旧规则点击取消']
        task['stage_details'] = {'acceptance': {'items': [dict(id='A1', status='done', scenario='已核验'), dict(id='A2', status='pending', scenario='名额调整', instruction='增加3人并查看候补')]}}
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
