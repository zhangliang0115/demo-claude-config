#!/usr/bin/env python3
"""Prepare pinned local fixtures; explicitly run six fresh Claude sessions, never business code."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import uuid

REPOSITORY = Path(__file__).resolve().parents[2]
VARIANTS = {'v0160': 'a329f16', 'v0200': 'b53d4a2'}
ORDER = [('progress','v0160'), ('progress','v0200'), ('summary','v0200'),
         ('summary','v0160'), ('report','v0160'), ('report','v0200')]
ADDITION = '补充：本轮只记录说明，不改变验收标准。'
NOTICE = ('合成评测，只操作指定任务；源码只读。未要求业务实现或测试，'
          '不对外发消息，不执行生产操作。保留真实失败，不伪造结果。\n')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, data, exclusive=False):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def stamp(path):
    path = Path(path)
    if not path.exists():
        return None
    raw = path.read_bytes()
    return dict(sha256=digest(raw), bytes=len(raw), mtime_ns=path.stat().st_mtime_ns)


def execute(args, cwd=None):
    # 固定的历史插件版本早于 UTF-8 输出修复；统一子进程编码，不改动历史代码
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    result = subprocess.run([str(x) for x in args], cwd=cwd, capture_output=True, text=True, encoding='utf-8',
                            timeout=30, env=env)
    if result.returncode:
        raise ValueError('Fixture command failed: ' + result.stderr[-1200:])
    return result.stdout


def git_state(repo):
    return dict(head=execute(['git','rev-parse','HEAD'],repo).strip(),
                status=execute(['git','status','--porcelain=v1','--untracked-files=all'],repo))


def archive_plugin(repository, commit, target):
    revision = execute(['git','rev-parse',commit+'^{commit}'], repository).strip()
    raw = subprocess.run(['git','archive','--format=tar',revision,'zl-dev'], cwd=repository,
                         check=True, capture_output=True, timeout=30).stdout
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Archive contains unsafe path or non-regular member')
        archive.extractall(target)
    plugin = target / 'zl-dev'
    version = json.loads((plugin/'.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    return dict(commit=revision, version=version, plugin=str(plugin), archive_sha256=digest(raw))


def fixture_files(root):
    for path in sorted(root.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            yield path


def prompt_for(scenario, task, repo, update):
    start = f'/zl-dev:go 已有任务 {task}，项目 {repo}。'
    if scenario == 'progress':
        return start + '请说明当前进展和下一步，本轮不推进开发。'
    if scenario == 'summary':
        return start + f'在 summary 末尾追加“{ADDITION}”并保存，其他事实字段保持原样，不做业务操作。临时完整 JSON 使用 {update}。'
    return start + '请给我现有报告，业务内容没有变化，不继续开发。'


def prepare(output, repository=REPOSITORY):
    output = Path(output).expanduser()
    if not output.is_absolute() or output.exists():
        raise ValueError('prepare requires a NEW absolute output directory')
    output.mkdir(mode=0o700, parents=False)
    output = output.resolve()
    variants = {}
    for name, revision in VARIANTS.items():
        variants[name] = archive_plugin(repository, revision, output/name)
    cases = []
    for ordinal, (scenario, variant) in enumerate(ORDER):
        started = time.monotonic()
        folder = output / f'{ordinal+1:02d}-{scenario}-{variant}'
        folder.mkdir()
        repo, task = folder/'repo', folder/'task'
        repo.mkdir()
        commands = []
        def command(args, cwd=None):
            commands.append(dict(argv=[str(x) for x in args], cwd=str(cwd) if cwd else None))
            return execute(args, cwd)
        command(['git','init','-q',str(repo)])
        (repo/'logic.py').write_text('def total(price, quantity):\n    return price * quantity\n', encoding='utf-8')
        (repo/'CLAUDE.md').write_text(NOTICE, encoding='utf-8')
        command(['git','add','.'], repo)
        command(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                 'commit','-qm','isolated cost fixture'], repo)
        script = Path(variants[variant]['plugin'])/'scripts/reviewable.py'
        command([sys.executable,script,'init',task,'--project',repo,'--kind','feature',
                 '--title','成本基线 · 订单客户筛选'])
        data = json.loads((task/'task.json').read_text(encoding='utf-8'))
        data.update(summary='订单导出支持按客户筛选；当前仅记录需求，尚未实施。',
                    why='减少人工筛选。', scope='限定任务说明与报告，不实施业务。',
                    behaviors=[dict(id='B1',before='人工筛选导出数据。',after='支持选择客户筛选导出数据。')])
        source = folder/'controller-next.json'
        write_json(source,data)
        state = json.loads(command([sys.executable,script,'locate',task]))
        command([sys.executable,script,'update',task,'--project',repo,'--from-file',source,
                 '--expect-revision',state['task_revision']])
        command([sys.executable,script,'render',task])
        initial = json.loads(command([sys.executable,script,'locate',task]))
        snapshot = folder/'before';snapshot.mkdir()
        for name,path in [('source.py',repo/'logic.py'),('task.json',task/'task.json'),
                          ('report.html',task/'report.html')]:
            (snapshot/name).write_bytes(path.read_bytes())
        cases.append(dict(id=folder.name, scenario=scenario, variant=variant,
                          folder=str(folder),repo=str(repo),task=str(task),
                          session_id=str(uuid.uuid4()),
                          prompt=prompt_for(scenario,task,repo,folder/'update.json'),
                          git_state=git_state(repo),initial_fingerprint=initial['fingerprint'],
                          initial_report_state=initial['report_state'],
                          before={name:stamp(path) for name,path in [
                              ('source',repo/'logic.py'),('task',task/'task.json'),('report',task/'report.html')]},
                          setup_wall_ms=round((time.monotonic()-started)*1000,3),
                          controller_commands=commands))
    manifest = dict(version=1,origin='controller-authored synthetic fixture, not real business feedback',
                    root=str(output), variants=variants,cases=cases,
                    setup_scope='CLI initialization/rendering measured separately; no model sessions during prepare',
                    environment_isolation='Global Claude settings/plugins/hooks remain enabled and must be compared using actual init events')
    write_json(output/'prepared.json',manifest)
    files = {p.relative_to(output).as_posix():digest(p.read_bytes()) for p in fixture_files(output)
             if '.git' not in p.parts}
    write_json(output/'integrity.json',dict(version=1, files=files))
    return dict(output=str(output), prepared_cases=len(cases), model_calls=0)


def validate_prepared(output):
    output = Path(output).expanduser().resolve()
    if not output.is_dir() or output.is_symlink():
        raise ValueError('Prepared directory missing')
    integrity = json.loads((output/'integrity.json').read_text(encoding='utf-8'))
    if integrity.get('version') != 1 or not isinstance(integrity.get('files'),dict):
        raise ValueError('Invalid integrity manifest')
    for name, sha in integrity['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid manifest path')
        path = output/relative
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != sha:
            raise ValueError('Prepared fixture changed: '+name)
    manifest = json.loads((output/'prepared.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or manifest.get('root') != str(output) or len(manifest.get('cases',[])) != 6:
        raise ValueError('Invalid or moved fixture manifest')
    expected_files = set(integrity['files'])
    for variant in manifest['variants'].values():
        plugin = Path(variant['plugin'])
        for path in fixture_files(plugin):
            if path.relative_to(output).as_posix() not in expected_files:
                raise ValueError('Unexpected plugin file: '+path.relative_to(output).as_posix())
    for case in manifest['cases']:
        if git_state(case['repo']) != case.get('git_state'):
            raise ValueError('Prepared Git state changed: '+case['id'])
    return output,manifest


def plugin_integrity(output, manifest, expected_files=None):
    """Observe frozen plugin trees without trusting a model-modified manifest."""
    output=Path(output)
    if expected_files is None:
        expected_files=json.loads((output/'integrity.json').read_text(encoding='utf-8'))['files']
    result={}
    for name,variant in manifest['variants'].items():
        row=dict(state='unknown',expected_files=None,changed_files=[],unexpected_files=[])
        try:
            plugin=Path(variant['plugin'])
            if plugin.resolve()!=plugin:
                raise ValueError('Plugin root is no longer its prepared physical path')
            prefix=plugin.relative_to(output).as_posix()+'/'
            expected={p:sha for p,sha in expected_files.items() if p.startswith(prefix)}
            row['expected_files']=len(expected)
            if not expected:
                raise ValueError('No frozen plugin files in manifest')
            for relative,sha in expected.items():
                path=output/relative
                if path.resolve()!=path or not path.is_file() or digest(path.read_bytes())!=sha:
                    row['changed_files'].append(relative)
            for path in plugin.rglob('*'):
                if path.is_symlink():
                    relative=path.relative_to(output).as_posix()
                    if relative not in expected:
                        row['unexpected_files'].append(relative)
            for path in fixture_files(plugin):
                relative=path.relative_to(output).as_posix()
                if relative not in expected and relative not in row['unexpected_files']:
                    row['unexpected_files'].append(relative)
            row['state']='changed' if row['changed_files'] or row['unexpected_files'] else 'current'
        except (OSError,ValueError,KeyError) as exc:
            row['reason']=str(exc)
        result[name]=row
    return result


def read_events(path):
    events, errors = [], []
    for number,line in enumerate(Path(path).read_text(encoding='utf-8',errors='replace').splitlines(),1):
        try:
            value=json.loads(line)
            if isinstance(value,dict):events.append(value)
            else:errors.append(number)
        except ValueError:errors.append(number)
    return events,errors


def outcome(case, plugin, events, expected_version=None):
    folder,repo,task = Path(case['folder']),Path(case['repo']),Path(case['task'])
    before=json.loads((folder/'before/task.json').read_text(encoding='utf-8'))
    try:after=json.loads((task/'task.json').read_text(encoding='utf-8'))
    except (ValueError,OSError):after=None
    checks=dict(source_unchanged=stamp(repo/'logic.py') == case['before']['source'],
                task_json_readable=isinstance(after,dict), summary_expectation_met=None,
                other_task_fields_unchanged=None, report_current=None, repo_git_state_unchanged=None)
    try:
        observed_git=git_state(repo)
        checks['repo_git_state_unchanged']=observed_git==case.get('git_state')
    except (OSError,ValueError,subprocess.SubprocessError):observed_git=None
    if after is not None:
        left={k:v for k,v in before.items() if k!='summary'}
        right={k:v for k,v in after.items() if k!='summary'}
        checks['other_task_fields_unchanged']=left==right
        expected=before['summary']+(ADDITION if case['scenario']=='summary' else '')
        actual=after.get('summary')
        checks['summary_expectation_met']=(isinstance(actual,str) and
            (actual==expected or (case['scenario']=='summary' and actual.startswith(before['summary'])
                                 and actual[len(before['summary']):].strip()==ADDITION)))
    try:
        state=json.loads(execute([sys.executable,Path(plugin)/'scripts/reviewable.py','locate',task]))
        checks['report_current']=state['report_state']['freshness']=='current'
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
    init=next((e for e in events if e.get('type')=='system' and e.get('subtype')=='init'),None)
    loaded=[p for p in (init or {}).get('plugins',[]) if p.get('name')=='zl-dev']
    actual_plugin=loaded[0] if len(loaded)==1 else None
    checks['expected_plugin_loaded']=(actual_plugin is not None and expected_version is not None
        and actual_plugin.get('version')==expected_version
        and Path(actual_plugin.get('path','')).resolve()==Path(plugin).resolve())
    return dict(checks=checks,after={name:stamp(path) for name,path in [
        ('source',repo/'logic.py'),('task',task/'task.json'),('report',task/'report.html')]} | dict(git_state=observed_git),
        actual_plugin=actual_plugin,actual_zl_plugin_count=len(loaded))


def run(output, confirm_runs, timeout=150, max_turns=12, claude='claude'):
    if confirm_runs != 6 or not 1 <= timeout <= 150 or not 1 <= max_turns <= 12:
        raise ValueError('Explicit --confirm-runs 6 required; timeout<=150 and max-turns<=12')
    output,manifest=validate_prepared(output)
    expected_plugin_files=json.loads((output/'integrity.json').read_text(encoding='utf-8'))['files']
    initial_plugin_integrity=plugin_integrity(output,manifest,expected_plugin_files)
    if any(row['state']!='current' for row in initial_plugin_integrity.values()):
        raise ValueError('Prepared plugin integrity unavailable or changed')
    if (output/'run-started.json').exists() or (output/'outcomes.json').exists():
        raise ValueError('Run already started; results must not be overwritten or selectively retried')
    for case in manifest['cases']:
        if any((Path(case['folder'])/name).exists() for name in ('events.jsonl','stderr.log','outcome.json')):
            raise ValueError('Case already has output')
    version=execute([claude,'--version']).strip()
    write_json(output/'run-started.json',dict(at=datetime.now(timezone.utc).isoformat(),
        claude_version=version,requested_max_turns=max_turns,timeout_seconds=timeout,
        plugin_integrity=initial_plugin_integrity,
        notice='Six sequential fresh sessions; no retries. Turn limit is not a token budget. Timeout kills the direct subprocess, not a guaranteed whole descendant process tree.'),True)
    outcomes=[]
    for case in manifest['cases']:
        folder=Path(case['folder']);plugin=Path(manifest['variants'][case['variant']]['plugin'])
        args=[claude,'-p',case['prompt'],'--session-id',case['session_id'],'--plugin-dir',str(plugin),
              '--tools','Read','Bash','Write','--allowedTools','Read',
              'Bash(python3 '+str(plugin/'scripts/reviewable.py')+' *)',
              'Write('+str(folder/'update.json')+')']
        if (plugin/'scripts/session_context.py').exists():
            args+=['Bash(python3 '+str(plugin/'scripts/session_context.py')+' *)']
        args+=['--max-turns',str(max_turns),'--output-format','stream-json','--verbose']
        started=time.monotonic();code=None;timed_out=False
        with (folder/'events.jsonl').open('x') as stdout,(folder/'stderr.log').open('x') as stderr:
            os.chmod(stdout.name,0o600);os.chmod(stderr.name,0o600)
            try:code=subprocess.run(args,cwd=case['repo'],stdout=stdout,stderr=stderr,timeout=timeout).returncode
            except subprocess.TimeoutExpired:timed_out=True
            except OSError as exc:stderr.write(str(exc))
        wall=round((time.monotonic()-started)*1000,3)
        events,errors=read_events(folder/'events.jsonl')
        results=[e for e in events if e.get('type')=='result']
        result=results[-1] if len(results)==1 else {}
        row=dict(id=case['id'],scenario=case['scenario'],variant=case['variant'],
                 exit_code=code,timed_out=timed_out,wall_ms=wall,
                 requested_max_turns=max_turns,observed_num_turns=result.get('num_turns'),
                 result_count=len(results),result_subtype=result.get('subtype'),
                 malformed_event_lines=errors,
                 **outcome(case,plugin,events,manifest['variants'][case['variant']]['version']),
                 plugin_integrity=plugin_integrity(output,manifest,expected_plugin_files))
        write_json(folder/'outcome.json',row,True);outcomes.append(row)
        write_json(output/'outcomes.json',dict(version=1,cases=outcomes,complete=len(outcomes)==6,
                    interpretation='Raw observations; no savings claim, no exact billing attribution'))
    return dict(output=str(output),completed_cases=len(outcomes),
                successful_cli_results=sum(x['result_subtype']=='success' for x in outcomes))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('prepare','run'):
        p=sub.add_parser(name);p.add_argument('--output',type=Path,required=True)
        if name=='run':
            p.add_argument('--confirm-runs',type=int,required=True)
            p.add_argument('--timeout',type=int,default=150)
            p.add_argument('--max-turns',type=int,default=12)
    args=parser.parse_args()
    try:
        result=prepare(args.output) if args.command=='prepare' else run(args.output,args.confirm_runs,args.timeout,args.max_turns)
        print(json.dumps(result,ensure_ascii=False,separators=(',',':')));return 0
    except (OSError,ValueError,KeyError,subprocess.SubprocessError,tarfile.TarError) as exc:
        print('错误：'+str(exc),file=sys.stderr);return 1


if __name__=='__main__':
    from filelock import utf8_stdio
    utf8_stdio()
    sys.exit(main())
