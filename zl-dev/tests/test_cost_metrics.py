"""Reported usage windows and observed transport bytes are different measurements."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cost_metrics as metrics


def call(identity, name, data):
    return dict(type='assistant', message=dict(content=[dict(type='tool_use', id=identity, name=name, input=data)],
                                               usage={'input_tokens': 999999}))


def result(**kw):
    return dict(type='result', subtype='success', **kw)


class CostMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'events.jsonl'

    def analyze(self, events):
        self.path.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
        before = self.path.read_bytes()
        value = metrics.summarize(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(value['source']['sha256'], hashlib.sha256(before).hexdigest())
        return value

    def test_missing_result_is_partial_and_missing_usage_is_unknown(self):
        value = self.analyze([call('c', 'Read', {'file_path': '/never/read/this/file'})])
        self.assertEqual(value['trace_state'], 'partial_or_ambiguous')
        self.assertIsNone(value['reported'])
        self.assertIsNone(value['reads'][0]['reported_content_utf8_bytes'])
        value = self.analyze([dict(type='system', subtype='init'), result()])
        self.assertEqual(value['trace_state'], 'complete')
        self.assertIsNone(value['reported']['usage'])
        self.assertIsNone(value['reported']['total_cost_usd'])

    def test_result_only_keeps_usage_but_has_no_complete_zero_tool_claim(self):
        value = self.analyze([result(usage={'input_tokens': 123})])
        self.assertEqual(value['trace_state'], 'partial_or_ambiguous')
        self.assertFalse(value['observed_trace_coverage']['init_observed'])
        self.assertEqual(value['reported']['usage']['input_tokens'], 123)
        self.assertTrue(any(x['kind'] == 'missing_init_event' for x in value['anomalies']))

    def test_missing_receipts_and_orphan_results_are_incomplete_coverage(self):
        initial = dict(type='system', subtype='init')
        value = self.analyze([initial, call('a', 'Read', {'file_path': '/x'}), result()])
        self.assertEqual(value['trace_state'], 'partial_or_ambiguous')
        self.assertEqual(value['tools']['missing_receipts'], 1)
        self.assertEqual(value['observed_trace_coverage']['paired_unambiguous_calls'], 0)
        orphan = dict(type='user', message={'content': [dict(type='tool_result', tool_use_id='absent', content='x')]})
        value = self.analyze([initial, orphan, result()])
        self.assertEqual(value['trace_state'], 'partial_or_ambiguous')
        self.assertEqual(value['observed_trace_coverage']['orphan_results'], 1)
        value = self.analyze([initial, result()])
        self.assertEqual(value['trace_state'], 'complete')
        self.assertEqual(value['tools']['unambiguous_identified_tool_calls'], 0)

    def test_complete_error_result_is_not_task_success(self):
        value = self.analyze([dict(type='system', subtype='init'),
                              dict(type='result', subtype='error_max_turns', is_error=True, num_turns=15)])
        self.assertEqual(value['trace_state'], 'complete')
        self.assertEqual(value['reported']['subtype'], 'error_max_turns')
        self.assertTrue(value['reported']['is_error'])
        self.assertIn('never whether the task succeeded', value['notice'])

    def test_uses_final_result_window_without_summing_assistant_or_cumulative_values(self):
        usage = dict(input_tokens=12, output_tokens=3, cache_read_input_tokens=40,
                     cache_creation={'ephemeral_1h_input_tokens': 7})
        model = {'custom': dict(inputTokens=1000, outputTokens=2000, costBasis='unknown')}
        value = self.analyze([call('c', 'Read', {'file_path': '/x'}), result(
            usage=usage, modelUsage=model, model_usage_since_last_result={'custom': {'inputTokens': 12}},
            total_cost_usd=9.9, duration_ms=123)])
        self.assertEqual(value['reported']['usage'], usage)
        self.assertEqual(value['reported']['modelUsage'], model)
        self.assertEqual(value['reported']['total_cost_usd'], 9.9)
        self.assertEqual(value['reporting_scopes']['reported.modelUsage'], 'session_reported_may_be_cumulative')
        self.assertIn('not_a_bill', value['reporting_scopes']['reported.total_cost_usd'])
        self.assertNotIn('total_tokens', value)
        self.assertNotIn('999999', json.dumps(value))

    def test_identical_tool_replays_deduplicate_and_conflicting_ids_are_not_selected(self):
        first = call('a', 'Read', {'file_path': '/one'})
        value = self.analyze([first, first, result()])
        self.assertEqual(value['tools']['by_name']['Read'], 1)
        self.assertEqual(value['tools']['repeated_call_blocks'], 1)
        value = self.analyze([first, call('a', 'Write', {'file_path': '/two', 'content': 'secret'}), result()])
        self.assertEqual(value['tools']['conflicting_call_ids'], 1)
        self.assertEqual(value['trace_state'], 'partial_or_ambiguous')
        self.assertEqual(value['tools']['unambiguous_identified_tool_calls'], 0)
        self.assertEqual(value['writes'], [])
        self.assertTrue(any(a['kind'] == 'conflicting_tool_call_id' for a in value['anomalies']))

    def test_non_ascii_write_bytes_and_full_record_candidates_are_only_observed(self):
        content = json.dumps(dict(version=1, id='T', title='中文', kind='feature', project_path='/明确'), ensure_ascii=False)
        value = self.analyze([call('a', 'Write', {'file_path': '/must/not/be/created.json', 'content': content}), result()])
        expected = len(content.encode('utf-8'))
        self.assertGreater(expected, len(content))
        self.assertEqual(value['bytes_observed']['write_input_content_utf8_bytes'], expected)
        self.assertEqual(value['bytes_observed']['json_write_candidate_bytes']['task_record_candidate'], expected)
        self.assertFalse(value['writes'][0]['success_inferred'])
        self.assertNotIn(content, json.dumps(value, ensure_ascii=False))

    def test_tool_result_and_read_metadata_have_separate_non_doubled_byte_scopes(self):
        event = dict(type='user', message={'content': [dict(type='tool_result', tool_use_id='a', content='1→中文')]},
                     tool_use_result={'type': 'text', 'file': {'content': '中文', 'numLines': 1, 'totalLines': 100,
                                                             'startLine': 20, 'filePath': '/x'}})
        value = self.analyze([call('a', 'Read', {'file_path': '/x', 'offset': 20, 'limit': 1}), event, event, result()])
        self.assertEqual(value['bytes_observed']['read_reported_content_utf8_bytes'], 6)
        self.assertEqual(value['bytes_observed']['tool_result_content_utf8_bytes'], len('1→中文'.encode()))
        self.assertEqual(value['reads'][0]['requested_offset'], 20)
        self.assertEqual(value['reads'][0]['reported_total_lines'], 100)
        self.assertEqual(value['reads'][0]['reported_num_lines'], 1)

    def test_shell_wrappers_pipelines_and_redirects_are_not_counted_as_successful_plugin_calls(self):
        direct = 'python3 "/plugin path/reviewable.py" continue "/task path" --no-render'
        self.assertEqual(metrics.classify_bash(direct)['action'], 'continue')
        self.assertTrue(metrics.classify_bash(direct)['no_render_flag'])
        for command in [direct + ' | head', 'cd /x && ' + direct, 'rtk proxy ' + direct,
                        direct + ' 2>&1', 'env X=y ' + direct, 'python3 -c "print(1)"',
                        'python3 /x/reviewable.py render "$(touch /tmp/no)"']:
            with self.subTest(command=command):
                self.assertEqual(metrics.classify_bash(command)['classification'], 'ambiguous')
        value = self.analyze([call('a', 'Bash', {'command': direct}),
                              call('b', 'Bash', {'command': direct + ' | head'}), result()])
        self.assertEqual(value['tools']['plugin_invocation_syntax_counts'], {'reviewable.py:continue:no_render': 1})
        self.assertEqual(value['tools']['bash_classifications']['ambiguous'], 1)
        self.assertNotIn(direct, json.dumps(value))

    def test_bash_input_payload_is_counted_without_guessing_json_record_transport(self):
        command = 'python3 -c "print(\"中文\")"'
        data = {'command': command}
        value = self.analyze([call('b', 'Bash', data), result()])
        observed = value['bytes_observed']
        self.assertEqual(observed['bash_command_utf8_bytes'], len(command.encode()))
        self.assertEqual(observed['tool_input_compact_json_utf8_bytes_by_name']['Bash'],
                         len(metrics.canonical(data).encode()))
        self.assertEqual(observed['json_write_candidate_bytes'], {})
        self.assertIn('unknown rather than zero', observed['json_candidate_scope'])
        self.assertNotIn(command, json.dumps(value, ensure_ascii=False))

    def test_comments_and_expansion_cannot_fake_no_render_flags(self):
        command = 'python3 /p/reviewable.py continue /t'
        for suffix in [' # --no-render', ' *', ' ?no-render', ' [ab]', ' {a,b}', ' ~/task']:
            with self.subTest(suffix=suffix):
                self.assertEqual(metrics.classify_bash(command + suffix)['classification'], 'ambiguous')
        self.assertFalse(metrics.classify_bash(command)['no_render_flag'])
        self.assertTrue(metrics.classify_bash(command + ' --no-render')['no_render_flag'])

    def test_denials_and_error_receipts_keep_unknown_separate_from_zero(self):
        initial = dict(type='system', subtype='init')
        tool = call('x', 'Bash', {'command': 'false'})
        receipt = dict(type='user', message={'content': [dict(type='tool_result', tool_use_id='x',
                                                             content='failure', is_error=True)]})
        value = self.analyze([initial, tool, receipt, result(permission_denials=[{'command': 'secret'}])])
        self.assertEqual(value['reported']['permission_denials_count'], 1)
        self.assertEqual(value['tools']['error_result_count'], 1)
        self.assertNotIn('secret', json.dumps(value))
        value = self.analyze([initial, tool, result()])
        self.assertIsNone(value['reported']['permission_denials_count'])
        self.assertIsNone(value['tools']['error_result_count'])
        self.assertEqual(value['tools']['error_result_unknown_count'], 1)
        receipt['message']['content'][0].pop('is_error')
        value = self.analyze([initial, tool, receipt, result(permission_denials=[])])
        self.assertEqual(value['reported']['permission_denials_count'], 0)
        self.assertIsNone(value['tools']['error_result_count'])
        self.assertEqual(value['tools']['error_result_count_observed'], 0)

    def test_multiple_results_never_silently_select_a_usage_window(self):
        value = self.analyze([result(usage={'input_tokens': 1}), result(usage={'input_tokens': 99})])
        self.assertEqual(value['result_event_count'], 2)
        self.assertEqual(value['trace_state'], 'partial_or_ambiguous')
        self.assertIsNone(value['reported'])
        self.assertTrue(any(a['kind'] == 'multiple_result_events' for a in value['anomalies']))

    def test_malformed_and_oversized_lines_preserve_partial_metrics(self):
        self.path.write_bytes(b'{"type":"assistant"}\nnot-json\n' + b'X' * 100 + b'\n' +
                              json.dumps(result(usage={'output_tokens': 2})).encode() + b'\n')
        before = self.path.read_bytes()
        value = metrics.summarize(self.path, max_line_bytes=90)
        self.assertEqual(value['malformed_lines'], 1)
        self.assertEqual(value['oversized_lines'], 1)
        self.assertEqual(value['trace_state'], 'partial_or_ambiguous')
        self.assertEqual(value['reported']['usage']['output_tokens'], 2)
        self.assertEqual(value['source']['sha256'], hashlib.sha256(before).hexdigest())

    def test_init_context_sources_are_counted_and_fingerprinted_without_config_values(self):
        event = dict(type='system', subtype='init', model='custom', claude_code_version='test',
                     tools=['Read', 'Bash'], plugins=[{'name': 'zl-dev', 'path': '/private/plugin'}],
                     mcp_servers=[{'name': 'private-mcp', 'url': 'https://secret.example/?token=secret'}],
                     memory_paths=['/private/instructions'], apiKeySource='secret')
        value = self.analyze([event, result()])
        self.assertEqual(value['initialization']['plugins']['count'], 1)
        self.assertEqual(value['initialization']['tools']['count'], 2)
        self.assertEqual(value['initialization']['mcp_servers']['names'], ['private-mcp'])
        self.assertEqual(value['initialization']['memory_paths']['count'], 1)
        serialized = json.dumps(value)
        for text in ['https://secret.example', '/private/instructions', 'apiKeySource', '/private/plugin']:
            self.assertNotIn(text, serialized)

    def test_cli_only_writes_explicit_new_output_and_rejects_input_or_existing_target(self):
        self.analyze([result()])
        output = self.root / 'summary.json'
        command = [sys.executable, str(ROOT / 'scripts/cost_metrics.py'), 'summarize', str(self.path)]
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(output.exists())
        run = subprocess.run(command + ['--output', str(output)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        before = output.read_bytes()
        run = subprocess.run(command + ['--output', str(output)], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(output.read_bytes(), before)
        run = subprocess.run(command + ['--output', str(self.path)], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)


if __name__ == '__main__':
    unittest.main()
