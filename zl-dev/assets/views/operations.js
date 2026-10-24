/* Operations use a scoped runbook; the HTML never executes an operation. */
function renderOperationsView(parent, task, ui) {
  const {el, card, list, text, show} = ui;
  const origin = ui.evidenceOrigin || (typeof evidenceOrigin === 'function' ? evidenceOrigin : () => '来源等级未知；不能据此认定实际执行。');
  const focus = (task.workflow_summary || {}).focus_stage || task.focus_stage;
  const releasing = focus === 'release';
  const recovering = focus === 'acceptance';
  parent.classList.add('scene-operations');
  parent.append(el('h2', releasing ? '发布什么，何时停止' : recovering ? '是否恢复，依据是什么' : '操作什么，做到哪一步'));
  card(parent, '本次目标与范围', task.scope || task.summary);
  parent.append(el('p', '计划、授权、实际执行和恢复结果分别核对；页面不执行任何运维命令。', 'warning'));
  const operations = task.operations || [];
  const targets = el('section', undefined, 'scene-grid');
  operations.forEach(op => {
    const target = card(targets, op.environment || '目标环境尚未记录', op.impact);
    target.append(el('p', '负责人：' + text(op.owner)), el('p', '授权：' + text(op.authorization)));
  });
  if (!operations.length) card(targets, '目标与授权未知', '尚未记录运维目标、影响范围和执行授权。');
  parent.append(targets);

  const results = el('section', undefined, 'card');
  results.append(el('h2', recovering ? '恢复核验优先' : '执行后如何判定结果'));
  operations.forEach(op => {
    results.append(el('h3', text(op.id)), el('p', '实际结果：' + text(op.result)), el('p', '恢复 / 结果核验：' + text(op.verification)));
  });
  (task.evidence || []).forEach(e => {
    results.append(el('p', text(e.id) + ' · ' + text(e.status) + ' · ' + text(e.freshness)), el('p', text(e.summary)), el('p', origin(e), 'evidence-origin'), el('p', '来源：' + text(e.source)));
  });
  if (!operations.length && !(task.evidence || []).length) results.append(el('p', '没有执行或恢复证据。'));
  if (['testing', 'acceptance'].includes(focus)) {
    const checks = (((task.stage_details || {}).acceptance || {}).items || []);
    list(results, '人工核验', checks.length ? checks.map(item => [item.scenario, item.instruction, item.expected].filter(Boolean).join('；')) : task.acceptance || []);
  }
  if (recovering) parent.append(results);

  if (releasing) {
    const release = el('section', undefined, 'card'); release.append(el('h2', '放行条件逐项核对'));
    const items = ((task.stage_details || {}).release || {}).items || [];
    items.forEach(item => {
      release.append(el('h3', text(item.check || item.id)), el('p', '环境：' + text(item.environment)), el('p', '授权：' + text(item.authorization)), el('p', '观察指标：' + text(item.metric)), el('p', '实际：' + text(item.actual)), el('p', '状态：' + text(item.status)));
    });
    if (!items.length) release.append(el('p', '发布检查尚未记录，不能视为已具备放行条件。'));
    parent.append(release);
  }
  const runbook = el('section'); runbook.append(el('h2', '按顺序执行的操作记录'));
  const sequence = el('ol', undefined, 'scene-timeline');
  operations.forEach(op => {
    const item = el('li', undefined, 'card');
    item.append(el('h3', text(op.type || op.id)), el('span', text(op.status), 'badge'), el('p', '已观察：' + text(op.observation)), el('p', '待验证假设：' + text(op.hypothesis)), el('p', '计划：' + text(op.action)), el('p', '实际：' + text(op.result)));
    sequence.append(item);
  });
  if (!operations.length) sequence.append(el('li', '尚无操作步骤；不要把计划视作已执行。'));
  runbook.append(sequence); parent.append(runbook);
  const safety = el('section', undefined, 'scene-grid');
  list(safety, '何时立即停止', operations.map(op => text(op.id) + '：' + text(op.stop_condition)));
  list(safety, '如何回退或恢复', operations.map(op => text(op.id) + '：' + text(op.rollback)));
  card(safety, '整体恢复办法', task.rollback); parent.append(safety);
  if (!recovering) parent.append(results);
  list(parent, '尚未解决的风险', task.risks || []);
  const next = card(parent, '现在的动作', (task.workflow_summary || {}).next_action || '先确认目标、授权和停止条件，实际执行后记录结果与核验证据。');
  next.classList.add('scene-action');
  if ((task.decisions || []).some(item => item.status !== 'confirmed')) {
    const button = el('button', '查看待确认的操作决策'); button.type = 'button'; button.onclick = () => show('decisions'); next.append(button);
  }
}
