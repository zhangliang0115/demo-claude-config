#!/usr/bin/env python3
"""Repeat fixed plugin scenarios on named Claude models; record raw outcomes, never business code.

prepare 只建立隔离夹具（不调用模型）；run 需显式 --confirm-runs 等于计划次数，按顺序逐个全新会话执行，
不重试、不覆盖已有结果。summarize 汇总已有 outcome，不再调用模型。
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import cost_metrics
from evaluate_cost import NOTICE, execute, git_state, stamp, write_json

PLUGIN = Path(__file__).resolve().parents[1]
ADDITION = '补充：本轮只记录说明，不改变验收标准。'
SCENARIOS = ('progress', 'summary', 'report', 'handoff', 'analysis')
MAX_TIMEOUT, MAX_TURNS, MAX_RUNS = 180, 15, 40


def prompt_for(scenario, task, repo, update):
    start = f'/zl-dev:go 已有任务 {task}，项目 {repo}。'
    return {
        'progress': start + '请说明当前进展和下一步，本轮不推进开发。',
        'summary': start + f'在 summary 末尾追加“{ADDITION}”并保存，其他事实字段保持原样，不做业务操作。临时完整 JSON 使用 {update}。',
        'report': start + '请给我当前报告链接，业务内容没有变化，不继续开发。',
        'handoff': start + '导出交接说明给下一位接手者，不修改源码，不继续开发。',
        'analysis': f'/zl-dev:go 只读分析项目 {repo} 中 total 的计算逻辑与输入来源，不修改代码，不建实施计划。用简短文字回答即可，不需要报告。',
    }[scenario]


def build_case(folder, scenario, plugin):
    repo, task = folder / 'repo', folder / 'task'
    repo.mkdir(parents=True)
    execute(['git', 'init', '-q', str(repo)])
    (repo / 'logic.py').write_text('def total(price, quantity):\n    return price * quantity\n')
    (repo / 'api.py').write_text('from logic import total\n\n\ndef handle(req):\n    return {"total": total(req["price"], req["qty"])}\n')
    (repo / 'CLAUDE.md').write_text(NOTICE, encoding='utf-8')
    execute(['git', 'add', '.'], repo)
    execute(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], repo)
    if scenario != 'analysis':
        script = plugin / 'scripts/reviewable.py'
        execute([sys.executable, script, 'init', task, '--project', repo, '--kind', 'feature', '--title', '评测 · 订单客户筛选'])
        data = json.loads((task / 'task.json').read_text())
        data.update(summary='订单导出支持按客户筛选；当前仅记录需求，尚未实施。', why='减少人工筛选。',
                    scope='限定任务说明与报告，不实施业务。',
                    behaviors=[dict(id='B1', before='人工筛选导出数据。', after='支持选择客户筛选导出数据。')])
        source = folder / 'controller-next.json'
        write_json(source, data)
        state = json.loads(execute([sys.executable, script, 'locate', task]))
        execute([sys.executable, script, 'update', task, '--project', repo, '--from-file', source,
                 '--expect-revision', state['task_revision']])
        execute([sys.executable, script, 'render', task])
    snapshot = folder / 'before'
    snapshot.mkdir()
    if (task / 'task.json').exists():
        (snapshot / 'task.json').write_bytes((task / 'task.json').read_bytes())
    return repo, task


def prepare(output, models, repeats):
    output = Path(output).expanduser()
    if not output.is_absolute() or output.exists():
        raise ValueError('prepare 需要一个新的绝对输出目录')
    total = len(models) * len(SCENARIOS) * repeats
    if not models or repeats < 1 or total > MAX_RUNS:
        raise ValueError(f'计划次数须在 1..{MAX_RUNS}')
    output.mkdir(mode=0o700)
    version = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text())['version']
    cases = []
    for model in models:
        for repeat in range(1, repeats + 1):
            for scenario in SCENARIOS:
                folder = output / f'{len(cases) + 1:02d}-{model}-{scenario}-r{repeat}'
                repo, task = build_case(folder, scenario, PLUGIN)
                cases.append(dict(id=folder.name, model=model, scenario=scenario, repeat=repeat,
                                  folder=str(folder), repo=str(repo), task=str(task), session_id=str(uuid.uuid4()),
                                  prompt=prompt_for(scenario, task, repo, folder / 'update.json'),
                                  git_state=git_state(repo),
                                  before={k: stamp(p) for k, p in [('source', repo / 'logic.py'), ('task', task / 'task.json'),
                                                                     ('report', task / 'report.html')]}))
    write_json(output / 'prepared.json', dict(version=1, plugin=str(PLUGIN), plugin_version=version, cases=cases,
                                               origin='controller-authored synthetic fixture, not real business feedback'))
    return dict(output=str(output), planned_runs=len(cases), model_calls=0)


def checks_for(case, plugin):
    folder, repo, task = Path(case['folder']), Path(case['repo']), Path(case['task'])
    checks = dict(source_unchanged=stamp(repo / 'logic.py') == case['before']['source'],
                  repo_git_unchanged=git_state(repo) == case['git_state'])
    after = {k: stamp(p) for k, p in [('task', task / 'task.json'), ('report', task / 'report.html'),
                                      ('handoff', task / 'HANDOFF.md')]}
    if case['scenario'] == 'analysis':
        checks['no_task_created'] = after['task'] is None
        return checks, after
    before = json.loads((folder / 'before/task.json').read_text())
    data = json.loads((task / 'task.json').read_text())
    strip = lambda d: {k: v for k, v in d.items() if k not in {'summary'}}
    if case['scenario'] == 'summary':
        checks['summary_appended'] = data.get('summary', '').startswith(before['summary']) and \
            data['summary'][len(before['summary']):].strip() == ADDITION
        checks['other_fields_unchanged'] = strip(before) == strip(data)
    else:
        checks['task_unchanged'] = after['task'] == case['before']['task']
    if case['scenario'] in {'progress', 'handoff'}:
        checks['report_untouched'] = after['report'] == case['before']['report']
    if case['scenario'] == 'handoff':
        checks['handoff_exported'] = after['handoff'] is not None
    return checks, after


def run_case(case, plugin, timeout, max_turns, claude):
    folder = Path(case['folder'])
    args = [claude, '-p', case['prompt'], '--model', case['model'], '--session-id', case['session_id'],
            '--plugin-dir', str(plugin), '--permission-mode', 'bypassPermissions',
            '--max-turns', str(max_turns), '--output-format', 'stream-json', '--verbose']
    started, code, timed_out = time.monotonic(), None, False
    with (folder / 'events.jsonl').open('x') as out, (folder / 'stderr.log').open('x') as err:
        try:
            code = subprocess.run(args, cwd=case['repo'], stdout=out, stderr=err, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    wall = round(time.monotonic() - started, 2)
    metrics = cost_metrics.summarize(folder / 'events.jsonl')
    write_json(folder / 'metrics.json', metrics, True)
    reported = metrics.get('reported') or {}
    checks, after = checks_for(case, plugin)
    tools = metrics['tools']
    return dict(id=case['id'], model=case['model'], scenario=case['scenario'], repeat=case['repeat'],
                exit_code=code, timed_out=timed_out, wall_s=wall,
                result_subtype=reported.get('subtype'), num_turns=reported.get('num_turns'),
                total_cost_usd=reported.get('total_cost_usd'), usage=reported.get('usage'),
                tool_calls=tools['unique_identified_tool_calls'], tools_by_name=tools['by_name'],
                bash_classes=tools['bash_classifications'],
                read_bytes=metrics['bytes_observed']['read_reported_content_utf8_bytes'],
                tool_result_bytes=metrics['bytes_observed']['tool_result_content_utf8_bytes'],
                checks=checks, passed=all(v is True for v in checks.values()), after=after)


def run(output, confirm_runs, timeout, max_turns, claude='claude'):
    output = Path(output).resolve()
    manifest = json.loads((output / 'prepared.json').read_text())
    if confirm_runs != len(manifest['cases']):
        raise ValueError(f'须显式 --confirm-runs {len(manifest["cases"])}')
    if not 1 <= timeout <= MAX_TIMEOUT or not 1 <= max_turns <= MAX_TURNS:
        raise ValueError(f'timeout<={MAX_TIMEOUT}，max-turns<={MAX_TURNS}')
    if (output / 'run-started.json').exists():
        raise ValueError('已开始过运行；结果不能覆盖或挑选重跑')
    write_json(output / 'run-started.json', dict(at=datetime.now(timezone.utc).isoformat(),
               claude_version=execute([claude, '--version']).strip(), timeout=timeout, max_turns=max_turns,
               notice='Sequential fresh sessions, no retries; global user settings/plugins stay loaded.'), True)
    rows = []
    for case in manifest['cases']:
        rows.append(run_case(case, Path(manifest['plugin']), timeout, max_turns, claude))
        write_json(Path(case['folder']) / 'outcome.json', rows[-1], True)
        write_json(output / 'outcomes.json', dict(version=1, cases=rows, complete=len(rows) == len(manifest['cases'])))
    return summarize(output)


def summarize(output):
    rows = json.loads((Path(output) / 'outcomes.json').read_text())['cases']
    groups = {}
    for row in rows:
        groups.setdefault((row['model'], row['scenario']), []).append(row)
    table = []
    for (model, scenario), items in sorted(groups.items()):
        turns = [r['num_turns'] for r in items if isinstance(r['num_turns'], int)]
        costs = [r['total_cost_usd'] for r in items if isinstance(r['total_cost_usd'], (int, float))]
        table.append(dict(model=model, scenario=scenario, runs=len(items),
                          success=sum(r['result_subtype'] == 'success' for r in items),
                          checks_passed=sum(r['passed'] for r in items),
                          timeouts=sum(r['timed_out'] for r in items),
                          max_turns_hit=sum(r['result_subtype'] == 'error_max_turns' for r in items),
                          turns=turns, tool_calls=[r['tool_calls'] for r in items],
                          wall_s=[r['wall_s'] for r in items], cost_usd=round(sum(costs), 4) if costs else None,
                          failed_checks=sorted({k for r in items for k, v in r['checks'].items() if v is not True})))
    summary = dict(version=1, groups=table, total_runs=len(rows),
                   interpretation='Raw per-run observations; small samples, no savings claim, cost is CLI-reported not a bill')
    write_json(Path(output) / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--output', required=True)
    p.add_argument('--model', action='append', required=True)
    p.add_argument('--repeats', type=int, default=3)
    r = sub.add_parser('run')
    r.add_argument('--output', required=True)
    r.add_argument('--confirm-runs', type=int, required=True)
    r.add_argument('--timeout', type=int, default=150)
    r.add_argument('--max-turns', type=int, default=12)
    s = sub.add_parser('summarize')
    s.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.output, args.model, args.repeats)
        elif args.command == 'run':
            result = run(args.output, args.confirm_runs, args.timeout, args.max_turns)
        else:
            result = summarize(args.output)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
