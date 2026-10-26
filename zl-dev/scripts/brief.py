"""Bounded, read-only previews for locating work; never a new fact or decision."""

TEXT_LIMIT = 1200


def _text(data, key, source, truncated, unavailable, identity=False):
    value = data.get(key)
    if value is None:
        return ''
    if not isinstance(value, str):
        unavailable.append(source)
        return ''
    if not identity and len(value) > TEXT_LIMIT:
        truncated.append(source)
        return value[:TEXT_LIMIT]
    return value


def task_brief(data):
    """Return copied scalar previews without changing task facts or hashes."""
    truncated, unavailable = [], []
    result = {}
    for field in ('id', 'title', 'kind', 'project_path', 'summary', 'scope', 'why'):
        result[field] = _text(data, field, field, truncated, unavailable,
                              identity=field in {'id', 'kind', 'project_path'})
    if data.get('kind') == 'analysis':
        analysis = data.get('analysis')
        if analysis is not None and not isinstance(analysis, dict):
            unavailable.append('analysis')
        analysis = analysis if isinstance(analysis, dict) else {}
        for field in ('question', 'conclusion'):
            result['analysis_' + field] = _text(analysis, field, 'analysis.' + field,
                                               truncated, unavailable)
    result.update(truncated_fields=truncated, unavailable_fields=unavailable)
    return result


def feature_brief(data):
    """Explain the actual goal source; do not serialize arbitrary design objects."""
    truncated, unavailable = [], []
    result = {}
    for field in ('id', 'title', 'workspace_path', 'phase', 'scope'):
        result[field] = _text(data, field, field, truncated, unavailable,
                              identity=field in {'id', 'workspace_path'})
    design = data.get('design')
    if design is not None and not isinstance(design, dict):
        unavailable.append('design')
    design = design if isinstance(design, dict) else {}
    goal = _text(design, 'goal', 'design.goal', truncated, unavailable)
    has_goal = isinstance(design.get('goal'), str) and bool(design['goal'].strip())
    result['goal_source'] = 'design.goal' if has_goal else ''
    if not has_goal:
        goal = _text(data, 'summary', 'summary', truncated, unavailable)
        result['goal_source'] = 'summary' if isinstance(data.get('summary'), str) and data['summary'].strip() else ''
    missing = ['design.goal'] if not has_goal and 'design.goal' not in unavailable and 'design' not in unavailable else []
    result.update(goal=goal, truncated_fields=truncated, unavailable_fields=unavailable, missing_fields=missing)
    return result
