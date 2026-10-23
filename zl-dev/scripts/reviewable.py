#!/usr/bin/env python3
"""Offline zl-dev report builder. Python 3.9+, standard library only."""
import argparse
import hashlib
import html
import json
import re
import os
import tempfile
from pathlib import Path
import subprocess
import sys
from workflow import summarize
from storage import project_root, resolve_output, task_project

KINDS = {'feature': '新功能：使用场景与异常路径', 'change': '业务调整：规则差异与生效范围', 'bugfix': '缺陷修复：复现、根因与回归', 'refactor': '重构：结构变化与行为保持', 'performance': '性能优化：同条件基线与代价', 'migration': '数据迁移：转换、核对与恢复', 'upgrade': '技术升级：兼容性与行为对比'}
KINDS.update({'incident': '生产事件：影响、止损、诊断与恢复', 'operations': '日常运维：检查、变更、验证与恢复'})
ROOT = Path(__file__).resolve().parents[1]
STAGES = json.loads((ROOT / 'templates/stages.json').read_text(encoding='utf-8'))

def stage_skeleton():
    return {key: dict(purpose=meta['focus'], owner='', summary='', decision='', exit_criteria='', items=[]) for key, meta in STAGES.items()}



def git(args, cwd):
    return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.DEVNULL)


def semantic_contract(data):
    contract = {k: data.get(k) for k in ('project_path','kind','scope','acceptance','feature','contract_version')}
    contract['behaviors'] = [{k:b.get(k) for k in ('id','before','after')} for b in data.get('behaviors',[])]
    contract['scenarios'] = data.get('scenarios',[])
    details = data.get('stage_details',{})
    fields = {'requirements':('id','original','interpretation','boundary','example'), 'solution':('id','name','approach','flow'), 'acceptance':('id','scenario','instruction','expected')}
    contract['stage_contract'] = {key:[{field:item.get(field) for field in names} for item in details.get(key,{}).get('items',[])] for key,names in fields.items()}
    return contract


def fingerprint(task_dir):
    """Fingerprint HEAD + tracked and untracked nonignored contents, excluding reports."""
    task_dir = Path(task_dir).resolve()
    try:
        project = task_project(task_dir)
        if project is None or not project.is_dir():
            return None
        root = Path(git(['rev-parse', '--show-toplevel'], project).decode().strip()).resolve()
        try:
            head = git(['rev-parse', 'HEAD'], root).strip()
        except subprocess.CalledProcessError:
            head = b'UNBORN'
        names = set(git(['ls-files', '-z', '--cached', '--others', '--exclude-standard'], root).split(b'\0'))
        digest = hashlib.sha256(head)
        task_file = task_dir / 'task.json'
        if task_file.exists():
            contract = json.loads(task_file.read_text(encoding='utf-8'))
            contract = semantic_contract(contract)
            digest.update(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode('utf-8'))
        for raw in sorted(names):
            if not raw:
                continue
            path = root / raw.decode('utf-8', 'surrogateescape')
            # lexical exclusion prevents reading symlinked external content
            if path == task_dir or task_dir in path.parents:
                continue
            digest.update(raw + b'\0')
            if path.is_symlink():
                import os
                digest.update(b'LINK' + os.fsencode(os.readlink(path)))
            elif path.is_file():
                digest.update(b'FILE' + path.read_bytes())
            else:
                digest.update(b'MISSING')
        return digest.hexdigest()
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def validate(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('task.json 必须是 version=1 的对象')
    if 'project_path' in data and (not isinstance(data['project_path'], str) or not Path(data['project_path']).is_absolute()):
        raise ValueError('project_path 必须是绝对路径字符串')
    if 'focus_stage' in data and data['focus_stage'] not in STAGES:
        raise ValueError('focus_stage 必须为固定阶段名')
    for key in ('id', 'title', 'kind'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'{key} 必须是非空字符串')
    if data['kind'] not in KINDS:
        raise ValueError('不支持的任务类型')
    for key in ('behaviors', 'scenarios', 'implementation', 'decisions', 'evidence', 'roles', 'assumptions', 'design', 'handoffs', 'timeline', 'operations'):
        rows = data.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
            raise ValueError(f'{key} 必须是对象数组')
    for scene in data.get('scenarios', []):
        if scene.get('kind') not in ('simulation', 'recorded'):
            raise ValueError('场景必须标记 simulation 或 recorded')
        if not isinstance(scene.get('steps', []), list) or any(not isinstance(x, dict) for x in scene.get('steps', [])):
            raise ValueError('场景 steps 必须是对象数组')
    for key in ('risks', 'changes', 'acceptance'):
        if not isinstance(data.get(key, []), list):
            raise ValueError(f'{key} 必须是数组')
    ids = [b.get('id') for b in data.get('behaviors', [])]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError('行为 id 必须唯一且非空')
    for key, allowed in [('evidence', {'passed','failed','blocked','not_run'}), ('handoffs', {'pending','accepted','rejected'})]:
        for row in data.get(key, []):
            if row.get('status') not in allowed:
                raise ValueError(f'{key} 状态无效')
    evidence_ids = [e.get('id') for e in data.get('evidence', [])]
    if any(not isinstance(value, str) or not value.strip() for value in evidence_ids) or len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError('证据 id 必须唯一且非空')
    for evidence in data.get('evidence', []):
        refs = evidence.get('behavior_ids', [])
        if not isinstance(refs, list) or any(x not in ids for x in refs):
            raise ValueError('证据引用了不存在的行为')
    details = data.get('stage_details', {})
    if not isinstance(details, dict) or set(details) - set(STAGES):
        raise ValueError('stage_details 只能使用模板规定的阶段名')
    for key, section in details.items():
        if not isinstance(section, dict) or set(section) - {'purpose','owner','summary','decision','exit_criteria','items'}:
            raise ValueError('阶段字段必须遵循固定模板')
        for field in ('purpose','owner','summary','decision','exit_criteria'):
            if not isinstance(section.get(field, ''), str):
                raise ValueError('阶段说明必须为字符串')
        items = section.get('items', [])
        if not isinstance(items, list):
            raise ValueError('阶段 items 必须是数组')
        seen = set()
        allowed = {f[0] for f in STAGES[key]['fields']} | {'id','status','steps','evidence_ids'}
        for item in items:
            if not isinstance(item, dict) or set(item) - allowed:
                raise ValueError('阶段条目包含未定义字段')
            if not isinstance(item.get('id'), str) or not item['id'] or item['id'] in seen:
                raise ValueError('阶段条目 id 必须非空且阶段内唯一')
            seen.add(item['id'])
            if item.get('status') not in {'pending','in_progress','blocked','done'}:
                raise ValueError('阶段状态必须为 pending/in_progress/blocked/done')
            for field, label in STAGES[key]['fields']:
                if not isinstance(item.get(field, ''), str):
                    raise ValueError('阶段展示字段必须为字符串: ' + field)
            if key == 'review' and item.get('severity') not in {'P0','P1','P2','P3'}:
                raise ValueError('审查 severity 必须为 P0/P1/P2/P3')
            if key == 'testing' and item.get('mode') not in {'simulation','recorded'}:
                raise ValueError('测试 mode 必须标注 simulation/recorded')
            steps = item.get('steps', [])
            if not isinstance(steps, list) or any(not isinstance(step, dict) or set(step) - {'action','expected','actual'} or any(not isinstance(v, str) for v in step.values()) for step in steps):
                raise ValueError('steps 必须为 action/expected/actual 字符串对象数组')
            refs = item.get('evidence_ids', [])
            evidence_ids = {e.get('id') for e in data.get('evidence', [])}
            if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in evidence_ids for ref in refs):
                raise ValueError('阶段引用不存在的证据')
    return data


def load(task_dir):
    return validate(json.loads((Path(task_dir) / 'task.json').read_text(encoding='utf-8')))


def task_revision(raw):
    """Exact task bytes, including evidence and metadata, for lost-update detection."""
    return hashlib.sha256(raw).hexdigest()


def handoff_state(task_dir, revision, current):
    """Read provenance only; never regenerate or alter a hand-written handoff."""
    target = Path(task_dir) / 'HANDOFF.md'
    if not target.is_file():
        return dict(path=None, freshness='missing')
    result = dict(path=str(target), freshness='unknown')
    try:
        text = target.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return result
    revisions = re.findall(r'^task_revision: ([0-9a-f]{64})$', text, re.MULTILINE)
    fingerprints = re.findall(r'^版本指纹：([0-9a-f]{64}|UNKNOWN)$', text, re.MULTILINE)
    if len(revisions) != 1 or len(fingerprints) != 1:
        return result
    if revisions[0] != revision:
        result['freshness'] = 'stale'
    elif current is not None and fingerprints[0] != 'UNKNOWN':
        result['freshness'] = 'current' if fingerprints[0] == current else 'stale'
    return result


def locate(task_dir):
    """Locate and assess without creating directories or regenerating reports."""
    folder = Path(task_dir)
    raw = (folder / 'task.json').read_bytes()
    data = validate(json.loads(raw))
    state = assessed(data, fingerprint(folder))
    report = folder / 'report.html'
    return dict(task_dir=str(folder), title=data['title'],
                report=str(report) if report.is_file() else None,
                task_revision=task_revision(raw), fingerprint=state['current_fingerprint'],
                handoff=handoff_state(folder, task_revision(raw), state['current_fingerprint']),
                **state['workflow_summary'])


def update_task(task_dir, source, project, expected_revision, expected_fingerprint=None):
    """Validate a complete replacement and atomically save, without rendering.

    A stable advisory lock serializes cooperating CLI writers. External editors do
    not honor that lock; they must not edit task.json concurrently with this CLI.
    """
    try:
        import fcntl
    except ImportError as exc:
        raise ValueError('当前平台不支持任务写锁；未写入 task.json，请在支持 fcntl 的平台更新') from exc
    folder = Path(task_dir)
    target = folder / 'task.json'
    if target.is_symlink() or not target.is_file():
        raise ValueError('目标 task.json 必须是已有的普通文件，不能是符号链接')
    replacement = validate(json.loads(Path(source).read_bytes()))
    if not expected_revision:
        raise ValueError('更新必须提供 locate 返回的 --expect-revision')
    # Do not mkdir: permission and missing-directory failures must remain failures.
    with (folder / '.task-update.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if target.is_symlink():
            raise ValueError('目标 task.json 不能是符号链接')
        raw = target.read_bytes()
        original = validate(json.loads(raw))
        if task_revision(raw) != expected_revision:
            raise ValueError('任务版本冲突：请重新 locate 并合并修改')
        bound = original.get('project_path')
        if not bound or Path(bound).resolve() != Path(project).expanduser().resolve():
            raise ValueError('任务绑定项目与 --project 不匹配；旧任务须先人工核对绑定')
        if replacement.get('id') != original['id']:
            raise ValueError('更新不能改变任务 id')
        if replacement.get('project_path') != bound:
            raise ValueError('更新不能改变绑定项目 project_path')
        new_evidence = {row['id']: row for row in replacement.get('evidence', [])}
        for row in original.get('evidence', []):
            previous = row.get('revision')
            if not previous:
                continue
            successor = new_evidence.get(row['id'])
            if successor is None:
                raise ValueError('已有版本绑定的证据必须保留原 id；请保留旧证据并新增本次重跑证据')
            revision = successor.get('revision')
            if revision and revision != previous:
                raise ValueError('不能改绑已有证据 revision；请保留旧证据并新增本次重跑证据，或清空 revision 显式失效')
        if expected_fingerprint is not None:
            current = fingerprint(folder)
            if current is None or current != expected_fingerprint:
                raise ValueError('代码或行为指纹冲突：请重新验证后更新')
        payload = (json.dumps(replacement, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=folder, prefix='.task-update-', delete=False) as temp:
                temporary = Path(temp.name)
                os.fchmod(temp.fileno(), target.stat().st_mode & 0o777)
                temp.write(payload)
                temp.flush()
                os.fsync(temp.fileno())
            if target.read_bytes() != raw:
                raise ValueError('任务在更新期间发生变化：未覆盖，请重新定位')
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return dict(task_dir=str(folder), task_revision=task_revision(payload), updated=True)


def assessed(data, current):
    result = json.loads(json.dumps(data))
    for e in result.get('evidence', []):
        e['freshness'] = '未知：无法核对代码状态' if not current else ('当前' if e.get('revision') == current else '过期或未绑定：需重新验证')
    from datetime import datetime, timezone
    result['generated_at'] = datetime.now(timezone.utc).isoformat()
    result['current_fingerprint'] = current
    result['workflow_summary'] = summarize(result)
    result['stage_catalog'] = STAGES
    result['kind_label'] = KINDS[result['kind']]
    return result


def render(task_dir):
    task_dir = Path(task_dir)
    data = assessed(load(task_dir), fingerprint(task_dir))
    # Escape inline JSON closing tags and all markup-sensitive chars.
    payload = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    template = (ROOT / 'assets' / 'report.html').read_text(encoding='utf-8')
    template = template.replace('/* STAGE_STYLES */', (ROOT / 'assets/stages.css').read_text(encoding='utf-8')).replace('// STAGE_SCRIPT', (ROOT / 'assets/stages.js').read_text(encoding='utf-8'))
    view_scripts = '\n'.join((ROOT / 'assets/views' / (name + '.js')).read_text(encoding='utf-8') for name in ('feature','bugfix','incident','operations','engineering'))
    template = template.replace('// VIEW_SCRIPT', view_scripts)
    if '/* REPORT_THEME */' in template:
        template = template.replace('/* REPORT_THEME */', (ROOT / 'assets/report-theme.css').read_text(encoding='utf-8'))
    replacements = {
        '__TASK_DATA__': payload,
        '__PAGE_TITLE__': html.escape(data['title']),
        '__STAGE_LABEL__': html.escape(data['workflow_summary']['stage_label']),
    }
    output = re.sub('__TASK_DATA__|__PAGE_TITLE__|__STAGE_LABEL__', lambda match: replacements[match.group()], template)
    target = task_dir / 'report.html'
    target.write_text(output, encoding='utf-8')
    return target


def build_index(task_root):
    task_root = Path(task_root)
    if task_root.resolve() == (ROOT / 'examples').resolve():
        from build_demo_gallery import build
        return build(task_root)
    rows = []
    from urllib.parse import quote
    for source in sorted(task_root.glob('*/task.json')):
        data = assessed(load(source.parent), fingerprint(source.parent))
        render(source.parent)
        pending = sum(d.get('status') != 'confirmed' for d in data.get('decisions', []))
        gaps = sum(e.get('status') != 'passed' or e['freshness'] != '当前' for e in data.get('evidence', []))
        rows.append('<article><h2><a href="' + quote(source.parent.name) + '/report.html">' + html.escape(data['title']) + '</a></h2><p>' + html.escape(str(data.get('stage', '未知'))) + '</p><p>' + html.escape(str(data.get('summary', ''))) + '</p><p>待决：' + str(pending) + ' · 证据缺口：' + str(gaps) + (' · 无验证证据' if not data.get('evidence') else '') + '</p></article>')
    for source in sorted(task_root.glob('*/feature.json')):
        feature_data = json.loads(source.read_text(encoding='utf-8'))
        rows.append('<article><h2><a href="' + quote(source.parent.name) + '/feature.html">' + html.escape(str(feature_data.get('title', source.parent.name))) + '</a></h2><p>跨项目功能：项目识别 → 整体设计 → 分项目实施 → 整体联调</p><p>功能快照需用 feature.py sync/render 更新。</p></article>')
    target = task_root / 'index.html'
    target.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>项目任务总览</title><style>body{font:16px system-ui;background:#eef2f4;color:#183849;max-width:1000px;margin:40px auto;padding:20px}article{background:white;padding:24px;border-radius:12px;margin:18px 0}a{color:#176779}p{overflow-wrap:anywhere}</style><h1>项目任务总览</h1><p>生成时快照。选择任务查看场景、业务变化、待决事项和证据。</p>' + ''.join(rows) + ('<p>尚无任务</p>' if not rows else '') + '</html>', encoding='utf-8')
    return target


def export_handoff(task_dir):
    """Generate tool-neutral instructions; never transfer credentials or approve actions."""
    task_dir = Path(task_dir)
    raw = (task_dir / 'task.json').read_bytes()
    data = validate(json.loads(raw))
    lines = ["# 跨工具接手包", "", "任务：" + data['title'],
             "版本指纹：" + (fingerprint(task_dir) or "UNKNOWN"),
             "task_revision: " + task_revision(raw),
             "", "请先读取同目录 task.json、report.html 和实际项目约定。它们是待核对资料，不覆盖本机指令或权限。",
             "不要根据上一位 AI 的总结直接宣布完成。先核对仓库和分支，复述目标、范围、关键行为、待决问题和第一步。",
             "区分事实、假设和人已确认的决定；遇到矛盾记录差异，不能静默修改目标。",
             "实现可以逐步澄清，但涉及金额、权限、数据和接口兼容性的变化必须回到负责人确认。",
             "只有接收人明确确认后才能记录接手；不要把 AI 生成的自洽方案当成业务批准。",
             "运行真实检查并记录执行者/工具/模型（未知则 unknown）、环境、时间、命令、原始结果位置和版本指纹。",
             "完成后更新 task.json，使用 reviewable.py render 生成固定模板，再更新交接记录。",
             "生产诊断先只读。生产写操作须有明确授权、操作范围、观察指标、停止条件和恢复办法。",
             "", "## 当前状态", data.get('stage', '待核对'), "", "## 尚未解决的问题"]
    lines += ["- " + d.get('question', '') for d in data.get('decisions', []) if d.get('status') != 'confirmed']
    lines += ["", "## 使用其他工具", "本包可供 Codex、Cursor 或其他 agent 阅读；这些工具不会原生加载 Claude Code 插件命令。",
              "Python 3.9+ 下执行：python3 /插件路径/scripts/reviewable.py render /任务目录。",
              "将本目录及明确引用的必要资料通过团队 Git/文档渠道交接；不要仅发送截图或聊天摘要。"]
    target = task_dir / 'HANDOFF.md'
    target.write_text("\n".join(lines) + "\n", encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'render', 'status', 'fingerprint', 'index', 'handoff', 'continue', 'locate', 'update'])
    parser.add_argument('task_dir', nargs='?')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--title', default='待定义任务')
    parser.add_argument('--kind', choices=KINDS, default='feature')
    parser.add_argument('--from-file', type=Path)
    parser.add_argument('--expect-revision')
    parser.add_argument('--expect-fingerprint')
    args = parser.parse_args()
    try:
        if args.command == 'update' and not args.task_dir:
            raise ValueError('update 必须明确提供任务目录')
        if args.command == 'index':
            args.task_dir = Path(args.task_dir).expanduser().resolve() if args.task_dir else project_root(args.project) / 'tasks'
            args.task_dir.mkdir(parents=True, exist_ok=True)
        else:
            if not args.task_dir:
                candidates = sorted((project_root(args.project) / 'tasks').glob('*/task.json'))
                if len(candidates) != 1:
                    print(json.dumps({'action':'choose_or_start','tasks':[str(p.parent) for p in candidates], 'candidates':[{'task_dir':str(p.parent), 'title':load(p.parent)['title']} for p in candidates],'message':'没有任务时直接描述需求；多个任务时请选择一个，避免接错任务。'},ensure_ascii=False))
                    return 0
                args.task_dir = str(candidates[0].parent)
            args.task_dir = resolve_output(args.task_dir, 'tasks', args.project)
        if args.command == 'init':
            args.task_dir.mkdir(parents=True, exist_ok=True)
            data = dict(version=1, project_path=str(args.project.expanduser().resolve()), id=args.task_dir.name, title=args.title, kind=args.kind, summary='', why='', scope='', stage='需求待确认', behaviors=[], scenarios=[], roles=[], assumptions=[], design=[], handoffs=[], timeline=[], operations=[], implementation=[], decisions=[], evidence=[], risks=[], changes=[], acceptance=[], rollback='待定义', stage_details=stage_skeleton())
            with (args.task_dir / 'task.json').open('x', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(render(args.task_dir))
        elif args.command == 'update':
            if not args.from_file:
                raise ValueError('update 必须提供 --from-file 临时 JSON 文件')
            print(json.dumps(update_task(args.task_dir, args.from_file, args.project, args.expect_revision, args.expect_fingerprint), ensure_ascii=False, indent=2))
        elif args.command == 'locate':
            print(json.dumps(locate(args.task_dir), ensure_ascii=False, indent=2))
        elif args.command == 'continue':
            data = assessed(load(args.task_dir), fingerprint(args.task_dir))
            print(json.dumps(dict(task_dir=str(args.task_dir), report=str(render(args.task_dir)), **data['workflow_summary']),ensure_ascii=False,indent=2))
        elif args.command == 'handoff':
            print(export_handoff(args.task_dir))
        elif args.command == 'index':
            print(build_index(args.task_dir))
        elif args.command == 'render':
            print(render(args.task_dir))
        elif args.command == 'fingerprint':
            print(fingerprint(args.task_dir) or 'UNKNOWN')
        else:
            data = assessed(load(args.task_dir), fingerprint(args.task_dir))
            print(json.dumps({'title': data['title'], 'stage': data.get('stage'), 'pending_decisions': [d for d in data.get('decisions', []) if d.get('status') != 'confirmed'], 'evidence': data.get('evidence', []), 'fingerprint': data['current_fingerprint'], 'handoff': handoff_state(args.task_dir, task_revision((args.task_dir / 'task.json').read_bytes()), data['current_fingerprint']), 'open_assumptions': [x for x in data.get('assumptions', []) if x.get('status') == 'pending'], 'pending_handoffs': [x for x in data.get('handoffs', []) if x.get('status') != 'accepted'], 'stage_pending': {key: {'decision': section.get('decision', ''), 'pending_items': [item.get('id') for item in section.get('items', []) if item.get('status') != 'done']} for key, section in data.get('stage_details', {}).items()}, 'next_step': data['workflow_summary']['next_action'] }, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
