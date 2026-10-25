"""Deterministic derived-state provenance; reads local snapshots without executing HTML."""
import hashlib
import json
from html.parser import HTMLParser

START = '<!-- ZL-DEV:GENERATED:START -->'
END = '<!-- ZL-DEV:GENERATED:END -->'


def assessment_revision(data):
    clean = {key: value for key, value in data.items()
             if key not in {'generated_at', 'provenance', 'task_revision', 'feature_revision', 'assessment_revision'}}
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


class PayloadParser(HTMLParser):
    def __init__(self, payload_id='task-data'):
        super().__init__()
        self.payload_id = payload_id
        self.active = False
        self.payloads = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == self.payload_id:
            self.active = True
            self.payloads.append('')

    def handle_data(self, data):
        if self.active:
            self.payloads[-1] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = False


def read_payload(text, payload_id='task-data'):
    parser = PayloadParser(payload_id)
    parser.feed(text)
    if len(parser.payloads) != 1:
        raise ValueError('报告缺少唯一任务快照')
    value = json.loads(parser.payloads[0])
    if not isinstance(value, dict):
        raise ValueError('报告任务快照不是对象')
    return value


def generated_block(text):
    if text.count(START) != 1 or text.count(END) != 1:
        return None
    begin, finish = text.index(START), text.index(END)
    return text[begin + len(START):finish] if begin < finish else None


def atomic_write(target, raw, before_replace=None):
    """Replace a generated artifact only after a complete same-directory write.

    This protects existing contents on write/replace failure, not concurrent external edits.
    """
    import os
    from pathlib import Path
    import tempfile
    target = Path(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.zl-dev-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            if target.exists():
                os.fchmod(stream.fileno(), target.stat().st_mode & 0o777)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def report_bytes(target):
    """Capture an artifact version without following a generated-file symlink."""
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError('报告目标必须为普通文件，未覆盖')
    return target.read_bytes() if target.exists() else None


def report_signature(data, payload_id):
    """Validate the snapshot itself before comparing it with current facts."""
    try:
        provenance = data['provenance']
        if provenance['version'] != 1:
            raise ValueError('未知版本来源')
        if payload_id == 'task-data':
            expected = dict(task_id=data['id'], project_path=data.get('project_path'),
                            task_revision=data['task_revision'],
                            current_fingerprint=data['current_fingerprint'],
                            assessment_revision=data['assessment_revision'])
        elif payload_id == 'feature-data':
            bindings = sorted([dict(id=p['id'], path=p['path']) for p in data['projects']], key=lambda p: p['id'])
            expected = dict(feature_id=data['id'], workspace_path=data.get('workspace_path'),
                            project_bindings=bindings, feature_revision=data['feature_revision'],
                            assessment_revision=data['assessment_revision'])
        else:
            raise ValueError('未知报告类型')
        if (any(key not in provenance or provenance[key] != value for key, value in expected.items())
                or assessment_revision(data) != expected['assessment_revision']):
            raise ValueError('内容与版本来源不一致')
        return expected
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('报告快照缺少有效版本来源，未覆盖') from exc


def publish_report(target, raw, expected_report, candidate, snapshot, lock, payload_id,
                   reuse_matching=False):
    """Publish under the facts writer lock, with source and HTML comparisons.

    The lock serializes cooperating fact/report writers. Worktrees, child tasks,
    external editors and live services do not share it and may change afterwards.
    """
    expected = report_signature(candidate, payload_id)
    rendered = read_payload(raw.decode('utf-8'), payload_id)
    if report_signature(rendered, payload_id) != expected:
        raise ValueError('报告生成内容与输入快照不一致，未覆盖')

    def matching_report(value):
        if value is None:
            return False
        try:
            return report_signature(read_payload(value.decode('utf-8'), payload_id), payload_id) == expected
        except (ValueError, UnicodeError, TypeError):
            return False

    with lock():
        def validate_source():
            if report_signature(snapshot(), payload_id) != expected:
                raise ValueError('报告生成冲突：任务、代码或证据评估已变化，未覆盖，请重新核对')

        validate_source()
        actual = report_bytes(target)
        if actual != expected_report:
            if matching_report(actual):
                return target
            raise ValueError('报告生成冲突：报告已由其他写入者更新，未覆盖，请重新核对')
        # A supplied same-version snapshot must not replace a current page only
        # to move its display timestamp backwards (timestamps are not ordering).
        if reuse_matching and matching_report(actual):
            return target

        def before_replace():
            validate_source()
            if report_bytes(target) != expected_report:
                raise ValueError('报告生成冲突：发布前报告已变化，未覆盖，请重新核对')

        atomic_write(target, raw, before_replace=before_replace)
    return target
