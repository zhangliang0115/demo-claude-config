"""The fake CLI in these tests never calls a model or represents a real evaluation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import evaluate_cost as runner


class CostRunnerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()

    def synthetic_prepared(self):
        output=self.root/'prepared';output.mkdir()
        plugin=output/'plugin';(plugin/'scripts').mkdir(parents=True)
        (plugin/'scripts/reviewable.py').write_text('# synthetic test file\n')
        cases=[]
        for i,(scenario,variant) in enumerate(runner.ORDER):
            folder=output/str(i);repo=folder/'repo';task=folder/'task'
            repo.mkdir(parents=True);task.mkdir();before=folder/'before';before.mkdir()
            (repo/'logic.py').write_text('total = 1\n')
            data=dict(summary='original',id=str(i),project_path=str(repo))
            (task/'task.json').write_text(json.dumps(data));(before/'task.json').write_text(json.dumps(data))
            (task/'report.html').write_text('synthetic report')
            cases.append(dict(id=str(i),scenario=scenario,variant=variant,folder=str(folder),repo=str(repo),
                              task=str(task),session_id='session-'+str(i),prompt='synthetic '+scenario,
                              git_state=dict(head='synthetic',status=''),
                              before={k:runner.stamp(p) for k,p in [
                                  ('source',repo/'logic.py'),('task',task/'task.json'),('report',task/'report.html')]}))
        variants={key:dict(plugin=str(plugin),commit='synthetic',version='synthetic') for key in runner.VARIANTS}
        runner.write_json(output/'prepared.json',dict(version=1,root=str(output),variants=variants,cases=cases))
        runner.write_json(output/'integrity.json',dict(version=1,files={str(p.relative_to(output)):runner.digest(p.read_bytes())
                          for p in runner.fixture_files(output)}))
        return output,cases,plugin

    def test_prepare_uses_pinned_archives_and_six_independent_sessions_without_model(self):
        result=runner.prepare(self.root/'actual')
        manifest=json.loads((Path(result['output'])/'prepared.json').read_text())
        self.assertEqual(result['model_calls'],0)
        self.assertEqual([(c['scenario'],c['variant']) for c in manifest['cases']],runner.ORDER)
        self.assertEqual(len({c['session_id'] for c in manifest['cases']}),6)
        self.assertEqual(len({c['repo'] for c in manifest['cases']}),6)
        self.assertEqual(manifest['variants']['v0160']['version'],'0.16.0')
        self.assertEqual(manifest['variants']['v0200']['version'],'0.20.0')
        for c in manifest['cases']:
            self.assertTrue((Path(c['task'])/'report.html').is_file())
            self.assertGreater(c['setup_wall_ms'],0)
            self.assertNotIn('--no-render',' '.join(' '.join(x['argv']) for x in c['controller_commands']))
            self.assertEqual((Path(c['repo'])/'CLAUDE.md').read_text(),runner.NOTICE)
        self.assertEqual(os.stat(result['output']).st_mode & 0o777,0o700)
        runner.validate_prepared(result['output'])
        with self.assertRaises(ValueError):runner.prepare(self.root/'actual')

    def test_explicit_confirmation_and_caps_are_required_before_any_process(self):
        with patch.object(runner.subprocess,'run') as launch:
            for count,timeout,turns in [(5,150,12),(6,151,12),(6,150,13)]:
                with self.assertRaises(ValueError):runner.run(self.root,count,timeout,turns)
            launch.assert_not_called()

    def test_tampered_or_extra_plugin_file_rejected_without_launch(self):
        output,_,plugin=self.synthetic_prepared()
        manifest=json.loads((output/'prepared.json').read_text())
        self.assertTrue(all(r['state']=='current' for r in runner.plugin_integrity(output,manifest).values()))
        (plugin/'extra.py').write_text('unexpected')
        self.assertTrue(all(r['state']=='changed' for r in runner.plugin_integrity(output,manifest).values()))
        with patch.object(runner.subprocess,'run') as launch:
            with self.assertRaisesRegex(ValueError,'Unexpected plugin file'):runner.run(output,6)
            launch.assert_not_called()
        (plugin/'extra.py').unlink()
        (plugin/'scripts/reviewable.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Prepared fixture changed'):runner.validate_prepared(output)

    def test_fake_cli_failure_retained_no_retry_and_outputs_never_overwritten(self):
        output,cases,plugin=self.synthetic_prepared();calls=[]
        def fake_execute(args,cwd=None):
            if args[-1]=='--version':return 'synthetic fake CLI'
            return json.dumps({'report_state':{'freshness':'current'}})
        def fake_cli(args,**kwargs):
            calls.append(args);index=len(calls)-1;case=cases[index]
            if case['scenario']=='summary':
                path=Path(case['task'])/'task.json';data=json.loads(path.read_text());data['summary']+=runner.ADDITION;path.write_text(json.dumps(data))
            events=[dict(type='system',subtype='init',plugins=[dict(name='zl-dev',path=str(plugin),version='synthetic')]),
                    dict(type='result',subtype='error_max_turns' if index==0 else 'success',num_turns=13)]
            kwargs['stdout'].write('\n'.join(json.dumps(e) for e in events)+'\n');kwargs['stdout'].flush()
            return subprocess.CompletedProcess(args,1 if index==0 else 0)
        with patch.object(runner,'execute',fake_execute),patch.object(runner,'git_state',return_value=dict(head='synthetic',status='')),patch.object(runner.subprocess,'run',fake_cli):
            result=runner.run(output,6)
        self.assertEqual(len(calls),6);self.assertEqual(result['successful_cli_results'],5)
        self.assertTrue(all('--resume' not in c for c in calls))
        data=json.loads((output/'outcomes.json').read_text())
        self.assertEqual(data['cases'][0]['exit_code'],1)
        self.assertEqual(data['cases'][0]['observed_num_turns'],13)
        self.assertTrue(data['complete'])
        self.assertTrue(all(c['checks']['summary_expectation_met'] for c in data['cases']))
        self.assertTrue(all(c['checks']['repo_git_state_unchanged'] for c in data['cases']))
        self.assertTrue(all(c['checks']['expected_plugin_loaded'] for c in data['cases']))
        self.assertTrue(all(r['state']=='current' for c in data['cases'] for r in c['plugin_integrity'].values()))
        with patch.object(runner,'execute',fake_execute),patch.object(runner,'git_state',return_value=dict(head='different',status=' M logic.py\n')):
            duplicate=dict(type='system',subtype='init',plugins=[dict(name='zl-dev',path=str(plugin),version='synthetic')]*2)
            checked=runner.outcome(cases[0],plugin,[duplicate],'synthetic')
            self.assertFalse(checked['checks']['expected_plugin_loaded'])
            self.assertFalse(checked['checks']['repo_git_state_unchanged'])
            wrong=dict(type='system',subtype='init',plugins=[dict(name='zl-dev',path=str(plugin),version='other')])
            self.assertFalse(runner.outcome(cases[0],plugin,[wrong],'synthetic')['checks']['expected_plugin_loaded'])
        raw=(Path(cases[0]['folder'])/'events.jsonl').read_bytes()
        with patch.object(runner.subprocess,'run') as launch:
            with self.assertRaises(ValueError):runner.run(output,6)
            launch.assert_not_called()
        self.assertEqual(raw,(Path(cases[0]['folder'])/'events.jsonl').read_bytes())
        self.assertEqual((Path(cases[0]['folder'])/'events.jsonl').stat().st_mode & 0o777,0o600)

    def test_partial_and_malformed_events_are_preserved_as_missing_result(self):
        path=self.root/'events.jsonl';path.write_text('{"type":"assistant"}\nnot-json\n')
        events,errors=runner.read_events(path)
        self.assertEqual(errors,[2]);self.assertEqual(len(events),1)
        self.assertFalse(any(e.get('type')=='result' for e in events))


if __name__=='__main__':unittest.main()
