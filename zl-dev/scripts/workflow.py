"""Evidence-derived current action; no automatic human approval."""
STAGE_LABELS = {'requirements':'理解需求','solution':'确定方案','implementation':'开发中','testing':'验证中','acceptance':'待人工核验','operations':'排查与运维','handoff':'上下文交接','review':'审查中','release':'发布准备'}

def reading_guide(kind, focus):
    """Reading intent only: never infer completion or verification results."""
    specialty = {
        'bugfix': ('理解故障如何出现、修复准备阻断什么', '复现步骤，再对照原因与证据', '核对问题是否与你遇到的一致，确认修复后的关键路径'),
        'incident': ('掌握生产影响、当前处置和恢复依据', '影响范围与当前动作，再看现场事实', '确认操作范围与停止条件，核对恢复记录'),
        'operations': ('核对运维目标、执行顺序和恢复条件', '目标环境与操作步骤，再看实际结果', '确认授权范围，并核对执行与恢复证据'),
        'refactor': ('理解结构调整及必须保持的行为', '结构变化与行为不变量，再看回归依据', '核对对外行为是否保持，检查剩余风险'),
        'performance': ('比较同等条件下的性能目标与测量依据', '基线、测量条件和结果，再看代价', '核对比较是否公平，以及正确性是否受到影响'),
        'migration': ('理解数据转换范围及恢复路径', '转换规则与异常数据，再看核对记录', '确认数据边界、预演证据与可恢复性'),
        'upgrade': ('理解版本兼容性和升级范围', '兼容性差异与试点，再看行为对比', '确认接受的变化，并核对未验证项'),
    }
    stages = {
        'requirements': ('确认这件事解决什么问题及边界', '用户故事与具体例子，再看范围', '纠正理解偏差，补充尚未确定的业务规则'),
        'solution': ('判断整体方案是否符合目标', '完整流程与方案比较，再看取舍', '确认关键边界和方案选择；具体待决问题见下方'),
        'implementation': ('理解本轮实际改动及影响', '实施切片与实际变化，再看偏差', '检查改动是否符合约定，指出遗漏的使用场景'),
        'testing': ('检查验收条件对应的验证依据', '测试场景与结果，再看未覆盖项', '核对证据来源；未执行项不能当作通过'),
        'acceptance': ('按具体步骤核验本轮交付', '人工操作步骤、预期结果和已有证据', '亲自核验关键路径，填写实际结果并复制反馈'),
        'handoff': ('确认交接内容与接手范围', '交付版本、职责和接收者复述', '指出理解差异并确认未决问题的负责人'),
        'review': ('理解改动风险及审查发现', '问题成立条件、代码位置和修复情况', '判断剩余风险是否可接受，核对关键证据'),
        'release': ('核对发布范围、顺序和恢复条件', '发布检查项与停止条件，再看恢复方案', '核对版本和环境，确认发布条件'),
    }
    values = specialty.get(kind, stages.get(focus, stages['requirements']))
    return dict(zip(('page_purpose', 'read_first', 'human_action'), values))

PHASE_SECTIONS = {
    'requirements':['scenarios','behavior','decisions','stage-views'],
    'solution':['scenarios','design','decisions','stage-views'],
    'implementation':['implementation','behavior','decisions','stage-views'],
    'review':['implementation','evidence','decisions','stage-views'],
    'testing':['scenarios','evidence','stage-views'],
    'acceptance':['evidence','decisions','stage-views'],
    'operations':['operations','evidence','decisions','stage-views'],
    'release':['operations','evidence','decisions','stage-views'],
    'handoff':['handoffs','behavior','decisions','stage-views'],
}

def _status_counts(evidence):
    # Each record belongs to exactly one bucket; unfamiliar legacy values stay visible.
    counts = dict.fromkeys(('passed', 'failed', 'blocked', 'not_run', 'unknown'), 0)
    for item in evidence:
        status = item.get('status')
        counts[status if status in counts else 'unknown'] += 1
    return counts


def human_verification(data):
    """Classify explicit human records without inferring approval from prose."""
    current = data.get('current_fingerprint')
    stages = {}
    for stage in ('acceptance', 'release'):
        items = data.get('stage_details', {}).get(stage, {}).get('items', [])
        value = {key: [] for key in ('current_pass_ids', 'current_fail_ids', 'current_blocked_ids', 'pending_ids', 'historical_ids')}
        for item in items:
            identity = item.get('id', '')
            revision = item.get('reviewed_revision')
            same = bool(current) and bool(revision) and revision == current
            explicit = item.get('result_status')
            trusted = same and item.get('reviewer_kind') == 'human'
            if trusted and explicit in {'pass', 'fail', 'blocked'}:
                value[{'pass': 'current_pass_ids', 'fail': 'current_fail_ids', 'blocked': 'current_blocked_ids'}[explicit]].append(identity)
            else:
                value['pending_ids'].append(identity)
            if current and revision and not same:
                value['historical_ids'].append(identity)
        value['all_current_passed'] = bool(items) and len(value['current_pass_ids']) == len(items)
        stages[stage] = value
    selected = 'release' if data.get('focus_stage') == 'release' and data.get('stage_details', {}).get('release', {}).get('items') else 'acceptance'
    return dict(stage=selected, **stages[selected], by_stage=stages)


def summarize(data):
    behaviors = data.get('behaviors', [])
    evidence = data.get('evidence', [])
    current = [e for e in evidence if e.get('freshness') == '当前']
    historical = [e for e in evidence if e.get('freshness') != '当前']
    source_counts = dict.fromkeys(('claim', 'parsed_result', 'invalid'), 0)
    for item in current:
        source = item.get('verification_source', 'claim')
        source_counts[source if source in source_counts else 'invalid'] += 1
    pending = [d for d in data.get('decisions', []) if d.get('status') != 'confirmed']
    current_unresolved = [e for e in current if e.get('status') in {'failed', 'blocked', 'not_run'}]
    disputed = {ref for e in current_unresolved for ref in e.get('behavior_ids', [])}
    covered = {ref for e in current if e.get('status') == 'passed' for ref in e.get('behavior_ids', [])} - disputed
    covered_ids = [b['id'] for b in behaviors if b['id'] in covered]
    missing_ids = [b['id'] for b in behaviors if b['id'] not in covered]
    evidence_by_id = {e.get('id'): e for e in evidence}
    blockers = [dict(type='evidence', id=e.get('id', ''), summary=e.get('title') or e.get('summary') or '当前检查尚未通过', severity='blocking', source='evidence') for e in current_unresolved]
    review_blockers, review_warnings = [], []
    for finding in data.get('stage_details', {}).get('review', {}).get('items', []):
        refs = finding.get('evidence_ids', [])
        rechecked = bool(refs) and all(
            ref in evidence_by_id and evidence_by_id[ref].get('freshness') == '当前'
            and evidence_by_id[ref].get('status') == 'passed'
            and not disputed.intersection(evidence_by_id[ref].get('behavior_ids', []))
            for ref in refs)
        resolved = finding.get('status') == 'done' and rechecked
        if resolved:
            continue
        entry = dict(type='review', id=finding.get('id', ''), summary=finding.get('finding') or '审查问题缺少有效复查依据', severity=finding.get('severity', 'P3'), source='stage_details.review')
        if finding.get('severity') in {'P0', 'P1'}:
            review_blockers.append(entry)
        else:
            review_warnings.append(entry)
    blockers.extend(review_blockers)
    human = human_verification(data)
    human_blockers = []
    for stage, results in human['by_stage'].items():
        for status, field in (('fail', 'current_fail_ids'), ('blocked', 'current_blocked_ids')):
            for identity in results[field]:
                human_blockers.append(dict(type='human_feedback', id=identity, stage=stage,
                    summary=('人工核验不符合预期：' if status == 'fail' else '人工记录无法核验：') + stage + ':' + identity,
                    severity='blocking', source='stage_details.' + stage, result_status=status))
    blockers.extend(human_blockers)
    owner = 'AI'
    # Existing evidence and high-risk findings outrank reading preferences and business decisions.
    if current_unresolved:
        step, focus = 'verify', 'testing'
        action = 'AI 先解决当前检查 '+ '、'.join(str(e.get('id', '未编号')) for e in current_unresolved[:3])+'；修复后重新验证，不能以其他通过记录覆盖失败。'
        reason = '存在当前失败、受阻或尚未执行的检查。'
    elif review_blockers:
        step, focus = 'review', 'review'
        action = 'AI 先处理高风险审查问题 '+ '、'.join(str(b['id']) for b in review_blockers[:3])+'，并补充当前有效且无矛盾的通过证据。'
        reason = 'P0/P1 问题尚未解决或缺少有效复查证据。'
    elif human_blockers:
        step, focus = 'human_feedback', human_blockers[0]['stage']
        action = 'AI 先处理人工退回或无法核验项 ' + '、'.join(b['stage'] + ':' + b['id'] for b in human_blockers[:3]) + '，查明原因并修复或准备核验条件，再安排复核。'
        reason = '当前版本已有明确的人工不符合预期或无法核验记录，不能继续要求人重复同一项。'
    elif not data.get('summary') or not behaviors:
        step, focus = 'understand', 'requirements'
        action = 'AI 先查清“'+data.get('title','当前需求')+'”的现状，给出一个具体输入与预期结果，再推进明确的工作。'
        reason = '目标或可观察行为尚未明确。'
    elif pending:
        step, focus, owner = 'decide', 'solution', '你'
        first = pending[0]
        action = '请确认：'+first.get('question','待确认的业务规则')+'；建议：'+first.get('recommendation','AI 尚未给出建议，请先补充依据。')
        reason = '关键业务规则需要负责人确认。'
    elif not data.get('implementation'):
        step, focus = 'implement', 'implementation'
        action = 'AI 实现“'+behaviors[0].get('after',data.get('title','当前功能'))+'”的最小切片，并验证相关行为。'
        reason = '行为已明确，尚无实际实施记录。'
    elif missing_ids:
        step, focus = 'verify', 'testing'
        action = 'AI 验证 '+ '、'.join(missing_ids[:3])+' 的实际结果；失败先修复，过期证据重跑。'
        reason = '部分约定行为缺少当前通过证据。'
    elif human['all_current_passed']:
        step, focus, owner = 'human_reviewed', human['stage'], '你'
        action = '本版人工核验通过已记录；请负责人决定后续安排或是否放行，不自动发布或推进阶段。'
        reason = '本阶段全部条目均有当前版本的明确人工通过记录；记录来源仍需对照回传依据。'
    else:
        step, focus, owner = 'accept', human['stage'], '你'
        structured = data.get('stage_details', {}).get(human['stage'], {}).get('items', [])
        if structured:
            item = next((x for x in structured if x.get('id') not in human['current_pass_ids']), structured[0])
            check = '；'.join(x for x in (item.get('scenario'), item.get('instruction')) if x)
        else:
            checks = data.get('acceptance', [])
            check = checks[0] if checks else ''
        action = '请亲自核验：'+(check or '关键用户路径；AI 需先给出可操作步骤。')
        reason = ('已有通过记录，部分尚无脚本解析，仍需负责人亲自核验。'
                  if source_counts['claim'] else '当前行为证据已覆盖，仍需负责人亲自核验。')
    blockers.extend(dict(type='decision', id=d.get('id', ''), summary=d.get('question') or '业务规则待确认', severity='decision', source='decisions') for d in pending)
    if data.get('implementation'):
        blockers.extend(dict(type='verification', id=ref, summary='行为缺少当前无矛盾的通过证据', severity='blocking', source='behaviors') for ref in missing_ids)
    explicit = data.get('focus_stage')
    if not current_unresolved and not review_blockers and not human_blockers:
        if data.get('kind') in {'incident','operations'} and step not in {'accept', 'human_reviewed'}:
            focus = 'operations'
        if explicit in STAGE_LABELS:
            focus = explicit
    verification = dict(covered_behavior_ids=covered_ids, missing_behavior_ids=missing_ids,
        current_unresolved_evidence_ids=[e.get('id', '') for e in current_unresolved],
        historical_evidence_count=len(historical), current_source_counts=source_counts, current_status_counts=_status_counts(current),
        historical_status_counts=_status_counts(historical))
    guide = reading_guide(data.get('kind'), focus)
    if step == 'human_reviewed':
        guide.update(page_purpose='了解本版已记录的人工核验结论与后续安排', read_first='已记录的核验结果，再看剩余风险与后续决定', human_action='确认后续安排或是否放行；补充意见用于更正记录，不要求重复核验')
    elif step == 'human_feedback':
        guide['human_action'] = '等待 AI 处理退回原因或准备核验条件，完成后再复核'
    stage_label = STAGE_LABELS[focus]
    if step == 'human_reviewed':
        stage_label = '发布核验已记录' if human['stage'] == 'release' else '人工核验已记录'
    elif step == 'human_feedback':
        stage_label = '人工反馈 · 待 AI 处理'
    return dict(visible_sections=PHASE_SECTIONS[focus], **guide,
        step=step, focus_stage=focus, requested_focus_stage=explicit, stage_label=stage_label,
        action_owner=owner, next_action=action, primary_action=dict(owner=owner, title=action, reason=reason, kind=step),
        blockers=blockers, review_warnings=review_warnings, verification=verification, human_verification=human,
        visible_result=data.get('summary') or data.get('why') or 'AI 尚未说明目标，需要先明确用户要解决的问题。',
        missing_verification_count=len(missing_ids), stale_evidence_count=len(historical),
        unresolved_current_evidence_count=len(current_unresolved), pending_decision_count=len(pending))
