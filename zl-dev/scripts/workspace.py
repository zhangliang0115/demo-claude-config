#!/usr/bin/env python3
"""Local checkout observations and cooperative execution records; never authority or isolation."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from provenance import atomic_write
from session_context import _identity, inspect_target

NOTICE = '仅观察本机工作区和遵循协议的活动；不授予权限，不拦截外部编辑，不证明代码、端口或数据已隔离。registry_revision只核对活动索引字节，不说明源码或外部状态是否变化；observation_unstable=false仅表示未观察到登记写入。'
HISTORY_LIMIT = 20
MODES = {'read', 'write', 'verify'}


def _expected(value):
    if not isinstance(value, str) or (value != 'missing' and not re.fullmatch(r'[0-9a-f]{64}', value)):
        raise ValueError('必须提供 status 返回的 --expect-revision（missing 或 SHA256）；unknown/null 不能代替版本')


def registry_path():
    return Path.home() / '.claude/zl-dev/executions/activities.json'


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _git(project, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    return subprocess.run(['git', '-C', str(project), *args], capture_output=True, text=True,
                          timeout=10, env=env)


def inspect(project, task_dir=None):
    requested = Path(project).expanduser()
    if not requested.is_absolute():
        raise ValueError('project 必须为明确绝对路径')
    project = requested.resolve()
    if not project.is_dir():
        raise ValueError('项目工作区不存在或不可访问')
    target = inspect_target('task', task_dir, project) if task_dir is not None else None
    task_kind = json.loads((Path(target['path']) / 'task.json').read_bytes()).get('kind') if target else None
    result = dict(requested_path=str(requested), project_path=str(project), root_path=str(project),
                  identity_state='unknown', checkout_id=None, repository_family=None,
                  git_dir=None, common_dir=None, head=None, branch=None, head_state=None, branch_state=None, reason=None, target=target, task_kind=task_kind, notice=NOTICE)
    try:
        root = _git(project, 'rev-parse', '--show-toplevel')
        if root.returncode:
            if 'not a git repository' in root.stderr.lower():
                result.update(identity_state='non_git', checkout_id=_hash('path:' + str(project)),
                              reason='非 Git 目录；只按规范路径及祖先重叠检测，不推断逻辑项目关系。')
            else:
                result['reason'] = 'Git 身份查询失败：' + root.stderr.strip()[:400]
            return result
        root_path = Path(root.stdout.strip()).resolve()
        git_dir = _git(root_path, 'rev-parse', '--absolute-git-dir')
        common_dir = _git(root_path, 'rev-parse', '--git-common-dir')
        if git_dir.returncode or common_dir.returncode:
            result['reason'] = 'Git 工作区管理目录不可确认'
            return result
        common = Path(common_dir.stdout.strip())
        common = (root_path / common).resolve() if not common.is_absolute() else common.resolve()
        actual_git = Path(git_dir.stdout.strip()).resolve()
        head = _git(root_path, 'rev-parse', '--verify', 'HEAD')
        branch = _git(root_path, 'symbolic-ref', '--quiet', '--short', 'HEAD')
        if head.returncode and branch.returncode:
            result['reason'] = 'HEAD 与分支均不可确认，不能假定为空仓库'
            return result
        result.update(identity_state='git', root_path=str(root_path), git_dir=str(actual_git),
                      common_dir=str(common), checkout_id=_hash(str(root_path) + '\0' + str(actual_git)),
                      repository_family=_hash(str(common)), head=head.stdout.strip() if head.returncode == 0 else None,
                      branch=branch.stdout.strip() if branch.returncode == 0 else None,
                      head_state='current' if head.returncode == 0 else 'unborn',
                      branch_state='branch' if branch.returncode == 0 else 'detached',
                      reason='common_dir 仅表示本机 Git 家族；不按 remote URL 自动合并项目，不复用其他 checkout 证据。')
    except (OSError, subprocess.SubprocessError) as exc:
        result['reason'] = '工作区身份不可确认：' + str(exc)
    return result



def _redact(url):
    # 不在输出中暴露 URL 里的凭据
    return re.sub(r'^([a-z][a-z0-9+.-]*://)[^/@]*@', r'\1', url, flags=re.I)


def _remote_urls(root):
    try:
        result = _git(root, 'remote', '-v')
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode:
        return []
    return sorted({_redact(line.split()[1]) for line in result.stdout.splitlines() if len(line.split()) >= 2})


def _commit_known(root, commit):
    try:
        return bool(commit) and _git(root, 'cat-file', '-e', commit + '^{commit}').returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def relate(task_dir, other):
    """Read-only comparison of a task's bound checkout with another checkout (worktree, clone, other machine).

    Reports observable relations only. It never migrates the task, rebinds evidence or treats a shared
    remote URL as proof that two directories are the same project.
    """
    folder = Path(task_dir).expanduser().resolve()
    data = json.loads((folder / 'task.json').read_bytes())
    if not isinstance(data, dict):
        raise ValueError('task.json 不是对象，未比较')
    bound = data.get('project_path')
    if not isinstance(bound, str) or not Path(bound).is_absolute():
        raise ValueError('任务缺少明确的 project_path 绑定，先人工核对')
    candidate = inspect(other)
    original = inspect(bound) if Path(bound).is_dir() else dict(identity_state='missing', project_path=bound)
    relation = dict(task_id=data.get('id'), bound_project=bound, candidate_project=candidate['project_path'],
                    bound_available=original['identity_state'] != 'missing', notice=(
                        '只读比较；不迁移任务、不改 project_path、不把旧证据改绑到候选工作区。'
                        '在候选工作区继续时，旧证据按指纹规则视为不适用，需在该工作区重新验证。'))
    if candidate['identity_state'] != 'git':
        relation.update(state='not_comparable', reason='候选目录不是可识别的 Git checkout：' + str(candidate.get('reason')))
        return relation
    same_path = original.get('checkout_id') is not None and original.get('checkout_id') == candidate['checkout_id']
    same_family = original.get('repository_family') and original.get('repository_family') == candidate['repository_family']
    shared_remotes = sorted(set(_remote_urls(candidate['root_path'])) & set(_remote_urls(original['root_path']))) if original.get('identity_state') == 'git' else []
    rows = data.get('evidence') if isinstance(data.get('evidence'), list) else []
    evidence_revisions = sorted({e.get('revision') for e in rows if isinstance(e, dict) and isinstance(e.get('revision'), str) and e['revision']})
    relation.update(candidate_head=candidate['head'], bound_head=original.get('head'),
                    shared_remote_urls=shared_remotes, same_checkout=same_path, same_local_family=bool(same_family),
                    bound_head_known_in_candidate=_commit_known(candidate['root_path'], original.get('head')),
                    evidence_bound_revisions=len(evidence_revisions))
    if same_path:
        relation.update(state='same_checkout', reason='候选与任务绑定位于同一 checkout（可能是其中的不同子目录）。')
    elif same_family:
        relation.update(state='same_local_family', reason='同一本机 Git 仓库的另一个 worktree；Git 管理数据共享，工作区文件与证据不共享。')
    elif shared_remotes:
        relation.update(state='shared_remote', reason='有相同 remote URL，可能是另一台机器或另一份克隆；remote 相同不证明代码、配置或依赖相同。')
    else:
        relation.update(state='unrelated_or_unknown', reason='没有可观察的共同 Git 家族或 remote；不能认定为同一逻辑项目。')
    return relation


def _validate_observation(row):
    value = row['checkout']
    fields = {'requested_path','project_path','root_path','identity_state','checkout_id','repository_family',
              'git_dir','common_dir','head','branch','head_state','branch_state','reason','target','task_kind','notice'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('活动工作区观察字段缺失或未知')
    if value['identity_state'] not in ('git','non_git') or value['project_path'] != row['project_path']:
        raise ValueError('活动工作区与项目不一致')
    for key in ('project_path','root_path'):
        path = value[key]
        if not isinstance(path, str) or not Path(path).is_absolute() or os.path.normpath(path) != path:
            raise ValueError('活动项目和根目录必须为规范绝对路径')
    if not isinstance(value['requested_path'], str) or not Path(value['requested_path']).is_absolute():
        raise ValueError('活动原始请求路径无效')
    root, project = Path(value['root_path']), Path(value['project_path'])
    if root != project and root not in project.parents:
        raise ValueError('checkout 根目录不包含项目')
    target = value['target']
    if (not isinstance(target, dict) or set(target) != {'kind','path','id','title','project_path'}
        or target.get('kind') != 'task' or target.get('id') != row['task']['id']
        or target.get('path') != row['task']['path'] or target.get('project_path') != row['project_path']
        or not isinstance(target.get('title'), str) or not target['title']
        or not isinstance(value['task_kind'], str) or not value['task_kind']):
        raise ValueError('活动任务与工作区目标身份不一致')
    if not isinstance(value['checkout_id'], str) or not re.fullmatch(r'[0-9a-f]{64}', value['checkout_id']):
        raise ValueError('checkout_id 无效')
    if value['identity_state'] == 'non_git':
        if (root != project or value['checkout_id'] != _hash('path:' + str(project))
            or any(value[key] is not None for key in ('repository_family','git_dir','common_dir','head','branch','head_state','branch_state'))):
            raise ValueError('非 Git 观察内部不一致')
    else:
        for key in ('git_dir','common_dir'):
            path = value[key]
            if not isinstance(path, str) or not Path(path).is_absolute() or os.path.normpath(path) != path:
                raise ValueError('Git 管理目录必须为规范绝对路径')
        if value['checkout_id'] != _hash(str(root) + '\0' + value['git_dir']) or value['repository_family'] != _hash(value['common_dir']):
            raise ValueError('Git 工作区身份哈希不一致')
        if value['head_state'] not in ('current','unborn') or value['branch_state'] not in ('branch','detached'):
            raise ValueError('Git 版本观察无效')
        if value['head_state'] == 'current':
            if not isinstance(value['head'], str) or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', value['head']):
                raise ValueError('Git HEAD 无效')
        elif value['head'] is not None or value['branch_state'] != 'branch':
            raise ValueError('空分支版本观察不一致')
        if value['branch_state'] == 'branch':
            if not isinstance(value['branch'], str) or not value['branch']:
                raise ValueError('Git 分支观察无效')
        elif value['branch'] is not None:
            raise ValueError('分离 HEAD 不应记录分支')
    if value['task_kind'] == 'analysis' and row['mode'] != 'read':
        raise ValueError('只读分析活动不能是写入或验证')


def _read():
    path = registry_path()
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('活动索引必须为普通文件')
    if not path.exists():
        return None, dict(version=1, active=[], history=[]), 'missing'
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {'version', 'active', 'history'} or data['version'] != 1:
            raise ValueError('索引结构无效')
        if not isinstance(data['active'], list) or not isinstance(data['history'], list) or len(data['history']) > HISTORY_LIMIT:
            raise ValueError('活动或历史结构无效')
        tokens = set()
        for position, row in enumerate(data['active'] + data['history']):
            fields = {'token','host','session_id','task','project_path','checkout','mode','resources','started_at'}
            if not isinstance(row, dict) or set(row) != (fields if position < len(data['active']) else fields | {'ended_at'}):
                raise ValueError('活动结构无效')
            if (row['mode'] not in MODES or not isinstance(row['resources'], list)
                or not isinstance(row['started_at'], str) or not row['started_at']
                or ('ended_at' in row and (not isinstance(row['ended_at'], str) or not row['ended_at']))):
                raise ValueError('活动模式无效')
            _resources(row['resources'])
            _identity(row['host'], row['session_id'], '/')
            if not isinstance(row['token'], str) or not re.fullmatch(r'[0-9a-f]{32}', row['token']) or row['token'] in tokens:
                raise ValueError('活动 token 无效或重复')
            tokens.add(row['token'])
            if (not isinstance(row['task'], dict) or not all(isinstance(row['task'].get(k), str) and row['task'][k] for k in ('id','path'))
                or not Path(row['task']['path']).is_absolute()
                or not isinstance(row['checkout'], dict) or row['checkout'].get('identity_state') not in ('git','non_git')
                or not isinstance(row['checkout'].get('root_path'), str) or not Path(row['checkout']['root_path']).is_absolute()
                or not isinstance(row['checkout'].get('checkout_id'), str)):
                raise ValueError('活动任务或工作区身份无效')
            _validate_observation(row)
        return raw, data, hashlib.sha256(raw).hexdigest()
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ValueError('活动索引损坏，未覆盖；需核对原始记录：' + str(exc)) from exc


@contextmanager
def _lock():
    from filelock import _backend, exclusive
    if _backend()[0] is None:
        raise ValueError('当前平台不支持活动写锁；只读 inspect/status 仍可使用')
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix('.lock')
    if lock.is_symlink():
        raise ValueError('活动锁不能为符号链接')
    with exclusive(lock, '当前平台不支持活动写锁；只读 inspect/status 仍可使用'):
        yield


def _overlap(a, b):
    if a['checkout_id'] == b['checkout_id']:
        return True
    x, y = Path(a['root_path']), Path(b['root_path'])
    return x == y or x in y.parents or y in x.parents


def _resources(values):
    if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() or len(x) > 256 for x in values) or len(set(values)) != len(values):
        raise ValueError('resources 必须为唯一、非空的明确资源标识数组')
    return sorted(values)


def status(project):
    checkout = inspect(project)
    result = dict(checkout=checkout, registry_path=str(registry_path()), registry_revision=None,
                  state='unknown', active=[], observation_unstable=None, notice=NOTICE)
    try:
        _, data, revision = _read()
        result.update(state='observed', registry_revision=revision,
                      active=[row for row in data['active'] if _overlap(checkout, row['checkout'])
                              or (checkout['repository_family'] and checkout['repository_family'] == row['checkout'].get('repository_family'))],
                      reason='这里只列已登记活动；没有登记不代表没有其他编辑者。记录不会因时间久自动失效；须确认执行已停止后显式结束。')
    except (ValueError, OSError) as exc:
        result['reason'] = str(exc)
    if checkout['identity_state'] == 'unknown':
        result['state'] = 'unknown'
    if result['state'] == 'observed':
        result['observation_unstable'] = any(row['mode'] != 'read' for row in result['active'])
    return result


def _save(path, raw, data):
    if path.is_symlink() or (path.read_bytes() if path.exists() else None) != raw:
        raise ValueError('活动索引更新期间变化，未覆盖')
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())


def begin(host, session, project, task_dir, mode, expected_revision, resources=None):
    host, session, project = _identity(host, session, project)
    _expected(expected_revision)
    if mode not in MODES:
        raise ValueError('mode 必须为 read/write/verify')
    resources = _resources([] if resources is None else resources)
    checkout = inspect(project, task_dir)
    if checkout['identity_state'] == 'unknown':
        raise ValueError('工作区身份不明，未登记活动：' + checkout['reason'])
    target = checkout['target']
    if checkout['task_kind'] == 'analysis' and mode != 'read':
        raise ValueError('只读分析任务仅允许 read 活动')
    with _lock():
        raw, data, revision = _read()
        if revision != expected_revision:
            raise ValueError('活动索引版本冲突；请重新 status，未开始登记')
        current = inspect(project, task_dir)
        if any(current.get(k) != checkout.get(k) for k in ('identity_state','checkout_id','head','branch','target','task_kind')):
            raise ValueError('登记期间工作区或任务身份变化；请重新核对')
        if current['task_kind'] == 'analysis' and mode != 'read':
            raise ValueError('只读分析任务仅允许 read 活动')
        warnings, conflicts, existing = [], [], None
        for row in data['active']:
            same_checkout = _overlap(checkout, row['checkout'])
            same_resource = bool(set(resources) & set(row['resources']))
            same = (row['host'] == host and row['session_id'] == session and row['task']['path'] == target['path']
                    and row['task']['id'] == target['id'] and row['project_path'] == str(project)
                    and row['mode'] == mode and row['resources'] == resources and row['checkout']['checkout_id'] == checkout['checkout_id'])
            if same:
                existing = row
                if any(row['checkout'].get(k) != checkout.get(k) for k in ('head','branch')):
                    warnings.append('已有活动的 HEAD/分支快照与当前不同；未重写原始执行观察，需核对期间变化。')
                continue
            if (same_checkout or same_resource) and mode != 'read' and row['mode'] != 'read':
                conflicts.append(row)
            elif same_checkout or same_resource:
                warnings.append('存在共享工作区/资源的活动 ' + row['token'] + '；只读结果可能在观察期间变化。')
            elif checkout['repository_family'] and checkout['repository_family'] == row['checkout'].get('repository_family'):
                warnings.append('另一个 worktree 存在活动 ' + row['token'] + '；Git 管理数据与未声明端口/数据库可能共享。')
        if conflicts:
            return dict(state='conflict', changed=False, conflicts=conflicts, registry_revision=revision,
                        reason='已有登记的写入/验证活动共享实际工作区或显式资源；先核对后串行、协作或选择独立环境。', notice=NOTICE)
        if existing is not None:
            return dict(state='active', changed=False, activity=existing, registry_revision=revision, warnings=warnings, notice=NOTICE)
        activity = dict(token=uuid.uuid4().hex, host=host, session_id=session,
                        task=dict(id=target['id'], path=target['path']), project_path=str(project), checkout=checkout,
                        mode=mode, resources=resources, started_at=datetime.now(timezone.utc).isoformat())
        data['active'].append(activity)
        _save(registry_path(), raw, data)
        revision = hashlib.sha256(registry_path().read_bytes()).hexdigest()
        return dict(state='active', changed=True, activity=activity, registry_revision=revision, warnings=warnings, notice=NOTICE)


def end(host, session, token, expected_revision):
    _identity(host, session, '/')
    _expected(expected_revision)
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('必须提供 begin 返回的明确活动 token')
    with _lock():
        raw, data, revision = _read()
        if revision != expected_revision:
            raise ValueError('活动索引版本冲突；请重新 status，未结束登记')
        row = next((x for x in data['active'] if x['token'] == token), None)
        if row is None:
            return dict(state='not_found', changed=False, token=token, registry_revision=revision, notice=NOTICE)
        if row['host'] != host or row['session_id'] != session:
            raise ValueError('不能结束其他宿主/会话的活动；需由原执行者核对停止状态')
        data['active'] = [x for x in data['active'] if x['token'] != token]
        data['history'] = (data['history'] + [dict(row, ended_at=datetime.now(timezone.utc).isoformat())])[-HISTORY_LIMIT:]
        _save(registry_path(), raw, data)
        return dict(state='ended', changed=True, token=token, registry_revision=hashlib.sha256(registry_path().read_bytes()).hexdigest(),
                    notice=NOTICE + ' 结束登记不负责停止进程或提交代码。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect','status','begin','end','relate'])
    parser.add_argument('--other', type=Path)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--task', type=Path)
    parser.add_argument('--host')
    parser.add_argument('--session')
    parser.add_argument('--mode', choices=sorted(MODES))
    parser.add_argument('--resource', action='append', default=[])
    parser.add_argument('--expect-revision')
    parser.add_argument('--token')
    args = parser.parse_args()
    try:
        if args.command == 'end':
            if args.project or args.task or args.mode or args.resource:
                raise ValueError('end 只接受活动 token、宿主、会话和索引版本')
            result = end(args.host, args.session, args.token, args.expect_revision)
        elif args.command == 'relate':
            if not args.task or not args.other or args.project or args.resource or args.host or args.session or args.mode or args.expect_revision or args.token:
                raise ValueError('relate 只接受 --task 与 --other，且只读')
            result = relate(args.task, args.other)
        elif not args.project:
            raise ValueError('必须提供 --project')
        elif args.command == 'begin':
            if not args.task or args.token:
                raise ValueError('begin 必须提供 --task，不接受 --token')
            result = begin(args.host, args.session, args.project, args.task, args.mode, args.expect_revision, args.resource)
        else:
            if args.host or args.session or args.mode or args.resource or args.expect_revision or args.token or (args.command == 'status' and args.task):
                raise ValueError('只读观察不接受活动写入参数')
            result = inspect(args.project, args.task) if args.command == 'inspect' else status(args.project)
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
