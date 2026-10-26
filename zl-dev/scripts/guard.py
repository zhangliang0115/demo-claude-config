"""PreToolUse guard: protected zl-dev records change only through the CLI.

Edit tools aimed at protected files are always denied. Bash is checked with a
heuristic (protected name + write operator); it is a guard rail, not a sandbox.
Exit code 2 blocks the tool call and shows stderr to the model.
"""
import json
import os
from pathlib import Path
import re
import sys

PROTECTED_NAMES = ('task.json', 'feature.json', 'report.html', 'feature.html')
EDIT_TOOLS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}
CLI_SCRIPTS = re.compile(r'\b(reviewable|feature|workflow|analysis|verification|workspace|session_context)\.py\b')
NAME = '|'.join(re.escape(n) for n in PROTECTED_NAMES)
# 写入目标是受保护文件的常见形态：重定向、tee、cp/mv/install 的最后一个参数、原地编辑、Python 写打开
BASH_WRITE_TARGET = [
    re.compile(r'>>?\s*["\']?[^\s;&|]*(%s)\b' % NAME),
    re.compile(r'\btee\b[^;&|]*(%s)\b' % NAME),
    re.compile(r'\b(cp|mv|install|rsync|ln)\b[^;&|]*\s["\']?[^\s;&|]*(%s)["\']?\s*$' % NAME),
    re.compile(r'\b(sed\s+-i|perl\s+-p?i|truncate|rm)\b[^;&|]*(%s)\b' % NAME),
    re.compile(r'open\([^)]*(%s)[^)]*[\'"][wax+]' % NAME),
    re.compile(r'(%s)[^;&|]*\.(write_text|write_bytes)\(' % NAME),
]
ADVICE = ('zl-dev 记录只能经 CLI 修改：先 locate 取得 task_revision，把合并后的完整 JSON 写到系统临时目录，'
          '再运行 reviewable.py update --from-file <临时文件> --expect-revision <revision>；页面用 render 生成。'
          '不要改用其他工具或命令绕过。')


def zl_home():
    return Path(os.environ.get('HOME', str(Path.home()))) / '.claude' / 'zl-dev'


def protected_path(value):
    if not value:
        return False
    path = Path(value).expanduser()
    try:
        relative = path.resolve().relative_to(zl_home().resolve())
    except ValueError:
        return False
    return path.name in PROTECTED_NAMES or relative.parts[:1] in {('contexts',), ('executions',)}


def bash_violation(command):
    if 'zl-dev' not in command or not any(name in command for name in PROTECTED_NAMES):
        return False
    segments = [seg.strip() for seg in re.split(r'&&|\|\||;|\n|\|', command)]
    return any(not CLI_SCRIPTS.search(seg) and any(rule.search(seg) for rule in BASH_WRITE_TARGET)
               for seg in segments)


def check(event):
    tool = event.get('tool_name')
    params = event.get('tool_input') or {}
    if tool in EDIT_TOOLS:
        target = params.get('file_path') or params.get('notebook_path')
        if protected_path(target):
            return f'已拒绝直接修改 {target}。' + ADVICE
    elif tool == 'Bash' and bash_violation(params.get('command', '')):
        return '已拒绝用 shell 命令改写 zl-dev 记录或页面。' + ADVICE
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0  # 输入异常时不阻断宿主，避免误伤普通操作
    reason = check(event)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    from filelock import utf8_stdio
    utf8_stdio()
    sys.exit(main())
