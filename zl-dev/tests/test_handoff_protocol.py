"""Generated handoffs follow the same lightweight protocol as the live prompts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analysis
import reviewable as api
from provenance import START, END


class HandoffProtocolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'price.py').write_text('def quote(price, quantity):\n    return price * quantity\n')
        self.folder = self.root / 'task'
        self.folder.mkdir()

    def save(self, data):
        (self.folder / 'task.json').write_text(json.dumps(data))

    def base(self, kind):
        return dict(version=1, id='t', title='Explain quotation', kind=kind,
                    project_path=str(self.repo), stage='pending', summary='报价说明',
                    behaviors=[], implementation=[], evidence=[])

    def test_analysis_handoff_contains_current_answer_and_source_without_development_stage(self):
        data = self.base('analysis')
        data.update(focus_stage='analysis', scope='只解释本地报价函数', analysis=dict(
            mode='business_logic', question='实付金额如何计算？', conclusion='单价乘数量。',
            sources=[analysis.source(self.repo, 'price.py')],
            steps=[dict(id='ST1', title='计算', description='单价乘数量', source_ids=['S1'])],
            rules=[], mappings=[], findings=[], gaps=[], project_paths=[]))
        self.save(data)
        before = (self.folder / 'task.json').read_bytes()
        handoff = api.export_handoff(self.folder).read_text()
        self.assertEqual((self.folder / 'task.json').read_bytes(), before)
        for phrase in ['实付金额如何计算？', '单价乘数量。', '只解释本地报价函数', str(self.repo / 'price.py') + ':1–2', '静态源码依据', '不是运行或业务验收证明']:
            self.assertIn(phrase, handoff)
        self.assertNotIn('记录原文：pending', handoff)
        self.assertNotIn('完成后更新 task.json，render', handoff)
        self.assertNotIn('核对后显式 render', handoff)
        self.assertIn('仅在本轮操作依赖运行环境时检查环境', handoff)
        self.assertIn('缺失 HTML 不阻塞', handoff)
        self.assertFalse((self.folder / 'report.html').exists())
        self.assertEqual(api.locate(self.folder)['handoff']['freshness'], 'current')

    def test_feature_handoff_keeps_provenance_and_human_notes_without_forcing_updates(self):
        data = self.base('feature')
        data['stage'] = 'existing note'
        self.save(data)
        api.export_handoff(self.folder)
        target = self.folder / 'HANDOFF.md'
        target.write_text('User note before\n' + target.read_text() + '\nUser note after\n')
        facts = (self.folder / 'task.json').read_bytes()
        text = api.export_handoff(self.folder).read_text()
        self.assertTrue(text.startswith('User note before\n'))
        self.assertTrue(text.endswith('\nUser note after\n'))
        self.assertEqual(text.count(START), 1)
        self.assertEqual(text.count(END), 1)
        self.assertIn('记录原文：existing note', text)
        self.assertIn('普通解释或仅导出无需修改任务事实', text)
        self.assertIn('task_revision: ', text)
        self.assertIn('assessment_revision: ', text)
        self.assertEqual((self.folder / 'task.json').read_bytes(), facts)
        self.assertEqual(api.locate(self.folder)['handoff']['freshness'], 'current')

    def test_analysis_source_excerpt_is_bounded_and_keeps_unknown_source_notice(self):
        data = self.base('analysis')
        sources = [analysis.source(self.repo, 'price.py', identity='S' + str(i)) for i in range(13)]
        data.update(focus_stage='analysis', analysis=dict(mode='data_flow', question='来源？',
            conclusion='此范围内是price参数。', project_paths=[], sources=sources,
            steps=[dict(id='ST1', title='入口', description='读取参数', source_ids=['S0'])],
            rules=[], mappings=[], findings=[], gaps=[]))
        self.save(data)
        text = api.export_handoff(self.folder).read_text()
        self.assertIn('- S11：', text)
        self.assertNotIn('- S12：', text)
        self.assertIn('其余 1 项来源见 task.json', text)
        self.assertIn('不证明解释正确', text)


if __name__ == '__main__':
    unittest.main()
