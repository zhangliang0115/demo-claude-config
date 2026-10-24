"""Deterministic derived-state provenance; reads local snapshots without executing HTML."""
import hashlib
import json
from html.parser import HTMLParser

START = '<!-- ZL-DEV:GENERATED:START -->'
END = '<!-- ZL-DEV:GENERATED:END -->'


def assessment_revision(data):
    clean = {key: value for key, value in data.items()
             if key not in {'generated_at', 'provenance', 'task_revision', 'assessment_revision'}}
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


class PayloadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.payloads = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == 'task-data':
            self.active = True
            self.payloads.append('')

    def handle_data(self, data):
        if self.active:
            self.payloads[-1] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = False


def read_payload(text):
    parser = PayloadParser()
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


def atomic_write(target, raw):
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
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
