"""Model evaluation runner: fixtures, explicit run count and per-scenario checks without a real model."""
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import evaluate_models as runner

FAKE_CLAUDE = '''#!/bin/sh
if [ "$1" = "--version" ]; then echo "fake 0"; exit 0; fi
echo '{"type":"system","subtype":"init","plugins":[]}'
echo '{"type":"result","subtype":"success","num_turns":2,"total_cost_usd":0.01,"usage":{}}'
'''


FAKE_CLAUDE_PY = '''import sys
if sys.argv[1:2] == ["--version"]:
    print("fake 0"); sys.exit(0)
print('{"type":"system","subtype":"init","plugins":[]}')
print('{"type":"result","subtype":"success","num_turns":2,"total_cost_usd":0.01,"usage":{}}')
'''


class ModelRunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        if os.name == 'nt':
            script = self.root / 'fake_claude.py'
            script.write_text(FAKE_CLAUDE_PY, encoding='utf-8')
            self.fake = self.root / 'claude.cmd'
            self.fake.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding='utf-8')
        else:
            self.fake = self.root / 'claude'
            self.fake.write_text(FAKE_CLAUDE, encoding='utf-8')
            self.fake.chmod(self.fake.stat().st_mode | stat.S_IEXEC)

    def test_prepare_builds_one_isolated_case_per_model_scenario_repeat_without_model_calls(self):
        result = runner.prepare(self.root / 'out', ['m1'], 2)
        manifest = json.loads((self.root / 'out/prepared.json').read_text(encoding='utf-8'))
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(len(manifest['cases']), len(runner.SCENARIOS) * 2)
        self.assertEqual(len({c['repo'] for c in manifest['cases']}), len(manifest['cases']))
        analysis = [c for c in manifest['cases'] if c['scenario'] == 'analysis']
        self.assertTrue(all(c['before']['task'] is None for c in analysis))
        self.assertTrue(all(Path(c['task'], 'report.html').is_file() for c in manifest['cases'] if c['scenario'] != 'analysis'))

    def test_extra_scenarios_seed_session_and_clean_up_activity(self):
        home = self.root / 'home'; home.mkdir()
        with patch.dict(os.environ, HOME=str(home)), patch.object(Path, 'home', return_value=home):
            runner.prepare(self.root / 'x', ['m1'], 1, ('multisession', 'execcontext'))
            manifest = json.loads((self.root / 'x/prepared.json').read_text(encoding='utf-8'))
            multi = next(c for c in manifest['cases'] if c['scenario'] == 'multisession')
            self.assertTrue(Path(multi['other_task'], 'task.json').is_file())
            self.assertNotIn(multi['task'], multi['prompt'])
            runner.run(self.root / 'x', 2, 30, 5, str(self.fake))
            rows = {r['scenario']: r for r in json.loads((self.root / 'x/outcomes.json').read_text(encoding='utf-8'))['cases']}
            self.assertFalse(rows['multisession']['checks']['resumed_own_task'])  # 假 CLI 无答复，必须如实失败
            self.assertFalse(rows['execcontext']['checks']['conflict_reported'])
            registry = json.loads((home / '.claude/zl-dev/executions/activities.json').read_text(encoding='utf-8'))
            self.assertEqual(registry['active'], [])
            self.assertEqual(len(registry['history']), 1)

    def test_run_requires_exact_confirmation_and_bounded_limits(self):
        runner.prepare(self.root / 'out', ['m1'], 1)
        for count, timeout, turns in [(4, 150, 12), (5, 181, 12), (5, 150, 16)]:
            with self.assertRaises(ValueError):
                runner.run(self.root / 'out', count, timeout, turns, str(self.fake))
        self.assertFalse((self.root / 'out/run-started.json').exists())

    def test_run_records_outcomes_and_refuses_second_run(self):
        runner.prepare(self.root / 'out', ['m1'], 1)
        summary = runner.run(self.root / 'out', 5, 30, 5, str(self.fake))
        self.assertEqual(summary['total_runs'], 5)
        rows = {r['scenario']: r for r in json.loads((self.root / 'out/outcomes.json').read_text(encoding='utf-8'))['cases']}
        self.assertTrue(rows['progress']['passed'])
        self.assertTrue(rows['analysis']['passed'])
        self.assertFalse(rows['summary']['checks']['summary_appended'])  # 假 CLI 不写入，必须如实失败
        self.assertFalse(rows['handoff']['checks']['handoff_exported'])
        with self.assertRaises(ValueError):
            runner.run(self.root / 'out', 5, 30, 5, str(self.fake))


if __name__ == '__main__':
    unittest.main()
