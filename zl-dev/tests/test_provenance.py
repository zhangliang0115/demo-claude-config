import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reviewable as api
import verification
from provenance import START, END, read_payload


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'app.py').write_text('capacity = 3')
        self.folder = self.root / 'task'
        self.folder.mkdir()
        self.data = dict(version=1, id='t', title='名额调整', kind='feature', project_path=str(self.repo),
            stage='存在P1待修复', summary='调整名额并晋升候补',
            behaviors=[dict(id='B1', after='扩容3人')], implementation=[dict(title='事务')], evidence=[])
        self.save()
        self.data['evidence'] = [dict(id='E1', status='passed', revision=api.fingerprint(self.folder), behavior_ids=['B1'])]
        self.save()

    def save(self):
        (self.folder / 'task.json').write_text(json.dumps(self.data))

    def tree(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

    def test_report_metadata_and_source_staleness_are_readonly(self):
        api.render(self.folder)
        initial = api.locate(self.folder)
        self.assertEqual(initial['report_state']['freshness'], 'current')
        self.assertEqual(initial['report'], initial['report_state']['path'])
        self.data['summary'] = '只修改解释文字'
        old_fingerprint = api.fingerprint(self.folder)
        self.save()
        self.assertEqual(api.fingerprint(self.folder), old_fingerprint)
        before = self.tree()
        self.assertEqual(api.locate(self.folder)['report_state']['freshness'], 'stale')
        self.assertEqual(before, self.tree())
        api.render(self.folder)
        (self.repo / 'app.py').write_text('capacity = 1')
        self.assertEqual(api.report_state(self.folder)['freshness'], 'stale')

    def test_semantic_change_cannot_export_old_html_as_current(self):
        api.render(self.folder)
        self.data['behaviors'][0]['after'] = '扩容1人'
        self.save()
        api.export_handoff(self.folder)
        state = api.locate(self.folder)
        self.assertEqual(state['step'], 'verify')
        self.assertEqual(state['report_state']['freshness'], 'stale')
        self.assertEqual(state['handoff']['freshness'], 'current')
        handoff = (self.folder / 'HANDOFF.md').read_text()
        self.assertIn('报告非 current 时不得把旧 HTML 当作当前交付', handoff)
        self.assertIn('"freshness": "stale"', handoff)

    def test_receipt_log_change_invalidates_report_and_handoff_without_task_change(self):
        result, code = verification.execute(self.folder, self.repo, 'unittest', ['B1'],
            [sys.executable, '-c', 'import unittest\nclass T(unittest.TestCase):\n def test_one(self): self.assertTrue(True)\nunittest.main()'])
        self.assertEqual(code, 0, result)
        api.render(self.folder)
        api.export_handoff(self.folder)
        before_raw = (self.folder / 'task.json').read_bytes()
        fingerprint = api.fingerprint(self.folder)
        self.assertEqual(api.locate(self.folder)['report_state']['freshness'], 'current')
        (Path(result['receipt']).parent / 'stderr.log').write_text('tampered after render')
        before = self.tree()
        state = api.locate(self.folder)
        self.assertEqual(state['report_state']['freshness'], 'stale')
        self.assertEqual(state['handoff']['freshness'], 'stale')
        self.assertEqual(state['step'], 'verify')
        self.assertEqual(before_raw, (self.folder / 'task.json').read_bytes())
        self.assertEqual(fingerprint, api.fingerprint(self.folder))
        self.assertEqual(before, self.tree())

    def test_legacy_broken_and_missing_report_never_crash_or_write(self):
        self.assertEqual(api.report_state(self.folder)['freshness'], 'missing')
        for text in ['<html>old report</html>', '<script id="task-data">[]</script>',
                     '<script id="task-data">{broken</script>',
                     '<script id="task-data">{"id":"legacy"}</script>']:
            (self.folder / 'report.html').write_text(text)
            before = self.tree()
            self.assertEqual(api.report_state(self.folder)['freshness'], 'unknown')
            self.assertEqual(before, self.tree())

    def test_edited_embedded_snapshot_or_identity_is_not_current(self):
        report = api.render(self.folder)
        text = report.read_text()
        report.write_text(text.replace('调整名额并晋升候补', '伪造新说明'))
        self.assertEqual(api.report_state(self.folder)['freshness'], 'stale')
        report.write_text(text)
        payload = read_payload(text)
        self.assertEqual(payload['task_revision'], api.task_revision((self.folder / 'task.json').read_bytes()))
        self.assertEqual(payload['provenance']['project_path'], str(self.repo))

    def test_report_copied_versions_must_match_provenance(self):
        import re
        report = api.render(self.folder)
        original = report.read_text()
        payload = read_payload(original)
        self.assertEqual(api.report_state(self.folder)['freshness'], 'current')
        for field in ('task_revision', 'assessment_revision', 'current_fingerprint'):
            with self.subTest(field=field):
                altered = dict(payload)
                altered[field] = '0' * 64
                embedded = json.dumps(altered, ensure_ascii=False)
                report.write_text(re.sub(r'(<script id="task-data" type="application/json">).*?(</script>)',
                    lambda match: match[1] + embedded + match[2], original, count=1, flags=re.S))
                before = self.tree()
                result = api.report_state(self.folder)
                self.assertEqual(result['freshness'], 'stale')
                self.assertIn('复制版本与来源不一致', result['reason'])
                self.assertEqual(before, self.tree())
        report.write_text(original)
        self.assertEqual(api.report_state(self.folder)['freshness'], 'current')

    def test_report_without_top_level_copy_versions_is_unknown(self):
        import re
        report = api.render(self.folder)
        original = report.read_text()
        payload = read_payload(original)
        for field in ('task_revision', 'assessment_revision', 'current_fingerprint'):
            with self.subTest(field=field):
                legacy = dict(payload)
                del legacy[field]
                embedded = json.dumps(legacy, ensure_ascii=False)
                report.write_text(re.sub(r'(<script id="task-data" type="application/json">).*?(</script>)',
                    lambda match: match[1] + embedded + match[2], original, count=1, flags=re.S))
                before = self.tree()
                self.assertEqual(api.report_state(self.folder)['freshness'], 'unknown')
                self.assertEqual(before, self.tree())

    def test_handoff_preserves_human_text_and_backs_up_legacy_once(self):
        handoff = self.folder / 'HANDOFF.md'
        legacy = b'# Old handoff\r\nPort: 18921\r\n'
        handoff.write_bytes(legacy)
        api.export_handoff(self.folder)
        backups = list(self.folder.glob('HANDOFF.legacy-*.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), legacy)
        self.assertIn(backups[0].name, handoff.read_text())
        handoff.write_text('人工前言：先核对负责人\n' + handoff.read_text() + '\n人工后记：停止条件不能省略\n')
        api.export_handoff(self.folder)
        after = handoff.read_text()
        self.assertTrue(after.startswith('人工前言：先核对负责人\n'))
        self.assertTrue(after.endswith('\n人工后记：停止条件不能省略\n'))
        self.assertIn(backups[0].name, after)
        self.assertEqual(len(list(self.folder.glob('HANDOFF.legacy-*.md'))), 1)
        self.assertEqual(after.count(START), 1)
        self.assertEqual(after.count(END), 1)
        self.assertEqual(api.locate(self.folder)['handoff']['freshness'], 'current')

    def test_handoff_uses_derived_stage_action_and_blockers(self):
        handoff = api.export_handoff(self.folder).read_text()
        self.assertIn('## 当前状态\n待人工核验\n', handoff)
        self.assertIn('记录原文：存在P1待修复', handoff)
        self.data['stage_details'] = {'review': {'items': [dict(id='R1', status='pending', severity='P0', finding='重复晋升')]}}
        self.save()
        handoff = api.export_handoff(self.folder).read_text()
        self.assertIn('## 当前状态\n审查中\n', handoff)
        self.assertIn('重复晋升', handoff)
        self.assertIn('"owner": "AI"', handoff)

    def test_cli_status_report_provenance_is_readonly_and_continue_is_consistent(self):
        api.render(self.folder)
        self.data['summary'] = '元数据已更新但未render'
        self.save()
        before = self.tree()
        command = [sys.executable, str(Path(api.__file__)), 'status', str(self.folder), '--project', str(self.repo)]
        result = subprocess.run(command, text=True, capture_output=True, check=True)
        status = json.loads(result.stdout)
        self.assertEqual(status['report_state']['freshness'], 'stale')
        self.assertEqual(status['report_state'], api.locate(self.folder)['report_state'])
        self.assertEqual(before, self.tree())
        command[2] = 'continue'
        result = subprocess.run(command, text=True, capture_output=True, check=True)
        continued = json.loads(result.stdout)
        payload = read_payload((self.folder / 'report.html').read_text())
        self.assertEqual(continued['report_state']['freshness'], 'current')
        self.assertEqual(continued['task_revision'], payload['task_revision'])
        self.assertEqual(continued['next_action'], payload['workflow_summary']['next_action'])

    def test_all_public_resume_commands_expose_comparable_revision_fields(self):
        api.render(self.folder)
        expected = read_payload((self.folder / 'report.html').read_text())
        located = api.locate(self.folder)
        for key in ('task_revision', 'assessment_revision'):
            self.assertEqual(located[key], expected[key])
        for command in ('locate', 'status', 'continue'):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(Path(api.__file__)), command,
                    str(self.folder), '--project', str(self.repo)], text=True, capture_output=True, check=True)
                output = json.loads(result.stdout)
                payload = read_payload((self.folder / 'report.html').read_text())
                for key in ('task_revision', 'assessment_revision'):
                    self.assertEqual(output[key], payload[key])
                    self.assertEqual(output[key], expected[key])

    def test_failed_atomic_artifact_replace_preserves_report_and_human_handoff(self):
        report = api.render(self.folder)
        handoff = api.export_handoff(self.folder)
        handoff.write_text(handoff.read_text() + '\n人工补充：停止条件必须保留\n')
        report_bytes, handoff_bytes = report.read_bytes(), handoff.read_bytes()
        self.data['summary'] = '待刷新新内容'
        self.save()
        for operation, target, expected in [(api.render, report, report_bytes), (api.export_handoff, handoff, handoff_bytes)]:
            with self.subTest(operation=operation.__name__):
                with patch('os.replace', side_effect=PermissionError('injected replacement failure')):
                    with self.assertRaises(PermissionError):
                        operation(self.folder)
                self.assertEqual(target.read_bytes(), expected)
                self.assertEqual(list(self.folder.glob('.zl-dev-*.tmp')), [])

    def test_release_contract_change_makes_old_human_pass_historical(self):
        item = dict(id='RL1', status='done', check='灰度发布', environment='预生产',
                    metric='错误率小于1%', stop='错误率超1%停止', rollback='回滚到v1',
                    reviewer_kind='human', result_status='pass')
        self.data.update(focus_stage='release', stage_details={'release': {'items': [item]}})
        self.save()
        original = api.fingerprint(self.folder)
        item['reviewed_revision'] = original
        self.data['evidence'][0]['revision'] = original
        self.save()
        self.assertEqual(api.snapshot(self.folder)['workflow_summary']['step'], 'human_reviewed')
        for field in ('id', 'check', 'environment', 'metric', 'stop', 'rollback'):
            with self.subTest(field=field):
                old = item[field]
                item[field] = old + '（已变更）'
                self.save()
                state = api.snapshot(self.folder)
                self.assertNotEqual(state['current_fingerprint'], original)
                self.assertNotEqual(state['workflow_summary']['step'], 'human_reviewed')
                human = state['workflow_summary']['human_verification']
                self.assertEqual(human['historical_ids'], [item['id']])
                self.assertEqual(human['current_pass_ids'], [])
                item[field] = old

    def test_release_result_and_authorization_records_do_not_invalidate_behavior(self):
        item = dict(id='RL1', status='pending', check='灰度发布', environment='预生产',
                    metric='错误率小于1%', stop='超阈值停止', rollback='回滚v1')
        self.data['stage_details'] = {'release': {'items': [item]}}
        self.save()
        before = api.fingerprint(self.folder)
        item.update(status='done', authorization='负责人已授权本次灰度', actual='观察窗口无异常',
                    reviewer_kind='human', reviewed_revision=before, result_status='pass')
        self.save()
        api.validate(self.data)
        self.assertEqual(api.fingerprint(self.folder), before)

    def test_empty_release_preserves_existing_contract_shape(self):
        before = api.semantic_contract(self.data)
        self.assertNotIn('release', before['stage_contract'])
        self.data['stage_details'] = {'release': {'items': []}}
        self.assertEqual(api.semantic_contract(self.data), before)
        self.data['stage_details']['release']['summary'] = '发布尚未安排'
        self.assertEqual(api.semantic_contract(self.data), before)

    def test_acceptance_delegation_schema_and_provenance(self):
        item = dict(id='AC1', status='pending', scenario='扩容')
        self.data['stage_details'] = {'acceptance': {'items': [item]}}
        contract = api.semantic_contract(self.data)
        grant = dict(kind='acceptance', revision='current', source='用户原话：按标准代我验收', criteria='保存后刷新保持')
        item['acceptance_delegation'] = grant
        api.validate(self.data)
        self.assertEqual(api.semantic_contract(self.data), contract)
        for invalid in [None, {}, dict(grant, kind='testing'), dict(grant, source=' '), dict(grant, revision=''), dict(grant, criteria=[]), dict(grant, release=True)]:
            with self.subTest(invalid=invalid):
                item['acceptance_delegation'] = invalid
                with self.assertRaises(ValueError):
                    api.validate(self.data)
        item['acceptance_delegation'] = grant
        self.data['stage_details'] = {'release': {'items': [item]}}
        with self.assertRaises(ValueError):
            api.validate(self.data)

    def test_optional_result_status_is_validated_and_does_not_change_semantics(self):
        self.data['stage_details'] = {'acceptance': {'items': [dict(id='AC1', status='pending', scenario='扩容')]}}
        contract = api.semantic_contract(self.data)
        for status in ['pass', 'fail', 'blocked', 'not_checked']:
            self.data['stage_details']['acceptance']['items'][0]['result_status'] = status
            api.validate(self.data)
            self.assertEqual(api.semantic_contract(self.data), contract)
        for invalid in ['approved', [], None, True]:
            self.data['stage_details']['acceptance']['items'][0]['result_status'] = invalid
            with self.assertRaises(ValueError):
                api.validate(self.data)
