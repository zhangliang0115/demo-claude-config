/* Incident workspace: impact -> live action -> observations -> recovery. */
function renderIncidentView(parent, task, ui) {
  const el = ui.el;
  const arr = value => Array.isArray(value) ? value : [];
  const text = value => value === undefined || value === null || value === '' ? '尚未采集' : typeof value === 'string' ? value : JSON.stringify(value);
  const ops = arr(task.operations);
  const focus = task.focus_stage || (task.workflow_summary || {}).focus_stage || 'operations';
  parent.classList.add('incident-workspace');
  const section = (title, cls) => { const node = el('section', undefined, cls || 'card'); node.append(el('h2', title)); parent.append(node); return node; };
  const field = (node, label, value) => { const line = el('p'); line.append(el('strong', label + '：'), el('span', text(value))); node.append(line); };
  const impact = section(focus === 'acceptance' ? '恢复核验现场' : focus === 'release' ? '生产变更与观察窗口' : '事件现场', 'card incident-impact');
  field(impact, '当前状态', task.stage);
  field(impact, '影响范围 / 环境', task.scope || ops.map(o => [o.environment, o.impact].filter(Boolean).join(' · ')).filter(Boolean).join('\n'));

  function actions() {
    const active = section('当前处置动作', 'card incident-actions');
    active.append(el('p', '每个动作单独核对授权、停止条件和恢复办法；本页面不执行生产操作。', 'muted'));
    if (!ops.length) active.append(el('p', '尚未采集处置动作。'));
    ops.forEach((o, i) => {
      const box = el('article', undefined, 'card');
      box.append(el('h3', text(o.id || '动作 ' + (i + 1)) + ' · ' + text(o.action)), el('span', text(o.status), 'badge'));
      [['owner', '执行人'], ['environment', '环境'], ['authorization', '授权范围'], ['stop_condition', '停止条件'], ['rollback', '恢复办法'], ['result', '执行结果'], ['verification', '效果验证']].forEach(([key, label]) => field(box, label, o[key]));
      active.append(box);
    });
  }
  function recovery() {
    const box = section('是否真的恢复', 'card incident-recovery');
    const evidence = arr(task.evidence);
    const stale = evidence.filter(e => e.stale === true || e.freshness === 'stale' || e.status === 'stale');
    const passed = evidence.filter(e => ['pass', 'passed'].includes(e.status) && !stale.includes(e));
    box.append(el('p', '记录 ' + evidence.length + ' 条 · 当前标记通过 ' + passed.length + ' 条 · 标记过期 ' + stale.length + ' 条。数量不构成恢复结论。'));
    const standards = arr(task.behaviors);
    if (!standards.length) field(box, '恢复标准', undefined);
    standards.forEach(b => field(box, '恢复标准 ' + text(b.id), b.after));
    if (!evidence.length) box.append(el('p', '尚未采集恢复证据。'));
    evidence.forEach(e => {
      const detail = el('details'); detail.append(el('summary', text(e.id) + ' · ' + text(e.status) + ' · ' + text(e.summary)));
      [['source', '来源'], ['executed_at', '执行时间'], ['revision', '代码版本'], ['command', '验证命令'], ['freshness', '新鲜度'], ['stale', '过期标记']].forEach(([key, label]) => field(detail, label, e[key]));
      const snippet = e.output || e.snippet || e.raw || e.log;
      detail.append(el('pre', text(snippet))); box.append(detail);
    });
    if (focus === 'acceptance') { const list = el('ol'); arr(task.acceptance).forEach(a => list.append(el('li', text(a)))); box.append(el('h3', '人工恢复核验'), list); }
    if (focus === 'release') field(box, '整体恢复 / 回滚办法', task.rollback);
  }
  if (focus === 'acceptance') { recovery(); actions(); } else { actions(); }
  const observations = section('现场事实与待验证假设', 'card incident-observations');
  const columns = el('div', undefined, 'stage-compare');
  const facts = el('article'), hypotheses = el('article');
  facts.append(el('h3', '已记录的观测')); hypotheses.append(el('h3', '假设，不等于根因'));
  if (!ops.length) facts.append(el('p', '尚未采集现场观测。'));
  ops.forEach(o => field(facts, text(o.id), o.observation));
  const guesses = [...ops.filter(o => o.hypothesis).map(o => ({statement:o.hypothesis, status:o.status})), ...arr(task.assumptions)];
  if (!guesses.length) hypotheses.append(el('p', '尚未记录诊断假设。'));
  guesses.forEach(g => { const line = el('article'); field(line, '假设', g.statement); if (g.basis) field(line, '依据', g.basis); if (g.check) field(line, '如何证伪', g.check); field(line, '状态', g.status); hypotheses.append(line); });
  columns.append(facts, hypotheses); observations.append(columns);
  const history = section('事件时间线', 'card incident-timeline');
  const entries = arr(task.timeline).concat(arr(((task.stage_details || {}).operations || {}).items));
  if (!entries.length) history.append(el('p', '尚未采集事件时间线。'));
  const timeline = el('ol', undefined, 'stage-timeline');
  entries.forEach(entry => { const li = el('li'); li.append(el('h3', text(entry.at))); if (entry.actor) field(li, '记录人', entry.actor); field(li, '事实', entry.observation || entry.impact); if (entry.hypothesis) field(li, '待验证假设', entry.hypothesis); field(li, '动作', entry.action); if (entry.verification) field(li, '验证', entry.verification); timeline.append(li); });
  history.append(timeline);
  if (focus !== 'acceptance') recovery();
}
