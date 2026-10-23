"""Evidence-derived current action; no automatic human approval."""
STAGE_LABELS = {'requirements':'理解需求','solution':'确定方案','implementation':'开发中','testing':'验证中','acceptance':'待人工核验','operations':'排查与运维','handoff':'上下文交接','review':'审查中','release':'发布准备'}

def summarize(data):
    behaviors = data.get('behaviors', [])
    evidence = data.get('evidence', [])
    pending = [d for d in data.get('decisions', []) if d.get('status') != 'confirmed']
    covered = {ref for e in evidence if e.get('status') == 'passed' and e.get('freshness') == '当前' for ref in e.get('behavior_ids', [])}
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
    elif missing:
        step, focus = 'verify', 'testing'
        ids = [b['id'] for b in behaviors if b['id'] not in covered]
        action = 'AI 验证 '+ '、'.join(ids[:3])+' 的实际结果；失败先修复，过期证据重跑。'
    else:
        step, focus, owner = 'accept', 'acceptance', '你'
        checks = data.get('acceptance', [])
        action = '请亲自核验：'+(checks[0] if checks else '关键用户路径；AI 需先给出可操作步骤。')
    if data.get('kind') in {'incident','operations'} and step != 'accept':
        focus = 'operations'
    explicit = data.get('focus_stage')
    if explicit in STAGE_LABELS:
        focus = explicit
    return dict(step=step, focus_stage=focus, stage_label=STAGE_LABELS[focus], action_owner=owner, next_action=action, visible_result=data.get('summary') or data.get('why') or 'AI 尚未说明目标，需要先明确用户要解决的问题。', missing_verification_count=missing, stale_evidence_count=stale, pending_decision_count=len(pending))
