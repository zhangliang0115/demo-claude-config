#!/usr/bin/env python3
"""Explicit-path cross-project coordinator; no build or production execution."""
import argparse
from datetime import datetime, timezone
import html
import hashlib
import json
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


def save(folder, data):
    validate(data)
    (Path(folder) / 'feature.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


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
    save(folder, data)
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
    snap = dict(synced_at=now(), availability='available' if path.is_dir() else 'inaccessible', head=head(path), current_fingerprint=None, task_id='', task_stage='', task_contract_version='', contract_match=False, evidence_counts=dict(total=0, passed_current=0, failed=0, stale=0), issues=[])
    task = task_location(p)
    snap['current_fingerprint'] = repository_fingerprint(path) if path.is_dir() else None
    if not path.is_dir():
        snap['issues'].append('项目路径不存在或无法访问')
    if not task:
        snap['issues'].append('尚未关联项目子任务')
        return snap
    try:
        # A task from another repository cannot supply this project's evidence.
        child_data = reviewable.load(task)
        binding = child_data.get('project_path')
        if binding is not None:
            if Path(binding).resolve() != path.resolve():
                raise ValueError('子任务 project_path 与对应项目不匹配')
        elif task.resolve() != path.resolve() and path.resolve() not in task.resolve().parents:
            raise ValueError('外部子任务必须明确绑定对应项目 project_path')
        snap['current_fingerprint'] = reviewable.fingerprint(task)
        child = reviewable.assessed(child_data, snap['current_fingerprint'])
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
        if not child.get('behaviors'):
            snap['issues'].append('尚无可验证的行为约定')
        snap['missing_behaviors'] = child['workflow_summary']['missing_verification_count']
        if snap['missing_behaviors'] or snap['evidence_counts']['failed'] or snap['evidence_counts']['stale']:
            snap['issues'].append('项目验证仍有缺口、失败或过期证据')
        if not snap['evidence_counts']['total']:
            snap['issues'].append('尚无验证证据')
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        snap['issues'].append('子任务无法核对: ' + str(exc))
    return snap


def sync(folder):
    data = load(folder)
    for p in data['projects']:
        p['snapshot'] = project_snapshot(p)
    save(folder, data)
    return data


def assessed(data):
    result = json.loads(json.dumps(data))
    issues = []
    confirmed_versions = {c['version'] for c in result['contracts'] if c['status'] == 'confirmed'}
    for p in result['projects']:
        previous = p.get('snapshot')
        current = project_snapshot(p)
        p['snapshot_freshness'] = 'not_synced' if not previous else ('unknown' if not current['current_fingerprint'] else ('current' if all(previous.get(k) == current.get(k) for k in ('current_fingerprint', 'task_contract_version', 'contract_match', 'evidence_counts', 'task_stage', 'issues')) else 'stale'))
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
    result['assessment'] = dict(ready_for_integration=not issues, issues=issues, delivery='待人工核验；联调准备就绪不代表交付完成')
    result['generated_at'] = now()
    return result


def render(folder):
    data = assessed(load(folder))
    payload = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    template = (ROOT / 'assets/feature.html').read_text(encoding='utf-8')
    replacements = {'__FEATURE_DATA__': payload, '__FEATURE_TITLE__': html.escape(data['title'])}
    target = Path(folder) / 'feature.html'
    target.write_text(re.sub('__FEATURE_DATA__|__FEATURE_TITLE__', lambda m: replacements[m.group()], template), encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'inspect', 'sync', 'render', 'status'):
        cmd = sub.add_parser(name)
        cmd.add_argument('folder')
        cmd.add_argument('--workspace', type=Path, default=Path.cwd())
        if name == 'init':
            cmd.add_argument('--title', required=True)
            cmd.add_argument('--project', action='append', default=[])
    args = parser.parse_args()
    try:
        args.folder = resolve_output(args.folder, 'features', args.workspace)
        if args.command == 'init':
            value = init(args.folder, args.title, args.project, args.workspace)
        elif args.command == 'status':
            value = assessed(load(args.folder))
        else:
            value = globals()[args.command](args.folder)
        if isinstance(value, dict):
            value['output_dir'] = str(args.folder)
        print(str(value) if isinstance(value, Path) else json.dumps(value, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
