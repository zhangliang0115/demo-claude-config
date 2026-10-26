"""Bounded explanations of fingerprint changes; never an evidence-validity override."""
import hashlib
import json
import os
from pathlib import Path
import re

MAX_FILES = 1000
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_CHANGED_PATHS = 10
HEX = re.compile(r'[0-9a-f]{64}')


def display_path(raw):
    return raw.decode('utf-8', 'surrogateescape').encode('utf-8', 'backslashreplace').decode('utf-8')


def source_part(raw, kind, digest):
    return raw + b'\0' + kind.encode('ascii') + b'\0' + bytes.fromhex(digest)


def valid_context(value, fingerprint=None):
    """Check binding and stored metadata; hashes are not identity authentication."""
    try:
        keys = {'version','fingerprint','head','root_path','project_path','contract_sha256','source_digest','file_count','files_truncated','files'}
        if not isinstance(value, dict) or set(value) != keys or type(value['version']) is not int or value['version'] != 1:
            return False
        if not isinstance(value['fingerprint'], str) or not HEX.fullmatch(value['fingerprint']):
            return False
        if fingerprint is not None and value['fingerprint'] != fingerprint:
            return False
        for key in ('root_path','project_path'):
            if not isinstance(value[key], str) or not Path(value[key]).is_absolute() or os.path.normpath(value[key]) != value[key]:
                return False
        if Path(value['root_path']) != Path(value['project_path']) and Path(value['root_path']) not in Path(value['project_path']).parents:
            return False
        if not isinstance(value['head'], str) or (value['head'] != 'UNBORN' and not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', value['head'])):
            return False
        if value['contract_sha256'] is not None and (not isinstance(value['contract_sha256'], str) or not HEX.fullmatch(value['contract_sha256'])):
            return False
        if not isinstance(value['source_digest'], str) or not HEX.fullmatch(value['source_digest']):
            return False
        if type(value['file_count']) is not int or value['file_count'] < 0 or type(value['files_truncated']) is not bool:
            return False
        files = value['files']
        if not isinstance(files, list) or len(files) > MAX_FILES or value['file_count'] < len(files):
            return False
        if value['files_truncated'] != (value['file_count'] != len(files)):
            return False
        if len(json.dumps(files, ensure_ascii=True).encode()) > MAX_MANIFEST_BYTES:
            return False
        digest, previous = hashlib.sha256(), None
        for item in files:
            if not isinstance(item, dict) or set(item) != {'path','path_bytes_hex','kind','sha256'}:
                return False
            raw = bytes.fromhex(item['path_bytes_hex'])
            if not raw or b'\0' in raw or raw.startswith(b'/') or b'..' in raw.split(b'/') or (previous is not None and raw <= previous):
                return False
            if item['path'] != display_path(raw) or item['kind'] not in {'file','link','missing'} or not isinstance(item['sha256'], str) or not HEX.fullmatch(item['sha256']):
                return False
            previous = raw
            digest.update(source_part(raw, item['kind'], item['sha256']))
        if not value['files_truncated'] and digest.hexdigest() != value['source_digest']:
            return False
        return True
    except (ValueError, TypeError, KeyError, UnicodeError):
        return False


def _normalize(value, prefix=''):
    """Relative POSIX path under the Git root, or None when it cannot be compared safely."""
    text = value.strip().replace('\\', '/')
    if not text or text.startswith('/') or re.match(r'[A-Za-z]:/', text):
        return None
    while text.startswith('./'):
        text = text[2:]
    parts = [part for part in text.split('/') if part not in ('', '.')]
    if not parts or '..' in parts:
        return None
    joined = '/'.join(parts)
    return (prefix + '/' + joined).strip('/') if prefix else joined


def declared_files(implementation, prefix=''):
    """Paths this task declares as changed, relative to the Git root; a claim used only for explanation.

    Paths may be written relative to the Git root or to the project directory (prefix). A trailing
    slash declares a directory. Absolute, parent-relative and non-string values are ignored.
    """
    declared = set()
    rows = implementation if isinstance(implementation, list) else []
    for row in rows:
        files = row.get('files') if isinstance(row, dict) else None
        values = [files] if isinstance(files, str) else (files if isinstance(files, list) else [])
        for value in values:
            if not isinstance(value, str):
                continue
            directory = value.strip().replace('\\', '/').endswith('/')
            for base in {'', prefix}:
                path = _normalize(value, base)
                if path:
                    declared.add(path + '/' if directory else path)
    return declared


def _declared(path, declared):
    return path in declared or any(entry.endswith('/') and path.startswith(entry) for entry in declared)


def attribute(changed, complete, declared):
    """Compare observed paths with this task's declared files. Never widens evidence validity."""
    if not changed or not declared:
        return 'unknown', []
    inside = [p for p in changed if _declared(p, declared)]
    outside = [p for p in changed if not _declared(p, declared)]
    if not outside:
        # 明细截断时未见路径无法判断，不声称全部属于本任务
        return ('declared_by_this_task' if complete else 'unknown'), []
    return ('outside_declared' if not inside else 'partially_declared'), outside[:MAX_CHANGED_PATHS]


def explain(evidence, current, current_context=None, baseline=None, source=None, declared=None):
    source = source or {}
    revision = evidence.get('revision')
    baseline_state = 'legacy_missing' if baseline is None else ('captured' if valid_context(baseline, revision) else 'invalid')
    result = dict(state='unknown', baseline=baseline_state, reason_codes=[], reasons=[], changed_paths=[],
                  changed_path_count=None, paths_truncated=False, behavior_ids=list(evidence.get('behavior_ids', [])),
                  recheck='', attribution='unknown', undeclared_paths=[], dependency_scope='whole_repository_conservative')
    def reason(code, text):
        result['reason_codes'].append(code); result['reasons'].append(text)
    if source.get('verification_source') == 'invalid':
        result['state'] = 'invalid_receipt'
        reason('receipt_invalid', '回执或原始日志不可采信：' + str(source.get('verification_error') or '未能核对执行来源')[:600])
    elif not current:
        reason('unknown_current', '当前项目或代码状态无法核对，不能判断旧证据是否适用。')
    elif not revision:
        result['state'] = 'unbound'
        reason('unbound', '这条证据没有绑定代码/行为版本。')
    elif revision == current:
        result['state'] = 'current'
        reason('fingerprint_matches', '综合代码/行为指纹与当前一致；这不是运行真实性或业务覆盖证明。')
    else:
        result['state'] = 'stale'
        if baseline_state == 'captured' and valid_context(current_context, current):
            if baseline['root_path'] != current_context['root_path'] or baseline['project_path'] != current_context['project_path']:
                reason('location_changed', '实际项目或 Git 根位置与验证时不同；不能把旧证据迁到新工作区。')
            if baseline['head'] != current_context['head']:
                reason('head_changed', 'Git HEAD 与验证时不同；即使文件看似一致也保留原版本失效规则。')
            if baseline['contract_sha256'] != current_context['contract_sha256']:
                reason('contract_changed', '本任务的范围、行为或验收等约定摘要已变化。')
            if baseline['source_digest'] != current_context['source_digest']:
                reason('source_changed', 'Git 非忽略源码集合或内容与验证时不同；尚未证明业务行为是否变化。')
                left = {x['path_bytes_hex']: x for x in baseline['files']}
                right = {x['path_bytes_hex']: x for x in current_context['files']}
                complete = not baseline['files_truncated'] and not current_context['files_truncated']
                changed = []
                for key in sorted(set(left) | set(right)):
                    a, b = left.get(key), right.get(key)
                    if a is None or b is None:
                        if complete:
                            changed.append((b or a)['path'] + ('（进入观察集合）' if a is None else '（移出观察集合）'))
                    elif (a['kind'], a['sha256']) != (b['kind'], b['sha256']):
                        changed.append(b['path'] + ('（类型变化）' if a['kind'] != b['kind'] else '（内容变化）'))
                result['changed_paths'] = changed[:MAX_CHANGED_PATHS]
                bare = [path.rsplit('（', 1)[0] for path in changed]
                try:
                    prefix = Path(current_context['project_path']).relative_to(current_context['root_path']).as_posix()
                    declared_paths = declared_files(declared, '' if prefix == '.' else prefix) if declared else set()
                    result['attribution'], result['undeclared_paths'] = attribute(bare, complete, declared_paths)
                except (TypeError, ValueError, AttributeError):
                    pass  # 归属只是解释；声明格式异常时保持 unknown，绝不影响证据判断
                result['changed_path_count'] = len(changed) if complete else None
                result['paths_truncated'] = not complete or len(changed) > MAX_CHANGED_PATHS
                if not complete:
                    reason('partial_file_manifest', '文件明细有截断，只展示可对照样本，不能将移出样本的路径当作删除。')
        if not result['reason_codes']:
            reason('unknown_change', '旧证据缺少可用分项基线，不能从综合哈希反推具体变化原因。')
    if baseline_state == 'invalid' and result['state'] != 'invalid_receipt':
        reason('invalid_baseline', '分项基线缺失有效绑定或结构，未用它判断变化。')
    if result['state'] == 'current':
        result['recheck'] = '保持原证据来源与覆盖判断；外部环境、忽略文件和依赖仍未由本指纹证明。'
    else:
        ids = '、'.join(str(x) for x in result['behavior_ids']) or '原声明覆盖范围（未记录行为关联）'
        result['recheck'] = '这条记录不能当本版依据；是否仍需重验以当前行动及验证缺口为准。若仍缺，核对源码/约定后按原关联范围检查：' + ids + '；已有有效覆盖不因旧记录单独重跑，路径清单不证明其他测试不受影响。'
    return result
