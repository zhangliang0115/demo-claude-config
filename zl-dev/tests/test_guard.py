"""The PreToolUse guard denies direct rewrites of CLI-owned records only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'scripts' / 'guard.py'


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.task = self.home / '.claude/zl-dev/projects/p-1/tasks/t1'
        self.task.mkdir(parents=True)

    def run_guard(self, tool, **params):
        env = dict(os.environ, HOME=str(self.home))
        payload = json.dumps(dict(tool_name=tool, tool_input=params))
        return subprocess.run([sys.executable, str(GUARD)], input=payload, text=True, capture_output=True, env=env)

    def assertDenied(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertIn('--expect-revision', result.stderr)

    def test_write_to_task_json_is_denied_with_cli_advice(self):
        self.assertDenied(self.run_guard('Write', file_path=str(self.task / 'task.json'), content='{}'))

    def test_edit_of_report_html_is_denied(self):
        self.assertDenied(self.run_guard('Edit', file_path=str(self.task / 'report.html'), old_string='a', new_string='b'))

    def test_session_context_files_are_protected(self):
        target = self.home / '.claude/zl-dev/contexts/claude-code/abc/p.json'
        self.assertDenied(self.run_guard('Write', file_path=str(target), content='{}'))

    def test_temp_json_and_business_files_are_allowed(self):
        self.assertEqual(self.run_guard('Write', file_path='/tmp/zl-dev-update.json', content='{}').returncode, 0)
        self.assertEqual(self.run_guard('Write', file_path=str(self.home / 'repo/task.json'), content='{}').returncode, 0)
        self.assertEqual(self.run_guard('Write', file_path=str(self.task / 'HANDOFF.md'), content='x').returncode, 0)

    def test_shell_rewrite_of_task_json_is_denied(self):
        for command in [f'cp /tmp/new.json {self.task}/task.json',
                        f'cat x > ~/.claude/zl-dev/projects/p/tasks/t/task.json',
                        f"python3 -c \"open('{self.task}/task.json','w')\"",
                        f'mv /tmp/new.json "{self.task}/feature.json"',
                        f'sed -i "" s/a/b/ {self.task}/task.json',
                        f'echo x | tee {self.task}/report.html']:
            with self.subTest(command=command):
                self.assertDenied(self.run_guard('Bash', command=command))

    def test_cli_and_read_commands_are_allowed(self):
        for command in [f'python3 "$CLAUDE_PLUGIN_ROOT/scripts/reviewable.py" update {self.task} --from-file /tmp/a.json --expect-revision r1',
                        f'cat ~/.claude/zl-dev/projects/p/tasks/t/task.json',
                        f'python3 scripts/reviewable.py locate {self.task} > /tmp/out.json',
                        'ls ~/.claude/zl-dev/projects',
                        f'cp {self.task}/task.json /tmp/zl-edit.json',
                        f'cat {self.task}/task.json > /tmp/zl-edit.json',
                        f'jq . {self.task}/task.json | tee /tmp/zl-view.json']:
            with self.subTest(command=command):
                self.assertEqual(self.run_guard('Bash', command=command).returncode, 0)

    def test_malformed_input_never_blocks_host(self):
        result = subprocess.run([sys.executable, str(GUARD)], input='not json', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
