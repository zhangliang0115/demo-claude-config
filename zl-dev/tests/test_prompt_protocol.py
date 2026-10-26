"""Runtime routing and result wording must not invent an acceptance gate."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import feature


class FeatureAcceptanceProtocolTests(unittest.TestCase):
    def test_free_text_acceptance_never_becomes_a_derived_delivery_verdict(self):
        data = dict(version=1, id='example', title='Existing result', phase='acceptance',
                    projects=[], contracts=[], allocations=[], integration=[
                        dict(result='全部通过，AI代验完成', reviewer='ai')])
        result = feature.assessed(data)
        self.assertFalse(result['assessment']['ready_for_integration'])
        self.assertEqual(set(result['assessment']), {'ready_for_integration', 'issues', 'delivery'})
        message = result['assessment']['delivery']
        for phrase in ['不代表交付完成', '不汇总整体接受', '不重复核验', '不据自由文本或子任务通过']:
            self.assertIn(phrase, message)
        self.assertNotIn('待人工核验', message)
        self.assertEqual(result['integration'], data['integration'])

    @unittest.skipUnless(shutil.which('node'), 'Node required to execute report routing')
    def test_actual_report_phase_action_preserves_existing_acceptance_and_authority(self):
        source = (ROOT / 'assets/feature.html').read_text()
        route = source[source.index('function phaseStage('):source.index('const tabs=')]
        program = '''
const vm=require('vm'); const input=JSON.parse(process.argv[1]);
const node={textContent:''}; const sandbox={f:input, $:()=>node};
vm.createContext(sandbox); vm.runInContext(input.source,sandbox);
process.stdout.write(JSON.stringify({action:node.textContent,stage:vm.runInContext('initialStage',sandbox)}));
'''
        for phase in ['acceptance', '验收', '人工核验', 'integration', 'testing', 'implementation', 'design']:
            with self.subTest(phase=phase):
                run = subprocess.run(['node', '-e', program, json.dumps(dict(phase=phase, source=route))],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                action = result['action']
                self.assertNotIn('现在请由人核验', action)
                if phase in ['acceptance', '验收', '人工核验']:
                    self.assertEqual(result['stage'], 'integration')
                    for phrase in ['明确受托 AI', '不重复核验', '不自动汇总整体接受', '不从自由文本或子任务通过', '不会自动批准或授予发布权限']:
                        self.assertIn(phrase, action)
                elif phase in ['integration', 'testing']:
                    self.assertIn('已有适用结果不重复执行', action)
                    self.assertNotIn('现在运行', action)
                else:
                    self.assertNotIn('请由人', action)


if __name__ == '__main__':
    unittest.main()
