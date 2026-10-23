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
