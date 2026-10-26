"""Deterministic derived-state provenance; reads local snapshots without executing HTML."""
import hashlib
import json
import html
import re
from pathlib import Path
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


# Increment the relevant protocol when changing Python rendering behavior. Asset
# bytes are observed independently; unrelated docs and plugin versions do not count.
RENDERER_PROTOCOL = {'task-data': 1, 'feature-data': 1}


def template_bundle(root, payload_id):
    root = Path(root)
    if payload_id not in RENDERER_PROTOCOL:
        raise ValueError('未知报告类型')
    main = 'assets/report.html' if payload_id == 'task-data' else 'assets/feature.html'
    assets = {main: (root / main).read_bytes()}
    if payload_id == 'task-data':
        for name in ['assets/stages.css', 'assets/stages.js'] + [
                'assets/views/' + kind + '.js' for kind in
                ('feature', 'bugfix', 'incident', 'operations', 'engineering', 'analysis')]:
            assets[name] = (root / name).read_bytes()
    if b'/* REPORT_THEME */' in assets[main]:
        assets['assets/report-theme.css'] = (root / 'assets/report-theme.css').read_bytes()
    manifest = dict(kind=payload_id, renderer_protocol=RENDERER_PROTOCOL[payload_id],
                    assets={name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(assets.items())})
    revision = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(payload_id=payload_id, revision=revision, assets=assets)


def render_report_bytes(data, bundle):
    """Pure rendering from one captured bundle; never reread mutable assets."""
    payload_id, assets = bundle['payload_id'], bundle['assets']
    payload = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    def asset(name):
        return assets['assets/' + name].decode('utf-8')
    if payload_id == 'task-data':
        template = asset('report.html').replace('/* STAGE_STYLES */', asset('stages.css')).replace('// STAGE_SCRIPT', asset('stages.js'))
        views = '\n'.join(asset('views/' + name + '.js') for name in
                          ('feature', 'bugfix', 'incident', 'operations', 'engineering', 'analysis'))
        template = template.replace('// VIEW_SCRIPT', views)
        replacements = {'__TASK_DATA__': payload, '__PAGE_TITLE__': html.escape(data['title']),
                        '__STAGE_LABEL__': html.escape(data['workflow_summary']['stage_label'])}
    else:
        template = asset('feature.html')
        replacements = {'__FEATURE_DATA__': payload, '__FEATURE_TITLE__': html.escape(data['title'])}
    if '/* REPORT_THEME */' in template:
        template = template.replace('/* REPORT_THEME */', asset('report-theme.css'))
    return re.sub('|'.join(re.escape(key) for key in replacements),
                  lambda match: replacements[match.group()], template).encode('utf-8')


def template_signature(data):
    revision = data.get('provenance', {}).get('template_revision')
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{64}', revision):
        raise ValueError('报告缺少有效模板版本')
    return revision


def current_report_bytes(raw, expected, bundle):
    """Validate both embedded versions and every generated HTML byte."""
    if raw is None:
        return False
    try:
        recorded = read_payload(raw.decode('utf-8'), bundle['payload_id'])
        return (report_signature(recorded, bundle['payload_id']) == expected
                and template_signature(recorded) == bundle['revision']
                and render_report_bytes(recorded, bundle) == raw)
    except (ValueError, UnicodeError, TypeError, KeyError):
        return False


def inspect_report(target, state, payload_id, root, known_code):
    """Pure read: template state is independent of business assessment versions."""
    target = Path(target)
    result = dict(path=str(target) if target.is_file() else None, freshness='missing',
                  reason='报告尚未生成', generated_at=None, template_revision=None,
                  current_template_revision=None, template_freshness='unknown')
    if not target.is_file():
        return result
    result.update(freshness='unknown', reason='报告缺少可核对的版本来源')
    try:
        raw = report_bytes(target)
        recorded = read_payload(raw.decode('utf-8'), payload_id)
        result['generated_at'] = recorded.get('generated_at')
        try:
            signature = report_signature(recorded, payload_id)
        except ValueError:
            fields = ('task_id','project_path','task_revision','current_fingerprint','assessment_revision') if payload_id == 'task-data' else ('feature_id','workspace_path','project_bindings','feature_revision','assessment_revision')
            source = recorded.get('provenance', {})
            copied = ('task_revision','current_fingerprint','assessment_revision') if payload_id == 'task-data' else ('id','workspace_path','projects','feature_revision','assessment_revision')
            if isinstance(source, dict) and source.get('version') == 1 and all(key in source for key in fields) and all(key in recorded for key in copied):
                result.update(freshness='stale', reason='报告快照内容或复制版本与来源不一致')
            return result
        expected = report_signature(state, payload_id)
        bundle = template_bundle(root, payload_id)
        result['current_template_revision'] = bundle['revision']
        try:
            result['template_revision'] = template_signature(recorded)
        except ValueError:
            result['reason'] = '旧报告缺少模板版本，需按阅读需要重新生成；不影响业务证据'
            if signature != expected:
                result.update(freshness='stale', reason='任务、代码或证据评估已变化，且报告缺少模板版本')
            return result
        result['template_freshness'] = 'current' if result['template_revision'] == bundle['revision'] else 'stale'
        if signature != expected:
            result.update(freshness='stale', reason='任务、代码或证据评估已变化，请按需重新生成报告')
        elif result['template_freshness'] != 'current':
            result.update(freshness='stale', reason='报告模板已变化；业务证据不因此失效，需按阅读需要更新页面')
        elif not current_report_bytes(raw, expected, bundle):
            result.update(freshness='stale', reason='报告页面与当前模板及嵌入快照不一致，需重新核对')
        elif not known_code:
            result['reason'] = '无法核对当前代码状态；模板一致不代表业务版本已核实'
        else:
            result.update(freshness='current', reason='记录、代码、证据评估与报告模板均与当前一致')
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        result['reason'] = '报告损坏、模板不可读取或版本来源无法核对'
    return result


def publish_report(target, raw, expected_report, candidate, snapshot, lock, payload_id,
                   reuse_matching=False, bundle=None, current_template=None, known_code=True):
    """Publish with fact, template and HTML comparisons under the fact writer lock."""
    expected = report_signature(candidate, payload_id)
    rendered = read_payload(raw.decode('utf-8'), payload_id)
    if report_signature(rendered, payload_id) != expected:
        raise ValueError('报告生成内容与输入快照不一致，未覆盖')
    revision = template_signature(candidate) if bundle is not None else None
    if bundle is not None and (revision != bundle['revision'] or not current_report_bytes(raw, expected, bundle)):
        raise ValueError('报告生成内容与模板版本不一致，未覆盖')

    def matching_report(value):
        return bool(known_code and bundle is not None and current_report_bytes(value, expected, bundle))

    with lock():
        def validate_source():
            if report_signature(snapshot(), payload_id) != expected:
                raise ValueError('报告生成冲突：任务、代码或证据评估已变化，未覆盖，请重新核对')
            if current_template is not None and current_template() != revision:
                raise ValueError('报告生成冲突：模板已变化，未覆盖，请重新核对')

        validate_source()
        actual = report_bytes(target)
        if actual != expected_report:
            if matching_report(actual):
                validate_source()
                if report_bytes(target) != actual:
                    raise ValueError('报告生成冲突：复用前报告已变化，未覆盖，请重新核对')
                return target
            raise ValueError('报告生成冲突：报告已由其他写入者更新，未覆盖，请重新核对')
        if reuse_matching and matching_report(actual):
            validate_source()
            if report_bytes(target) != actual:
                raise ValueError('报告生成冲突：复用前报告已变化，未覆盖，请重新核对')
            return target

        def before_replace():
            validate_source()
            if report_bytes(target) != expected_report:
                raise ValueError('报告生成冲突：发布前报告已变化，未覆盖，请重新核对')

        atomic_write(target, raw, before_replace=before_replace)
    return target
