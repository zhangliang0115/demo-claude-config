"""Optional compact execution trace: what was actually chosen, loaded, run and observed.

Each entry is a declaration by the executing agent, not proof of execution. It is not part of
the behavior contract, so recording it never changes the code/behavior fingerprint.
"""

MAX_ENTRIES = 20
MAX_TEXT = 400
MAX_ITEMS = 12
SUMMARY_ENTRIES = 3
TEXT_FIELDS = ('at', 'actor', 'target', 'branch', 'reason', 'workspace', 'outcome')
LIST_FIELDS = ('guides_loaded', 'commands')
REQUIRED = ('at', 'actor', 'branch', 'outcome')
FORBIDDEN = ('\n', '\r', 'ZL-DEV:GENERATED')


def validate(rows):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('execution_trace 必须是对象数组')
    if len(rows) > MAX_ENTRIES:
        raise ValueError(f'execution_trace 最多保留 {MAX_ENTRIES} 条；请删除最旧的条目')
    for row in rows:
        unknown = set(row) - set(TEXT_FIELDS) - set(LIST_FIELDS)
        if unknown:
            raise ValueError('execution_trace 含未约定字段：' + '、'.join(sorted(unknown)))
        for field in REQUIRED:
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f'execution_trace.{field} 必须是非空字符串')
        for field in TEXT_FIELDS:
            value = row.get(field, '')
            if not isinstance(value, str) or len(value) > MAX_TEXT or any(x in value for x in FORBIDDEN):
                raise ValueError(f'execution_trace.{field} 必须是不超过 {MAX_TEXT} 字的单行字符串，不记录整段对话或生成区标记')
        for field in LIST_FIELDS:
            value = row.get(field, [])
            if (not isinstance(value, list) or len(value) > MAX_ITEMS
                    or any(not isinstance(x, str) or not x or len(x) > MAX_TEXT or any(f in x for f in FORBIDDEN) for x in value)):
                raise ValueError(f'execution_trace.{field} 必须是不超过 {MAX_ITEMS} 项的短字符串数组')


def summary(rows):
    """Latest entries only, for locate and handoff; full history stays in task.json."""
    rows = rows or []
    recent = [{k: row[k] for k in ('at', 'actor', 'branch', 'outcome', 'workspace') if row.get(k)}
              for row in rows[-SUMMARY_ENTRIES:]]
    return dict(total=len(rows), recent=recent, source='agent_declared_not_execution_proof')
