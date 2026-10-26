#!/usr/bin/env python3
"""Read-only source observations for business logic and data-flow explanations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

MODES = {'business_logic', 'data_flow'}
SOURCE_KEYS = {'id', 'project_path', 'path', 'line_start', 'line_end', 'sha256'}
MAX_SOURCE_BYTES = 16 * 1024 * 1024


class SourceReadError(ValueError):
    """Invalid readable bytes retain their observed version without being text evidence."""
    def __init__(self, message, raw):
        super().__init__(message)
        self.observed_sha256 = hashlib.sha256(raw).hexdigest()


def _text(value, label, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(label + ' 必须为' + ('字符串' if empty else '非空字符串'))


def _relative(value):
    _text(value, 'source.path')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or value in {'.', ''} or '\\' in value:
        raise ValueError('source.path 必须为项目内相对文件路径，不能越界')
    return path


def _projects(task):
    values = [task.get('project_path')] + task.get('analysis', {}).get('project_paths', [])
    return {str(Path(p).expanduser().resolve()) for p in values if isinstance(p, str) and Path(p).is_absolute()}


def validate(task):
    data = task.get('analysis', {})
    if not isinstance(data, dict) or set(data) - {'mode', 'question', 'conclusion', 'project_paths', 'sources', 'steps', 'rules', 'mappings', 'findings', 'gaps'}:
        raise ValueError('analysis 只能包含固定分析字段')
    if not isinstance(data.get('mode', 'business_logic'), str) or data.get('mode', 'business_logic') not in MODES:
        raise ValueError('analysis.mode 必须为 business_logic/data_flow')
    for key in ('question', 'conclusion'):
        _text(data.get(key, ''), 'analysis.' + key, empty=True)
    projects = data.get('project_paths', [])
    if not isinstance(projects, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in projects):
        raise ValueError('analysis.project_paths 必须为显式绝对项目路径数组')
    if len({str(Path(p).resolve()) for p in projects}) != len(projects):
        raise ValueError('analysis.project_paths 不能重复')
    known_projects = _projects(task)
    sources = data.get('sources', [])
    if not isinstance(sources, list):
        raise ValueError('analysis.sources 必须为数组')
    ids = set()
    for row in sources:
        if not isinstance(row, dict) or set(row) != SOURCE_KEYS:
            raise ValueError('analysis.sources 字段必须为 id/project_path/path/line_start/line_end/sha256')
        _text(row.get('id'), 'source.id')
        if row['id'] in ids:
            raise ValueError('source.id 必须唯一')
        ids.add(row['id'])
        root = row.get('project_path')
        if not isinstance(root, str) or not Path(root).is_absolute() or str(Path(root).resolve()) not in known_projects:
            raise ValueError('source.project_path 必须属于任务或显式额外项目范围')
        _relative(row.get('path'))
        start, end = row.get('line_start'), row.get('line_end')
        if type(start) is not int or type(end) is not int or start < 1 or end < start:
            raise ValueError('source 行范围必须为有效正整数')
        if not isinstance(row.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
            raise ValueError('source.sha256 必须为读取时文件字节 SHA256')
    shapes = {
        'steps': {'id', 'title', 'description', 'source_ids'},
        'rules': {'id', 'condition', 'outcome', 'source_ids'},
        'mappings': {'id', 'from', 'to', 'transformation', 'source_ids'},
        'findings': {'id', 'classification', 'statement', 'source_ids'},
        'gaps': {'id', 'description', 'next_action'},
    }
    for key, fields in shapes.items():
        rows = data.get(key, [])
        if not isinstance(rows, list):
            raise ValueError('analysis.' + key + ' 必须为数组')
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or (set(row) - {'disposition'} if key == 'gaps' else set(row)) != fields:
                raise ValueError('analysis.' + key + ' 条目必须使用固定字段：' + '/'.join(sorted(fields)))
            for field in fields - {'source_ids'}:
                _text(row.get(field), key + '.' + field)
            if row['id'] in seen:
                raise ValueError('analysis.' + key + ' id 必须唯一')
            seen.add(row['id'])
            if key == 'gaps':
                if row.get('disposition', 'investigate') not in ('investigate', 'needs_input', 'out_of_scope'):
                    raise ValueError('gap.disposition 必须为 investigate/needs_input/out_of_scope')
                continue
            refs = row['source_ids']
            if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in ids for ref in refs) or len(refs) != len(set(refs)):
                raise ValueError('analysis.' + key + ' 引用了不存在或重复的来源')
            if key == 'findings' and row['classification'] not in {'fact', 'inference', 'unknown'}:
                raise ValueError('finding.classification 必须为 fact/inference/unknown')
            if (key != 'findings' or row['classification'] == 'fact') and not refs:
                raise ValueError('分析事实、步骤、规则与映射必须引用源码来源；推断/未知请明确分类')
    return data


def _read(project, path):
    root = Path(project).expanduser()
    if not root.is_absolute():
        raise ValueError('project 必须为明确的绝对项目路径')
    root = root.resolve()
    relative = _relative(path)
    candidate = root / relative
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError('源码路径或符号链接越出声明项目，未读取') from exc
    if not root.is_dir() or not resolved.is_file():
        raise FileNotFoundError('源码文件或项目不可访问')
    if resolved.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('源码文件超过16MiB，需缩小分析材料范围')
    with resolved.open('rb') as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('源码文件超过16MiB，需缩小分析材料范围')
    if b'\0' in raw:
        raise SourceReadError('来源必须为文本源码文件', raw)
    try:
        lines = raw.decode('utf-8-sig').splitlines()
    except UnicodeError as exc:
        raise SourceReadError('来源不是可读取的 UTF-8 文本', raw) from exc
    return root, relative, raw, lines


def source(project, path, identity='S1', line_start=1, line_end=None):
    _text(identity, 'source.id')
    root, relative, raw, lines = _read(project, path)
    end = len(lines) if line_end is None else line_end
    if type(line_start) is not int or type(end) is not int or line_start < 1 or end < line_start or end > len(lines):
        raise ValueError('源码行范围不存在或文件为空')
    return dict(id=identity, project_path=str(root), path=relative.as_posix(), line_start=line_start,
                line_end=end, sha256=hashlib.sha256(raw).hexdigest())


def assess(task):
    data = validate(task)
    result = dict(sources=[], source_counts=dict.fromkeys(('current', 'stale', 'unavailable', 'invalid'), 0),
                  gap_count=len(data.get('gaps', [])), gap_counts=dict.fromkeys(('investigate','needs_input','out_of_scope'),0), inference_count=0, unknown_count=0, documented=False, missing_fields=[])
    for row in data.get('sources', []):
        status, reason = 'current', '源码字节和行范围与记录一致；不代表运行验证'
        observed_sha, observed_lines = None, None
        try:
            _, _, raw, lines = _read(row['project_path'], row['path'])
            observed_sha, observed_lines = hashlib.sha256(raw).hexdigest(), len(lines)
            if row['line_end'] > observed_lines:
                status, reason = 'invalid', '记录的源码行范围已不存在，需重新分析'
            elif observed_sha != row['sha256']:
                status, reason = 'stale', '源码字节已变化，需重新分析；没有自动改绑记录'
        except OSError as exc:
            status, reason = 'unavailable', '源码不可读取：' + str(exc)
        except ValueError as exc:
            if isinstance(exc, SourceReadError):
                observed_sha = exc.observed_sha256
            status, reason = 'invalid', str(exc)
        result['sources'].append(dict(row, status=status, reason=reason, current_sha256=observed_sha, current_line_count=observed_lines))
        result['source_counts'][status] += 1
    for row in data.get('gaps', []):
        result['gap_counts'][row.get('disposition', 'investigate')] += 1
    for row in data.get('findings', []):
        if row['classification'] in {'inference', 'unknown'}:
            result[row['classification'] + '_count'] += 1
    for key in ('question', 'conclusion'):
        if not data.get(key, '').strip():
            result['missing_fields'].append(key)
    if not data.get('sources'):
        result['missing_fields'].append('sources')
    if not data.get('steps'):
        result['missing_fields'].append('steps')
    result['documented'] = not result['missing_fields'] and all(s['status'] == 'current' for s in result['sources'])
    return result


def summarize(task):
    data = task.get('analysis', {})
    assessment = task.get('analysis_assessment') or assess(task)
    bad = [s for s in assessment['sources'] if s['status'] != 'current']
    blockers = []
    owner = 'AI'
    if not data.get('question', '').strip():
        step, title, reason = 'analysis_scope', 'AI 先明确要解释的问题、入口与只读范围。', '尚未记录分析问题。'
    elif bad:
        step, title, reason = 'analysis_refresh', 'AI 只读重查来源 ' + '、'.join(s['id'] for s in bad[:3]) + '，保留旧记录并说明结论适用范围。', '部分来源过期、不可读取或行范围无效；不能当作当前事实。'
        blockers = [dict(type='analysis_source', id=s['id'], summary=s['reason'], severity='information', source='analysis.sources') for s in bad]
        if (all(s['status'] == 'unavailable' for s in bad) and not assessment['gap_counts']['investigate']
                and assessment['gap_counts']['needs_input']):
            gap = next(g for g in data.get('gaps', []) if g.get('disposition') == 'needs_input')
            step, owner = 'analysis_input', '你'
            title, reason = '需要补充分析材料：' + gap['next_action'], '来源不可读取；' + gap['description'] + '。保留缺口，不视为已整理或验收。'
    elif assessment['gap_counts']['investigate']:
        gap = next(g for g in data.get('gaps', []) if g.get('disposition', 'investigate') == 'investigate')
        step, title, reason = 'analysis_investigate', 'AI 继续只读调查：' + gap['next_action'], '仍有已声明可继续调查的断点，不能把它当作工作已完成。'
    elif assessment['gap_counts']['needs_input']:
        gap = next(g for g in data.get('gaps', []) if g.get('disposition') == 'needs_input')
        step, owner = 'analysis_input', '你'
        title, reason = '需要补充分析材料：' + gap['next_action'], gap['description'] + '；这是补材料，不是验收或批准。'
    elif not assessment['documented']:
        step, title, reason = 'analyze', 'AI 继续只读追踪入口、规则或数据转换，补齐源码依据与结论。', '分析材料尚缺：' + '、'.join(assessment['missing_fields'])
    elif assessment['gap_count'] and assessment['gap_counts']['out_of_scope'] == assessment['gap_count']:
        step, owner = 'analysis_partial', 'none'
        title, reason = '分析材料已整理；本次范围外的未知与断点已保留。', '这是范围内的静态说明，不代表范围外链路已核实。'
    elif assessment['unknown_count']:
        step, title, reason = 'analysis_investigate', 'AI 需说明未知项还能调查什么、缺少什么材料或是否属于范围外。', '未知不等于材料已齐全，也不能自动停工。'
    elif assessment['gap_count']:
        step, owner = 'analysis_partial', 'none'
        title, reason = '分析材料已整理；仍有未覆盖断点，按已说明范围阅读。', '断点或未知项不代表链路已跑通，不自动要求验收或外部访问授权。'
    else:
        step, owner = 'analysis_documented', 'none'
        title, reason = '源码分析已整理，当前无需人工验收或开发动作。', '来源版本已核对；静态说明不等于运行验证或业务正确性证明。'
    compact = dict(mode=data.get('mode', 'business_logic'), question=data.get('question', ''), conclusion=data.get('conclusion', ''),
                   source_counts=assessment['source_counts'], gap_count=assessment['gap_count'],
                   inference_count=assessment['inference_count'], unknown_count=assessment['unknown_count'],
                   missing_fields=assessment['missing_fields'],
                   gaps=[dict(g, disposition=g.get('disposition', 'investigate')) for g in data.get('gaps', [])[:3]])
    verification = dict(covered_behavior_ids=[], missing_behavior_ids=[], current_unresolved_evidence_ids=[],
                        historical_evidence_count=0, current_source_counts=dict(claim=0, parsed_result=0, invalid=0),
                        current_status_counts=dict(passed=0, failed=0, blocked=0, not_run=0, unknown=0), historical_status_counts={})
    return dict(analysis_summary=compact, visible_sections=[], page_purpose='解释现有业务逻辑或数据链路，区分事实、推断与断点',
                read_first='问题与结论，再看流程、规则/映射和源码依据', human_action='仅在理解有偏差或需补充分析范围时反馈；不要求人工验收',
                step=step, focus_stage='analysis', requested_focus_stage=task.get('focus_stage'), stage_label={'analysis_scope':'明确分析问题','analyze':'只读分析中','analysis_refresh':'来源待重查','analysis_partial':'分析已整理 · 含断点','analysis_documented':'源码分析已整理','analysis_investigate':'继续只读调查','analysis_input':'待补分析材料'}[step],
                action_owner=owner, next_action=title, primary_action=dict(owner=owner, title=title, reason=reason, kind=step),
                blockers=blockers, review_warnings=[], verification=verification, human_verification={}, acceptance_verification={},
                visible_result=data.get('conclusion') or task.get('summary') or '尚未形成分析结论', missing_verification_count=0,
                stale_evidence_count=0, unresolved_current_evidence_count=0, pending_decision_count=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['source'])
    parser.add_argument('--id', default='S1')
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--path', required=True)
    parser.add_argument('--line-start', type=int, default=1)
    parser.add_argument('--line-end', type=int)
    args = parser.parse_args()
    try:
        print(json.dumps(source(args.project, args.path, args.id, args.line_start, args.line_end), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    from filelock import utf8_stdio
    utf8_stdio()
    sys.exit(main())
