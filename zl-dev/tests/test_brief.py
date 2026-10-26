"""Locate previews help a reader without becoming new task facts or losing scope."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import brief
import feature
import reviewable


class BriefTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.repo = self.root / 'repo'; self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'logic.py').write_text('total = 1\n', encoding='utf-8')
        self.task = self.root / 'task'; self.task.mkdir()
        self.data = dict(version=1, id='read-preview', title='订单客户筛选', kind='feature',
                         project_path=str(self.repo), summary='新增客户筛选；尚未实施。',
                         scope='只读需求记录，不运行项目。', why='减少手工筛选。',
                         behaviors=[], scenarios=[], evidence=[], decisions=[], implementation=[], acceptance=[])
        self.save()

    def save(self):
        (self.task / 'task.json').write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')

    def tree(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def test_task_locate_preserves_existing_results_facts_and_read_only_behavior(self):
        before_state = reviewable.snapshot(self.task)
        before_tree = self.tree()
        located = reviewable.locate(self.task)
        self.assertEqual(located['task_brief'], dict(
            id=self.data['id'], title=self.data['title'], kind='feature', project_path=str(self.repo),
            summary=self.data['summary'], scope=self.data['scope'], why=self.data['why'],
            truncated_fields=[], unavailable_fields=[]))
        self.assertEqual(located['task_revision'], before_state['task_revision'])
        self.assertEqual(located['assessment_revision'], before_state['assessment_revision'])
        self.assertEqual(located['fingerprint'], before_state['current_fingerprint'])
        self.assertEqual(located['primary_action'], before_state['workflow_summary']['primary_action'])
        self.assertEqual(located['report_state']['freshness'], 'missing')
        self.assertEqual(self.tree(), before_tree)
        self.assertEqual(reviewable.snapshot(self.task)['assessment_revision'], before_state['assessment_revision'])

    def test_feature_locate_explains_goal_source_without_modifying_feature_assessment(self):
        folder = self.root / 'feature'
        feature.init(folder, '整体订单导出', ['app=' + str(self.repo)], self.root)
        data = feature.load(folder); data['design']['goal'] = '跨项目支持按客户导出。'
        data['scope'] = '本轮设计。'; feature.save(folder, data)
        before = feature.snapshot(folder); files = self.tree()
        located = feature.locate(folder)
        view = located['feature_brief']
        self.assertEqual(view['goal'], data['design']['goal'])
        self.assertEqual(view['goal_source'], 'design.goal')
        self.assertEqual(view['workspace_path'], str(self.root))
        self.assertEqual(view['phase'], 'discovery')
        self.assertEqual(view['scope'], data['scope'])
        self.assertEqual(located['assessment'], before['assessment'])
        self.assertEqual(located['feature_revision'], before['feature_revision'])
        self.assertEqual(located['assessment_revision'], before['assessment_revision'])
        self.assertEqual(self.tree(), files)

    def test_long_text_marks_real_source_fields_and_keeps_identity_untruncated(self):
        data = dict(id='id-' + 'a' * 1500, kind='feature', project_path='/' + 'p' * 1500,
                    title='题' * 1300, summary='🙂中' * 700, scope='界' * 1201)
        original = copy.deepcopy(data)
        view = brief.task_brief(data)
        self.assertEqual(view['id'], data['id']); self.assertEqual(view['project_path'], data['project_path'])
        self.assertEqual(view['summary'], data['summary'][:brief.TEXT_LIMIT])
        self.assertEqual(set(view['truncated_fields']), {'title', 'summary', 'scope'})
        self.assertEqual(len(view['summary']), brief.TEXT_LIMIT)
        self.assertEqual(data, original)
        goal = brief.feature_brief(dict(design=dict(goal=' ' * 1250 + '真实目标'), summary='备用摘要'))
        self.assertEqual(goal['goal_source'], 'design.goal')
        self.assertIn('design.goal', goal['truncated_fields'])

    def test_nonstring_materials_are_explicitly_unavailable_and_not_dumped(self):
        data = dict(scope={'private': ['large'] * 2000}, summary=['not', 'plain'], why=False)
        view = brief.task_brief(data)
        self.assertEqual(view['scope'], ''); self.assertEqual(view['summary'], '')
        self.assertEqual(set(view['unavailable_fields']), {'scope', 'summary', 'why'})
        self.assertNotIn('private', json.dumps(view))
        feature_view = brief.feature_brief(dict(design=dict(goal={'not': 'a goal'}), summary='真实备用摘要'))
        self.assertEqual(feature_view['goal'], '真实备用摘要')
        self.assertEqual(feature_view['goal_source'], 'summary')
        self.assertEqual(feature_view['unavailable_fields'], ['design.goal'])

    def test_analysis_question_and_conclusion_are_distinct_bounded_static_materials(self):
        original = dict(kind='analysis', summary='原摘要', analysis=dict(
            question='金额从哪里来？', conclusion='据' * 1300))
        view = brief.task_brief(original)
        self.assertEqual(view['summary'], '原摘要')
        self.assertEqual(view['analysis_question'], '金额从哪里来？')
        self.assertEqual(len(view['analysis_conclusion']), brief.TEXT_LIMIT)
        self.assertIn('analysis.conclusion', view['truncated_fields'])
        self.assertEqual(original['analysis']['conclusion'], '据' * 1300)
        unavailable = brief.task_brief(dict(kind='analysis', analysis=dict(question=['unknown'])))
        self.assertEqual(unavailable['analysis_question'], '')
        self.assertIn('analysis.question', unavailable['unavailable_fields'])

    def test_missing_material_stays_unknown_and_returns_no_mutable_source_references(self):
        source = dict(summary='说明', scope=None, design={})
        task = brief.task_brief(source); aggregate = brief.feature_brief(source)
        self.assertEqual(task['id'], ''); self.assertEqual(task['scope'], '')
        self.assertEqual(aggregate['goal_source'], 'summary')
        self.assertEqual(aggregate['missing_fields'], ['design.goal'])
        empty = brief.feature_brief({})
        self.assertEqual(empty['goal'], ''); self.assertEqual(empty['goal_source'], '')
        task['truncated_fields'].append('summary'); aggregate['unavailable_fields'].append('design')
        self.assertEqual(source, dict(summary='说明', scope=None, design={}))
        self.assertEqual(brief.task_brief(source)['truncated_fields'], [])


if __name__ == '__main__':
    unittest.main()
