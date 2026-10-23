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

def summarize(data):
    behaviors = data.get('behaviors', [])
    evidence = data.get('evidence', [])
    pending = [d for d in data.get('decisions', []) if d.get('status') != 'confirmed']
    covered = {ref for e in evidence if e.get('status') == 'passed' and e.get('freshness') == '当前' for ref in e.get('behavior_ids', [])}
    current_unresolved = [e for e in evidence if e.get('freshness') == '当前' and e.get('status') in {'failed', 'blocked', 'not_run'}]
    disputed = {ref for e in current_unresolved for ref in e.get('behavior_ids', [])}
    covered -= disputed
    missing = sum(b['id'] not in covered for b in behaviors)
    stale = sum(e.get('freshness') != '当前' for e in evidence)
    owner = 'AI'
    if not data.get('summary') or not behaviors:
        step, focus = 'understand', 'requirements'
        action = 'AI 先查清“'+data.get('title','当前需求')+'”的现状，给出一个具体输入与预期结果，再推进明确的工作。'
    elif pending:
        step, focus, owner = 'decide', 'solution', '你'
        first = pending[0]
        action = '请确认：'+first.get('question','待确认的业务规则')+'；建议：'+first.get('recommendation','AI 尚未给出建议，请先补充依据。')
    elif not data.get('implementation'):
        step, focus = 'implement', 'implementation'
        action = 'AI 实现“'+behaviors[0].get('after',data.get('title','当前功能'))+'”的最小切片，并验证相关行为。'
    elif missing or current_unresolved:
        step, focus = 'verify', 'testing'
        ids = [b['id'] for b in behaviors if b['id'] not in covered]
        action = 'AI 验证 '+ ('、'.join(ids[:3]) if ids else '未解决的当前检查')+' 的实际结果；失败先修复，过期证据重跑。'
    else:
        step, focus, owner = 'accept', 'acceptance', '你'
        checks = data.get('acceptance', [])
        action = '请亲自核验：'+(checks[0] if checks else '关键用户路径；AI 需先给出可操作步骤。')
    if data.get('kind') in {'incident','operations'} and step != 'accept':
        focus = 'operations'
    explicit = data.get('focus_stage')
    if explicit in STAGE_LABELS:
        focus = explicit
    return dict(visible_sections=PHASE_SECTIONS[focus], **reading_guide(data.get('kind'), focus), step=step, focus_stage=focus, stage_label=STAGE_LABELS[focus], action_owner=owner, next_action=action, visible_result=data.get('summary') or data.get('why') or 'AI 尚未说明目标，需要先明确用户要解决的问题。', missing_verification_count=missing, stale_evidence_count=stale, unresolved_current_evidence_count=len(current_unresolved), pending_decision_count=len(pending))
