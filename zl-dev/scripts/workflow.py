"""Small, evidence-driven routing shared by CLI and human report."""
def summarize(data):
    behaviors = data.get('behaviors', [])
    evidence = data.get('evidence', [])
    pending = [d for d in data.get('decisions', []) if d.get('status') != 'confirmed']
    covered = {ref for e in evidence if e.get('status') == 'passed' and e.get('freshness') == '当前' for ref in e.get('behavior_ids', [])}
    missing = sum(b['id'] not in covered for b in behaviors)
    stale = sum(e.get('freshness') != '当前' for e in evidence)
    if not data.get('summary') or not behaviors:
        step, action = 'understand', 'AI 读取相关实现，给出最小行为例子与推荐方案；只集中询问影响结果的未知项。'
    elif pending:
        step, action = 'decide', '处理列出的业务决定；可独立进行的已授权工作继续推进。'
    elif not data.get('implementation'):
        step, action = 'implement', '按明确行为完成一个可验证的小切片，再运行实际检查。'
    elif missing:
        step, action = 'verify', '补齐缺少或过期的验证；失败则修复后重跑，不重新解释整个项目。'
    else:
        step, action = 'accept', '请人按验收步骤核验关键路径；当前证据覆盖不等于人工接受或上线完成。'
    return dict(step=step, next_action=action, visible_result=data.get('summary') or '尚未形成可核对的行为说明', missing_verification_count=missing, stale_evidence_count=stale, pending_decision_count=len(pending))
