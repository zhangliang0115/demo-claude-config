#!/usr/bin/env python3
"""Explicit-path cross-project coordinator; no build or production execution."""
import argparse
from datetime import datetime, timezone
import html
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
import re
import subprocess
import sys

import reviewable
from storage import resolve_output

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def validate(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('feature.json 必须是 version=1 的对象')
    if 'workspace_path' in data and (not isinstance(data['workspace_path'], str) or not Path(data['workspace_path']).is_absolute()):
        raise ValueError('workspace_path 必须是绝对路径字符串')
    for key in ('id', 'title'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(key + ' 必须非空')
    for key in ('projects', 'contracts', 'allocations', 'integration'):
        if not isinstance(data.get(key), list) or any(not isinstance(x, dict) for x in data[key]):
            raise ValueError(key + ' 必须是对象数组')
    ids, paths = set(), set()
    for p in data['projects']:
        ident = p.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident in ids:
            raise ValueError('project id 必须唯一且使用字母数字下划线或短横线')
        path = Path(p.get('path', ''))
        if not path.is_absolute() or path.resolve() in paths:
            raise ValueError('项目路径必须绝对且不能重复')
        ids.add(ident)
        paths.add(path.resolve())
    contracts = set()
    for c in data['contracts']:
        if not c.get('id') or c['id'] in contracts or not c.get('version') or c.get('status') not in {'proposed', 'confirmed'}:
            raise ValueError('共享约定需要唯一 id、version 和 proposed/confirmed 状态')
        contracts.add(c['id'])
    graph = {}
    for a in data['allocations']:
        if not a.get('id') or a['id'] in graph or a.get('project_id') not in ids:
            raise ValueError('分配必须有唯一 id 并引用已登记项目')
        deps = a.get('depends_on', [])
        if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
            raise ValueError('depends_on 必须为分配 id 数组')
        graph[a['id']] = deps
    active, done = set(), set()
    def visit(node):
        if node not in graph:
            raise ValueError('依赖引用不存在的分配: ' + node)
        if node in active:
            raise ValueError('分配依赖存在循环')
        if node in done:
            return
        active.add(node)
        for dep in graph[node]:
            visit(dep)
        active.remove(node)
        done.add(node)
    for node in graph:
        visit(node)
    return data


def load(folder):
    return validate(json.loads((Path(folder) / 'feature.json').read_text(encoding='utf-8')))


@contextmanager
def write_lock(folder):
    from filelock import exclusive
    with exclusive(Path(folder) / '.feature-update.lock', '当前平台不支持 feature 写锁；只读 locate/status/preflight 仍可使用，未执行写入'):
        yield


def _replace_locked(folder, data, previous=None):
    """Caller owns .feature-update.lock; replace in the same filesystem."""
    target = Path(folder) / 'feature.json'
    if target.is_symlink():
        raise ValueError('feature.json 不能是符号链接')
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix='.feature-update-', delete=False) as temp:
            temporary = Path(temp.name)
            if target.exists():
                os.fchmod(temp.fileno(), target.stat().st_mode & 0o777)
            temp.write(payload)
            temp.flush()
            os.fsync(temp.fileno())
        if previous is not None and target.read_bytes() != previous:
            raise ValueError('功能在更新期间发生变化：未覆盖，请重新 locate')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return payload


def save(folder, data, expected_revision=None):
    validate(data)
    with write_lock(folder):
        previous = None
        if expected_revision is not None:
            previous = (Path(folder) / 'feature.json').read_bytes()
            if reviewable.task_revision(previous) != expected_revision:
                raise ValueError('功能版本冲突：请重新 locate 并合并修改')
        _replace_locked(folder, data, previous)


def snapshot(folder):
    """Assess one exact feature input; never sync or rewrite linked materials."""
    from provenance import assessment_revision
    folder = Path(folder).resolve()
    raw = (folder / 'feature.json').read_bytes()
    data = assessed(validate(json.loads(raw)))
    data['feature_revision'] = reviewable.task_revision(raw)
    data['assessment_revision'] = assessment_revision(data)
    data['provenance'] = dict(version=1, feature_id=data['id'],
        workspace_path=data.get('workspace_path'), project_bindings=project_bindings(data),
        feature_revision=data['feature_revision'], assessment_revision=data['assessment_revision'])
    return data


def project_bindings(data):
    return sorted([dict(id=p['id'], path=p['path']) for p in data['projects']], key=lambda p: p['id'])


def report_state(folder, state=None):
    """Inspect data/template freshness without syncing or rendering."""
    from provenance import inspect_report
    target = Path(folder) / 'feature.html'
    state = snapshot(folder) if state is None and target.is_file() else state
    known = state is not None and all(p.get('current_snapshot', {}).get('current_fingerprint') for p in state['projects'])
    return inspect_report(target, state, 'feature-data', ROOT, known)


def locate(folder):
    from brief import feature_brief
    folder = Path(folder).resolve()
    data = snapshot(folder)
    report = report_state(folder, data)
    return dict(feature_dir=str(folder), feature_file=str(folder / 'feature.json'),
                feature_brief=feature_brief(data),
                feature_revision=data['feature_revision'], assessment_revision=data['assessment_revision'],
                id=data['id'], title=data['title'], workspace_path=data.get('workspace_path'),
                phase=data.get('phase'), contract_version=data.get('contract_version'),
                report=report['path'], report_state=report, assessment=data['assessment'])


def update_feature(folder, source, workspace, expected_revision):
    folder = Path(folder).resolve()
    target = folder / 'feature.json'
    if target.is_symlink() or not target.is_file():
        raise ValueError('目标 feature.json 必须是已有普通文件，不能是符号链接')
    if not expected_revision:
        raise ValueError('更新必须提供 locate 返回的 --expect-revision')
    replacement = validate(json.loads(Path(source).read_bytes()))
    with write_lock(folder):
        if target.is_symlink():
            raise ValueError('目标 feature.json 不能是符号链接')
        raw = target.read_bytes()
        original = validate(json.loads(raw))
        if reviewable.task_revision(raw) != expected_revision:
            raise ValueError('功能版本冲突：请重新 locate 并合并修改')
        bound = original.get('workspace_path')
        if not bound or Path(bound).resolve() != Path(workspace).expanduser().resolve():
            raise ValueError('功能绑定工作区与 --workspace 不匹配')
        if replacement.get('id') != original['id'] or replacement.get('workspace_path') != bound:
            raise ValueError('更新不能改变功能 id 或 workspace_path')
        original_projects = {p['id']: p for p in original['projects']}
        new_projects = {p['id']: p for p in replacement['projects']}
        if set(original_projects) != set(new_projects) or any(original_projects[key]['path'] != new_projects[key]['path'] for key in original_projects):
            raise ValueError('更新不能改变已绑定的项目 id/path 集合')
        derived = ('snapshot', 'snapshot_freshness', 'current_snapshot')
        for key in original_projects:
            for field in derived:
                old, new = original_projects[key], new_projects[key]
                if (field in old) != (field in new) or old.get(field) != new.get(field):
                    raise ValueError('派生快照只能通过 sync 更新，不能改写 ' + field)
        for field in ('assessment', 'generated_at', 'feature_revision', 'assessment_revision', 'provenance'):
            if (field in original) != (field in replacement) or original.get(field) != replacement.get(field):
                raise ValueError('更新不能改写派生字段 ' + field)
        payload = _replace_locked(folder, replacement, raw)
    return dict(feature_dir=str(folder), feature_revision=reviewable.task_revision(payload), updated=True)


def init(folder, title, projects, workspace=None):
    folder = Path(folder).resolve()
    if (folder / 'feature.json').exists():
        raise ValueError('feature.json 已存在，拒绝覆盖')
    rows = []
    for item in projects:
        ident, sep, path = item.partition('=')
        if not sep or not Path(path).is_absolute():
            raise ValueError('--project 格式为 id=/absolute/path')
        if Path(path).resolve() == folder:
            raise ValueError('功能目录不能作为项目自身')
        rows.append(dict(id=ident, path=str(Path(path).resolve()), observations=[], responsibility='', task_path='', contract_version='', status='unassigned'))
    data = dict(version=1, workspace_path=str(Path(workspace or Path.cwd()).expanduser().resolve()), id=folder.name, title=title, owner='当前负责人', mode='flexible', phase='discovery', contract_version='', design=dict(goal='',flow='',boundaries='',decisions=''), projects=rows, contracts=[], allocations=[], integration=[])
    validate(data)
    folder.mkdir(parents=True, exist_ok=True)
    save(folder, data)
    return data


def head(path):
    try:
        return reviewable.git(['rev-parse', 'HEAD'], path).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def inspect(folder):
    revision = locate(folder)['feature_revision']
    data = load(folder)
    for p in data['projects']:
        path = Path(p['path'])
        if not path.is_dir():
            p['observations'] = ['路径不存在或无法访问；不得推断项目职责']
            continue
        observations = []
        try:
            names = {x.name for x in path.iterdir()}
            for name in ('package.json', 'pom.xml', 'pyproject.toml', 'build.gradle', 'build.gradle.kts', 'go.mod', 'Cargo.toml', 'README.md', 'AGENTS.md', 'docs'):
                if name in names:
                    observations.append('存在: ' + name + '（尚未据此确认职责）')
            observations.append('Git HEAD: ' + (head(path) or '未知/非 Git 仓库'))
        except OSError:
            observations = ['路径无法读取；不得推断项目职责']
        p['observations'] = observations
    save(folder, data, revision)
    return data


def task_location(p):
    value = p.get('task_path', '')
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else Path(p['path']) / path


def repository_fingerprint(path):
    try:
        root = Path(reviewable.git(['rev-parse', '--show-toplevel'], path).decode().strip())
        digest = hashlib.sha256((head(path) or 'UNBORN').encode())
        names = reviewable.git(['ls-files', '-z', '--cached', '--others', '--exclude-standard'], root).split(b'\0')
        for raw in sorted(set(names)):
            if not raw:
                continue
            relative = Path(raw.decode('utf-8', 'surrogateescape'))
            if any(part in {'.zl-dev', '.reviewable-dev'} for part in relative.parts):
                continue
            target = root / relative
            digest.update(raw)
            if target.is_symlink():
                import os
                digest.update(os.fsencode(os.readlink(target)))
            else:
                digest.update(target.read_bytes() if target.is_file() else b'MISSING')
        return digest.hexdigest()
    except (OSError, subprocess.CalledProcessError):
        return None


def project_snapshot(p):
    path = Path(p['path'])
    snap = dict(synced_at=now(), availability='available' if path.is_dir() else 'inaccessible', head=head(path), current_fingerprint=None, task_id='', task_stage='', task_contract_version='', contract_match=False, evidence_counts=dict(total=0, passed_current=0, failed=0, stale=0, unresolved_current=0), issues=[])
    task = task_location(p)
    snap['task_path'] = str(task.expanduser().resolve()) if task else ''
    snap['current_fingerprint'] = repository_fingerprint(path) if path.is_dir() else None
    if not path.is_dir():
        snap['issues'].append('项目路径不存在或无法访问')
    if not task:
        snap['issues'].append('尚未关联项目子任务')
        return snap
    try:
        # A task from another repository cannot supply this project's evidence.
        child = reviewable.snapshot(task)
        if child.get('kind') == 'analysis':
            snap['issues'].append('关联任务仅为只读分析，不构成实施、测试或联调完成证据')
        binding = child.get('project_path')
        if binding is not None:
            if Path(binding).resolve() != path.resolve():
                raise ValueError('子任务 project_path 与对应项目不匹配')
        elif task.resolve() != path.resolve() and path.resolve() not in task.resolve().parents:
            raise ValueError('外部子任务必须明确绑定对应项目 project_path')
        snap['current_fingerprint'] = child['current_fingerprint']
        snap['task_revision'] = child['task_revision']
        snap['task_assessment_revision'] = child['assessment_revision']
        version = child.get('contract_version') or child.get('feature', {}).get('contract_version', '')
        snap.update(task_id=child['id'], task_stage=child.get('stage', ''), task_contract_version=version, contract_match=bool(p.get('contract_version')) and version == p.get('contract_version'))
        if not snap['contract_match']:
            snap['issues'].append('子任务共享约定版本缺失或不匹配')
        for e in child.get('evidence', []):
            counts = snap['evidence_counts']
            counts['total'] += 1
            counts['passed_current'] += int(e.get('status') == 'passed' and e['freshness'] == '当前')
            counts['failed'] += int(e.get('status') == 'failed')
            counts['stale'] += int(e['freshness'] != '当前')
            counts['unresolved_current'] += int(e['freshness'] == '当前' and e.get('status') != 'passed')
        if not child.get('behaviors'):
            snap['issues'].append('尚无可验证的行为约定')
        # Readiness consumes high-risk review and current explicit human returns.
        # Business decisions remain visible in the child, rather than being mislabeled failed tests.
        snap['technical_blockers'] = [b for b in child['workflow_summary']['blockers']
                                      if (b['type'] == 'review' and b['severity'] in {'P0', 'P1'})
                                      or b['type'] in {'human_feedback', 'delegated_feedback', 'ai_feedback'}]
        for blocker in snap['technical_blockers']:
            if blocker['type'] in {'human_feedback', 'delegated_feedback', 'ai_feedback'}:
                snap['issues'].append(('受托 AI 验收反馈 ' if blocker['type'] == 'delegated_feedback' else 'AI 核验反馈 ' if blocker['type'] == 'ai_feedback' else '人工反馈 ') + blocker.get('stage', '') + ' ' + blocker['id'] + ': ' + blocker['summary'])
            else:
                snap['issues'].append('审查 ' + blocker['severity'] + ' ' + blocker['id'] + ': ' + blocker['summary'])
        snap['missing_behaviors'] = child['workflow_summary']['missing_verification_count']
        if snap['missing_behaviors'] or snap['evidence_counts']['unresolved_current']:
            snap['issues'].append('项目当前验证仍有未覆盖行为或未通过证据；历史证据保留供追溯')
        if not snap['evidence_counts']['total']:
            snap['issues'].append('尚无验证证据')
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        snap['issues'].append('子任务无法核对: ' + str(exc))
    return snap


def sync(folder):
    revision = locate(folder)['feature_revision']
    data = load(folder)
    for p in data['projects']:
        p['snapshot'] = project_snapshot(p)
    save(folder, data, revision)
    return data


def assessed(data):
    result = json.loads(json.dumps(data))
    for field in ('feature_revision', 'assessment_revision', 'provenance'):
        result.pop(field, None)
    issues = []
    confirmed_versions = {c['version'] for c in result['contracts'] if c['status'] == 'confirmed'}
    for p in result['projects']:
        previous = p.get('snapshot')
        current = project_snapshot(p)
        p['current_snapshot'] = {key: value for key, value in current.items() if key != 'synced_at'}
        p['snapshot_freshness'] = 'not_synced' if not previous else ('unknown' if not current['current_fingerprint'] else ('current' if all(previous.get(k) == current.get(k) for k in ('task_path', 'task_id', 'current_fingerprint', 'task_contract_version', 'contract_match', 'evidence_counts', 'task_stage', 'technical_blockers', 'issues', 'task_revision', 'task_assessment_revision')) else 'stale'))
        issues.extend(p['id'] + ': ' + x for x in current['issues'])
        if result.get('contract_version') and p.get('contract_version') != result['contract_version']:
            issues.append(p['id'] + ': 项目基线落后于整体方案版本')
        if p.get('contract_version') not in confirmed_versions:
            issues.append(p['id'] + ': 项目绑定版本不在已确认的共享约定中')
        if p['snapshot_freshness'] != 'current':
            issues.append(p['id'] + ': 快照需要同步或无法核对')
    for allocation in result['allocations']:
        if result.get('contract_version') and allocation.get('contract_version') != result['contract_version']:
            issues.append(allocation['id'] + ': 开发切片尚未对齐整体方案基线')
    if not result['allocations']:
        issues.append('尚未确认项目分工')
    if not result['contracts'] or any(c['status'] != 'confirmed' for c in result['contracts']):
        issues.append('共享约定尚未全部确认')
    if not result['projects']:
        issues.append('尚未登记项目')
    result['assessment'] = dict(ready_for_integration=not issues, issues=issues, delivery='联调准备就绪不代表交付完成；此评估不汇总整体接受结论。核对完整链路的实际结果、判断者与接受依据；已有适用的人工或明确受托 AI 结果不重复核验，不据自由文本或子任务通过推断整体接受。')
    result['generated_at'] = now()
    return result


def preflight(folder):
    """Read-only implementation baseline check; this is not an Edit hook."""
    data = load(folder)
    issues = []
    baseline = data.get('contract_version')
    if not baseline:
        issues.append('整体方案尚无 contract_version')
    if not data['contracts'] or any(c['status'] != 'confirmed' or c['version'] != baseline for c in data['contracts']):
        issues.append('共享契约尚未全部在当前整体方案版本确认')
    projects = {p['id']: p for p in data['projects']}
    if not projects or not data['allocations']:
        issues.append('尚未登记项目或开发切片')
    for p in projects.values():
        if not Path(p['path']).is_dir():
            issues.append(p['id'] + ': 项目路径不存在或无法访问')
        if p.get('contract_version') != baseline:
            issues.append(p['id'] + ': 项目版本与整体方案不一致')
        task = task_location(p)
        if task:
            try:
                child = reviewable.load(task)
                binding = child.get('project_path')
                if binding and Path(binding).resolve() != Path(p['path']).resolve():
                    issues.append(p['id'] + ': 子任务项目绑定不匹配')
                if not binding and task.resolve() != Path(p['path']).resolve() and Path(p['path']).resolve() not in task.resolve().parents:
                    issues.append(p['id'] + ': 外部子任务缺少 project_path 绑定')
                if (child.get('contract_version') or child.get('feature', {}).get('contract_version')) != baseline:
                    issues.append(p['id'] + ': 子任务采用的契约版本不匹配')
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                issues.append(p['id'] + ': 子任务无法读取: ' + str(exc))
    allocations = {a['id']: a for a in data['allocations']}
    for allocation in allocations.values():
        if allocation.get('contract_version') != baseline:
            issues.append(allocation['id'] + ': 开发切片版本与整体方案不一致')
        for dep in allocation.get('depends_on', []):
            dependency = allocations[dep]
            if dependency.get('contract_version') != baseline or projects[dependency['project_id']].get('contract_version') != baseline:
                issues.append(allocation['id'] + ': 依赖 ' + dep + ' 尚未对齐共享契约')
    return dict(ready_for_implementation=not issues, contract_version=baseline, issues=issues,
                notice='只读前置核对，不修改快照，不替代人工确认或运行验证，也不能拦截任意代码编辑。')


def render(folder, state=None):
    from provenance import report_bytes, publish_report, template_bundle, render_report_bytes
    target = Path(folder) / 'feature.html'
    with write_lock(folder):
        expected_report = report_bytes(target)
        data = snapshot(folder) if state is None else json.loads(json.dumps(state))
    data['generated_at'] = now()
    bundle = template_bundle(ROOT, 'feature-data')
    data['provenance']['template_revision'] = bundle['revision']
    output = render_report_bytes(data, bundle)
    return publish_report(target, output, expected_report, data,
                          lambda: snapshot(folder), lambda: write_lock(folder),
                          'feature-data', reuse_matching=True, bundle=bundle,
                          current_template=lambda: template_bundle(ROOT, 'feature-data')['revision'],
                          known_code=all(p.get('current_snapshot', {}).get('current_fingerprint') for p in data['projects']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'inspect', 'sync', 'render', 'status', 'preflight', 'locate', 'update'):
        cmd = sub.add_parser(name)
        cmd.add_argument('folder')
        cmd.add_argument('--workspace', type=Path, default=Path.cwd())
        if name == 'update':
            cmd.add_argument('--from-file', type=Path, required=True)
            cmd.add_argument('--expect-revision', required=True)
        if name == 'init':
            cmd.add_argument('--title', required=True)
            cmd.add_argument('--project', action='append', default=[])
    args = parser.parse_args()
    try:
        args.folder = resolve_output(args.folder, 'features', args.workspace)
        if args.command == 'init':
            value = init(args.folder, args.title, args.project, args.workspace)
        elif args.command == 'update':
            value = update_feature(args.folder, args.from_file, args.workspace, args.expect_revision)
        elif args.command == 'status':
            value = snapshot(args.folder)
            value['report_state'] = report_state(args.folder, value)
            value['report'] = value['report_state']['path']
        else:
            value = globals()[args.command](args.folder)
        if isinstance(value, dict):
            value['output_dir'] = str(args.folder)
        print(str(value) if isinstance(value, Path) else json.dumps(value, ensure_ascii=False, indent=2))
        if args.command == 'preflight' and not value['ready_for_implementation']:
            raise SystemExit(2)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
