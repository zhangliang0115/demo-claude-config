#!/usr/bin/env python3
"""Recoverable session focus. This index never grants authority or owns task facts."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from provenance import atomic_write
from storage import project_key

MISSING = 'missing'
NOTICE = '会话关联仅用于定位，不隔离代码、不授予权限，也不代表任务完成。'
HISTORY_LIMIT = 10


def _identity(host, session, project):
    if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', host):
        raise ValueError('host 必须为明确的工具命名空间')
    if (not isinstance(session, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}', session)
        or session.lower() in {'unknown', 'undefined', 'null', 'none', 'current'}):
        raise ValueError('缺少可靠会话 ID；不能使用空值、占位符、PID 或当前目录代替，请使用明确任务引用')
    project = Path(project).expanduser()
    if not project.is_absolute():
        raise ValueError('project 必须为实际项目或总功能工作区的绝对路径')
    return host, session, project.resolve()


def context_path(host, session, project):
    host, session, project = _identity(host, session, project)
    session_key = hashlib.sha256(session.encode()).hexdigest()
    return Path.home() / '.claude' / 'zl-dev' / 'contexts' / host / session_key / (project_key(project) + '.json')


def _read(path, host, session, project):
    if path.is_symlink():
        raise ValueError('会话关联文件不能为符号链接')
    if not path.exists():
        return None, None, MISSING, None
    if not path.is_file():
        raise ValueError('会话关联必须为普通文件')
    raw = path.read_bytes()
    revision = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get('version') != 1 or data.get('host') != host
            or data.get('session_id') != session or data.get('project_path') != str(project)
            or 'target' not in data or not isinstance(data.get('history'), list)
            or len(data['history']) > HISTORY_LIMIT):
            raise ValueError('关联身份或结构不匹配')
        if data['target'] is not None:
            target = data['target']
            if (not isinstance(target, dict) or set(target) != {'kind', 'path', 'id', 'title', 'project_path'}
                or target.get('kind') not in {'task', 'feature'}
                or any(not isinstance(target.get(k), str) or not target[k].strip() for k in ('path', 'id', 'title', 'project_path'))
                or not Path(target['path']).is_absolute() or target['project_path'] != str(project)):
                raise ValueError('目标身份或结构无效')
        return raw, data, revision, None
    except (ValueError, TypeError, UnicodeError) as exc:
        return raw, None, revision, '关联文件损坏或身份不匹配：' + str(exc)


def inspect_target(kind, target, project):
    if kind not in {'task', 'feature'}:
        raise ValueError('target-kind 必须为 task 或 feature')
    folder = Path(target).expanduser()
    if not folder.is_absolute():
        raise ValueError('target 必须为明确的绝对任务或功能目录')
    folder = folder.resolve()
    if not folder.is_dir() or not project.is_dir():
        raise ValueError('目标或项目工作区不存在，请核对本机路径')
    source = folder / ('task.json' if kind == 'task' else 'feature.json')
    other = folder / ('feature.json' if kind == 'task' else 'task.json')
    if source.is_symlink() or not source.is_file():
        raise ValueError('目标事实记录必须为已有普通文件，不能为符号链接')
    if other.exists() or other.is_symlink():
        raise ValueError('目标同时包含 task.json 与 feature.json，不能确定目标身份')
    if kind == 'task':
        import reviewable
        data = reviewable.validate(json.loads(source.read_bytes()))
        bound = data.get('project_path')
    else:
        import feature
        data = feature.validate(json.loads(source.read_bytes()))
        bound = data.get('workspace_path')
    if not isinstance(bound, str) or not Path(bound).is_absolute() or Path(bound).resolve() != project:
        raise ValueError('目标绑定项目/工作区与 --project 不匹配；不能猜测补绑')
    return dict(kind=kind, path=str(folder), id=data['id'], title=data['title'], project_path=str(project))


def resolve(host, session, project):
    host, session, project = _identity(host, session, project)
    path = context_path(host, session, project)
    _, data, revision, error = _read(path, host, session, project)
    result = dict(context_path=str(path), context_revision=revision, host=host,
                  project_path=str(project), state='unbound', action='choose_or_start', target=None,
                  notice=NOTICE)
    if error:
        result.update(state='invalid_index', action='repair_binding', reason=error)
        return result
    if not data or data['target'] is None:
        return result
    saved = data['target']
    try:
        current = inspect_target(saved['kind'], saved['path'], project)
        if any(current[k] != saved[k] for k in ('kind', 'path', 'id', 'project_path')):
            raise ValueError('同一路径的目标身份已变化，必须明确重新选择')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result.update(state='invalid_target', action='repair_binding', reason=str(exc), recorded_target=saved)
        return result
    result.update(state='bound', action='continue', target=current)
    return result


@contextmanager
def _lock(path):
    from filelock import _backend, exclusive
    if _backend()[0] is None:
        raise ValueError('当前平台不支持会话写锁；只读 resolve 仍可使用')
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix('.lock')
    if lock.is_symlink():
        raise ValueError('会话关联锁不能为符号链接')
    with exclusive(lock, '当前平台不支持会话写锁；只读 resolve 仍可使用'):
        yield


def _expected(value):
    if value != MISSING and (not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value)):
        raise ValueError('必须提供 resolve 返回的 --expect-revision（missing 或 SHA256）')


def _same_target(a, b):
    if a is None or b is None:
        return a is b
    return all(a.get(k) == b.get(k) for k in ('kind', 'path', 'id', 'project_path'))


def _change(host, session, project, expected_revision, target):
    _expected(expected_revision)
    host, session, project = _identity(host, session, project)
    path = context_path(host, session, project)
    # Explicitly clearing a missing index is a read-only no-op, with no directories created.
    if target is None and not path.exists() and not path.is_symlink():
        if expected_revision != MISSING:
            raise ValueError('会话关联版本冲突：请重新 resolve，未切换关联')
        result = resolve(host, session, project)
        if result['context_revision'] != MISSING:
            raise ValueError('会话关联版本冲突：请重新 resolve，未切换关联')
        return dict(result, changed=False)
    with _lock(path):
        raw, previous, revision, error = _read(path, host, session, project)
        if revision != expected_revision:
            raise ValueError('会话关联版本冲突：请重新 resolve，未切换关联')
        # Recheck the actual target while holding the index lock, not merely its old display title.
        if target is not None:
            current = inspect_target(target['kind'], target['path'], project)
            if not _same_target(target, current):
                raise ValueError('目标身份在绑定期间变化，未切换关联，请重新核对')
            target = current
        if previous is not None and _same_target(previous['target'], target):
            return dict(resolve(host, session, project), changed=False)
        now = datetime.now(timezone.utc).isoformat()
        history = list(previous['history']) if previous else []
        if previous and previous['target'] is not None:
            history.append(dict(target=previous['target'], at=now))
        data = dict(version=1, host=host, session_id=session, project_path=str(project),
                    target=target, history=history[-HISTORY_LIMIT:], updated_at=now)
        if error:
            # Repair is explicit and CAS-bound; preserve malformed bytes for recovery.
            backup = path.with_name(path.name + '.invalid-' + revision)
            if not backup.exists():
                atomic_write(backup, raw)
            data['replaced_invalid_revision'] = revision
        payload = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
        if path.is_symlink() or (path.read_bytes() if path.exists() else None) != raw:
            raise ValueError('会话关联在更新期间变化，未覆盖')
        atomic_write(path, payload)
    return dict(resolve(host, session, project), changed=True)


def bind(host, session, project, target_kind, target, expected_revision):
    host, session, project = _identity(host, session, project)
    checked = inspect_target(target_kind, target, project)
    return _change(host, session, project, expected_revision, checked)


def clear(host, session, project, expected_revision):
    return _change(host, session, project, expected_revision, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['resolve', 'bind', 'clear'])
    parser.add_argument('--host', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--target-kind', choices=['task', 'feature'])
    parser.add_argument('--target', type=Path)
    parser.add_argument('--expect-revision')
    args = parser.parse_args()
    try:
        if args.command == 'resolve':
            if args.target_kind or args.target or args.expect_revision:
                raise ValueError('resolve 只读，不接受切换或写入参数')
            result = resolve(args.host, args.session, args.project)
        elif args.command == 'bind':
            if not args.target_kind or args.target is None:
                raise ValueError('bind 必须提供明确 --target-kind 和 --target')
            result = bind(args.host, args.session, args.project, args.target_kind, args.target, args.expect_revision)
        else:
            if args.target_kind or args.target:
                raise ValueError('clear 仅清除会话关联，不接受目标参数')
            result = clear(args.host, args.session, args.project, args.expect_revision)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    from filelock import utf8_stdio
    utf8_stdio()
    sys.exit(main())
