#!/usr/bin/env python3
"""Render offline examples and their scenario gallery (Python standard library)."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote

import feature
import reviewable
from workflow import STAGE_LABELS

ROOT = Path(__file__).resolve().parents[1]


def build(examples=None):
    folder = Path(examples or ROOT / 'examples').resolve()
    entries = []
    for source in sorted([*folder.rglob('task.json'), *folder.rglob('feature.json')]):
        data = json.loads(source.read_text(encoding='utf-8'))
        demo = data.get('demo', {})
        is_feature = source.name == 'feature.json'
        page = feature.render(source.parent) if is_feature else reviewable.render(source.parent)
        kind = data.get('kind', 'feature')
        fallback = {'incident': '运维', 'operations': '运维', 'bugfix': '排障', 'performance': '工程', 'migration': '工程', 'upgrade': '工程', 'refactor': '工程'}
        category = demo.get('category', fallback.get(kind, '需求'))
        stage = data.get('focus_stage') or data.get('workflow', {}).get('focus_stage', '')
        entries.append(dict(
            id=data.get('id', source.parent.name), title=data['title'], category=category,
            purpose=demo.get('purpose', data.get('summary', '了解整体流程、边界与当前动作')),
            read_order=demo.get('read_order', ['先看目标与当前动作', '再看场景和关键证据']),
            phase=STAGE_LABELS.get(stage, data.get('stage', '跨项目整体设计' if is_feature else '场景示例')),
            href=quote(page.relative_to(folder).as_posix(), safe='/'),
            simulation=True, order=demo.get('order'),
            mode='跨项目功能' if is_feature else '项目任务',
        ))
    payload = json.dumps(entries, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    template = (ROOT / 'assets/demo-gallery.html').read_text(encoding='utf-8')
    target = folder / 'index.html'
    target.write_text(template.replace('__DEMO_DATA__', payload), encoding='utf-8')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('examples', nargs='?', type=Path)
    args = parser.parse_args()
    print(build(args.examples))
