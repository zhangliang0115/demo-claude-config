"""Stable project-bound output locations; never migrate existing artifacts implicitly."""
import hashlib
import json
from pathlib import Path
import re
import subprocess


def project_key(project):
    path = Path(project).expanduser().resolve()
    label = re.sub(r'[^\w.-]+', '-', path.name) or 'project'
    return label + '-' + hashlib.sha256(str(path).encode()).hexdigest()[:12]


def project_root(project):
    return Path.home() / '.claude' / 'zl-dev' / 'projects' / project_key(project)


def resolve_output(location, bucket, project):
    if bucket not in {'tasks', 'features'}:
        raise ValueError('未知产出类型')
    value = str(location)
    if value in {'.', '..'}:
        raise ValueError('任务名称不能是 . 或 ..；旧路径请使用明确路径')
    path = Path(value).expanduser()
    if path.is_absolute() or '/' in value or '\\' in value:
        return path.resolve()
    if not value.strip():
        raise ValueError('任务名称不能为空')
    return project_root(project) / bucket / value


def task_project(task_dir):
    """An explicit binding is authoritative, including when its source is missing."""
    folder = Path(task_dir).resolve()
    source = folder / 'task.json'
    if source.exists():
        data = json.loads(source.read_text(encoding='utf-8'))
        if 'project_path' in data:
            value = data['project_path']
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError('project_path 必须是绝对路径字符串')
            return Path(value).resolve()
    try:
        return Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=folder, stderr=subprocess.DEVNULL).decode().strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        return None
