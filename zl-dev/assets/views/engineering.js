/* Engineering task kinds use different evidence and explanation structures. */
function renderEngineeringView(parent, task, ui) {
  const {el, card, list, text, show} = ui;
  const kind = task.kind || 'refactor';
  parent.dataset.layout = 'engineering-' + kind;
  parent.classList.add('scene-engineering-' + kind);
  const rows = key => ((task.stage_details || {})[key] || {}).items || [];
  const box = (title, body) => card(parent, title, body);
  function implementation(title) {
    const section = box(title, '以下只展示实际记录，不从设计推断已完成。');
    const sequence = el('ol', undefined, 'scene-timeline'); section.append(sequence);
    rows('implementation').forEach(r => { const step = el('li'); step.append(el('strong', text(r.planned)), el('p', '实际：' + text(r.actual)), el('p', '位置：' + text(r.source)), el('p', '影响与偏差：' + text(r.impact) + '；' + text(r.deviation))); sequence.append(step); });
    (task.implementation || []).forEach(r => sequence.append(el('li', typeof r==='string'?r:text(r.title)+'：'+text(r.description)+'；代码位置：'+text(r.files))));
    if (!sequence.children.length) section.append(el('p', '尚无实施记录。'));
  }
  function evidence(title) {
    const section = box(title, '未运行、模拟、过期与真实执行结果应按原状态判断。');
    (task.evidence || []).forEach(e => card(section, text(e.id) + ' · ' + text(e.status)+' · '+text(e.freshness), text(e.summary) + '\n命令：' + text(e.command) + '\n版本：' + text(e.revision)));
    rows('testing').forEach(t => card(section, text(t.case), '模式：' + text(t.mode) + '\n环境：' + text(t.environment) + '\n预期：' + text(t.expected) + '\n实际：' + text(t.actual) + '\n来源：' + text(t.source)));
    if (!(task.evidence || []).length && !rows('testing').length) section.append(el('p', '未记录执行证据，无法判断结果。'));
  }
  if (kind === 'performance') {
    box('正在优化什么', task.why || task.summary);
    const grid = el('div', undefined, 'scene-grid'); parent.append(grid);
    card(grid, '基线与目标', '按同一测试记录中的预期核对目标；没有提供的基线数值保持未知。');
    card(grid, '实际测量', '仅展示已记录的实际结果；不生成估算提升率或示意图表。');
    const measurements = rows('testing');
    measurements.forEach(t => { const pair = el('div', undefined, 'scene-grid'); parent.append(pair); card(pair, text(t.case) + ' · 预期 / 目标', t.expected); card(pair, '实际观测', text(t.actual) + '\n环境：' + text(t.environment) + '\n模式：' + text(t.mode)); });
    if (!measurements.length) box('测量缺口', '基线、目标、实际测量结果尚未记录，不能宣称优化有效。');
    implementation('瓶颈处理与改动'); evidence('正确性和性能验证');
  } else if (kind === 'migration') {
    box('迁移目标和范围', task.scope || task.summary);
    const map = box('转换规则', '每项旧行为或旧数据应如何变成新结果。');
    (task.behaviors || []).forEach(b => card(map, text(b.id), '迁移前：' + text(b.before) + '\n迁移后：' + text(b.after) + '\n状态：' + text(b.status)));
    if (!(task.behaviors || []).length) map.append(el('p', '转换规则尚未记录。'));
    (task.design || []).forEach(d => card(map, text(d.title), d.description));
    implementation('迁移执行次序'); evidence('预演与数据核对证据');
    box('恢复路径', task.rollback); list(parent, '停止或恢复前需关注', task.risks || []);
  } else if (kind === 'upgrade') {
    box('升级边界', task.scope || task.summary);
    const matrix = box('兼容性变化', '检查业务、接口或依赖行为是否改变。');
    (task.behaviors || []).forEach(b => { const pair = el('div', undefined, 'scene-grid'); matrix.append(pair); card(pair, '旧版本 · ' + text(b.id), b.before); card(pair, '目标版本', text(b.after) + '\n验证状态：' + text(b.status)); });
    if (!(task.behaviors || []).length) matrix.append(el('p', '尚无兼容性记录，不能假定新旧一致。'));
    implementation('试点与分批升级顺序'); evidence('升级验证'); box('回退与恢复', task.rollback);
  } else {
    box('为什么调整结构', task.why || task.summary);
    const invariants = box('必须保持的行为', '用行为约定检查结构调整是否改变外部结果。');
    (task.behaviors || []).forEach(b => card(invariants, text(b.id), '原行为：' + text(b.before) + '\n目标约定：' + text(b.after) + '\n状态：' + text(b.status)));
    if (!(task.behaviors || []).length) invariants.append(el('p', '尚未记录行为不变量。'));
    implementation('结构调整切片'); evidence('回归验证');
  }
  list(parent, '人工核对', task.acceptance || []);
  const action = box('反馈本轮结果', '记录发现的问题或需要补充的验证。');
  const button = el('button', '填写并复制反馈'); button.onclick = () => show('decisions'); action.append(button);
}
