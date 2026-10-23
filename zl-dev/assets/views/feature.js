/* Feature views share typography, but each phase has a different reading path. */
function renderFeatureView(parent, task, ui) {
  const {el, card, list, text, show} = ui;
  const stage = (task.workflow_summary || {}).focus_stage || task.focus_stage || 'requirements';
  parent.dataset.layout = 'feature-' + stage;
  const items = key => ((task.stage_details || {})[key] || {}).items || [];
  const block = (title, body) => card(parent, title, body);
  function stories(title) {
    const box = block(title, '场景说明只代表记录的预期；执行结果见验证证据。');
    const scenarios = task.scenarios || [];
    if (!scenarios.length) { box.append(el('p', '尚未记录具体场景。')); return; }
    const selector = el('select'); selector.setAttribute('aria-label', '选择业务场景');
    scenarios.forEach((s, i) => { const option = el('option', s.title || '场景 ' + (i + 1)); option.value = i; selector.append(option); });
    const flow = el('ol', undefined, 'scene-timeline');
    function draw() { flow.replaceChildren(); const s = scenarios[Number(selector.value)]; flow.append(el('li', '性质：' + text(s.kind))); (s.steps || []).forEach(step => { const row = el('li'); row.append(el('strong', text(step.action)), el('p', '预期：' + text(step.result || step.expected))); flow.append(row); }); }
    selector.onchange = draw; box.append(selector, flow); draw();
  }
  function questions() {
    const box = block('现在需要确认', '以下事项没有答案时，不能假定已经同意。');
    const pending = (task.decisions || []).filter(d => d.status !== 'confirmed');
    if (!pending.length) box.append(el('p', '尚未记录待决事项；这不代表所有业务边界已确认。'));
    pending.forEach(d => { const item = el('div', undefined, 'scene-action'); item.append(el('strong', text(d.question)), el('p', '建议：' + text(d.recommendation))); box.append(item); });
    const btn = el('button', '填写并复制反馈'); btn.onclick = () => show('decisions'); box.append(btn);
  }
  function changes() {
    const box = block('业务前后对照', '按实际记录核对行为变化。');
    (task.behaviors || []).forEach(b => { const row = el('article', undefined, 'scene-grid'); row.append(el('p', text(b.id) + ' · 原来：' + text(b.before)), el('p', '现在要求：' + text(b.after)), el('p', '状态：' + text(b.status))); box.append(row); });
    if (!(task.behaviors || []).length) box.append(el('p', '尚未记录行为变化。'));
  }
  function evidence() {
    const box = block('真实验证记录', '模拟、未执行及待核验结果不能当作通过。');
    (task.evidence || []).forEach(e => { const row = el('article'); row.append(el('strong', text(e.status)+' · '+text(e.freshness)), el('p', text(e.summary)), el('p', '执行命令：' + text(e.command)), el('p', '版本：' + text(e.revision))); box.append(row); });
    if (!(task.evidence || []).length) box.append(el('p', '没有执行证据。'));
    items('testing').forEach(t => card(box, text(t.case), '预期：' + text(t.expected) + '\n实际：' + text(t.actual) + '\n模式：' + text(t.mode) + '；环境：' + text(t.environment)));
  }
  if (stage === 'requirements') {
    parent.classList.add('scene-requirements');
    block('用户遇到了什么问题', task.why || task.summary);
    items('requirements').forEach(r => block('原话与理解', '原始描述：' + text(r.original) + '\n当前理解：' + text(r.interpretation) + '\n边界：' + text(r.boundary)));
    stories('用一个具体故事理解需求'); block('本次范围', task.scope); questions();
  } else if (stage === 'solution') {
    parent.classList.add('scene-solution'); stories('完整使用流程');
    const grid = el('div', undefined, 'scene-grid'); parent.append(grid);
    const designs = task.design || [];
    designs.forEach(d => card(grid, text(d.title), text(d.description) + '\n取舍：' + text(d.tradeoffs) + '\n状态：' + text(d.status)));
    items('solution').forEach(d => card(grid, text(d.name), '路径：' + text(d.flow) + '\n实现方式：' + text(d.approach) + '\n收益：' + text(d.benefit) + '\n代价：' + text(d.cost) + '\n风险：' + text(d.risk)));
    if (!designs.length && !items('solution').length) card(grid, '候选方案尚未记录', '需要先分析现有系统，不自动补造方案。');
    block('边界与不做的事情', task.scope); questions();
  } else if (stage === 'testing' || stage === 'acceptance') {
    parent.classList.add('scene-acceptance');
    list(parent, '请先亲自操作这些步骤', task.acceptance || []);
    items('acceptance').forEach(a => block(text(a.scenario), '操作：' + text(a.instruction) + '\n预期：' + text(a.expected) + '\n实际：' + text(a.actual) + '\n核验结果：' + text(a.result)));
    stories('选择要验收的业务路径'); evidence(); questions();
  } else {
    parent.classList.add('scene-delivery');
    const records = items('implementation');
    records.forEach(r => block(text(r.planned), '实际：' + text(r.actual) + '\n偏差：' + text(r.deviation) + '\n影响：' + text(r.impact) + '\n源码：' + text(r.source)));
    (task.implementation || []).forEach(r => block('实际改动', typeof r === 'string' ? r : text(r.title)+'：'+text(r.description)+'；代码位置：'+text(r.files)));
    if (!records.length && !(task.implementation || []).length) block('尚无实施记录', '设计方案不能作为实现完成的证据。');
    changes();
    items('review').forEach(r => block(text(r.severity) + ' · ' + text(r.finding), '位置：' + text(r.source) + '\n修复：' + text(r.fix) + '\n复查：' + text(r.recheck)));
    list(parent, '接下来需要验证', task.acceptance || []); evidence(); questions();
  }
}
