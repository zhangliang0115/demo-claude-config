/* Bug investigation is an evidence trail, rather than a project dashboard. */
function renderBugfixView(parent, task, ui) {
  const {el, card, list, text, show} = ui;
  const origin = ui.evidenceOrigin || (typeof evidenceOrigin === 'function' ? evidenceOrigin : () => '来源等级未知；不能据此认定实际执行。');
  parent.classList.add('scene-bugfix');
  parent.append(el('h2', '哪里出错了，为什么会错'));
  card(parent, '故障现象', task.summary);
  card(parent, '受影响范围', task.scope);

  const repro = el('section', undefined, 'card');
  repro.append(el('h2', '先复现，再判断修复'));
  const scenes = Array.isArray(task.scenarios) ? task.scenarios : [];
  const choices = el('div', undefined, 'scene-buttons');
  const steps = el('ol', undefined, 'scene-timeline');
  repro.append(choices, steps);
  function select(index) {
    steps.replaceChildren();
    Array.from(choices.children).forEach((button, i) => {
      button.classList.toggle('active', i === index);
      button.setAttribute('aria-pressed', String(i === index));
    });
    const scene = scenes[index];
    repro.querySelector('.scene-repro-kind').textContent = scene.kind === 'simulation'
      ? '模拟复现步骤 · 尚不证明故障或修复已实际执行'
      : '提供的复现记录 · 需核对关联证据';
    (scene.steps || []).forEach(step => {
      const item = el('li');
      item.append(el('strong', text(step.action)), el('p', '结果：' + text(step.result || step.actual || step.expected)));
      steps.append(item);
    });
    if (!(scene.steps || []).length) steps.append(el('li', '复现步骤尚未记录'));
  }
  repro.insertBefore(el('p', '', 'scene-repro-kind muted'), steps);
  scenes.forEach((scene, index) => {
    const button = el('button', scene.title || '复现场景 ' + (index + 1));
    button.type = 'button'; button.onclick = () => select(index); choices.append(button);
  });
  if (scenes.length) select(0);
  else steps.append(el('li', '缺少复现记录：先补充触发条件、操作与实际结果。'));
  parent.append(repro);

  const causes = el('section', undefined, 'scene-grid');
  const hypothesis = el('article', undefined, 'card');
  hypothesis.append(el('h2', '可能原因 · 不是结论'));
  const assumptions = task.assumptions || [];
  assumptions.forEach(item => {
    hypothesis.append(el('h3', text(item.statement)), el('p', '依据：' + text(item.basis)), el('p', '如何排除或确认：' + text(item.check)));
  });
  if (!assumptions.length) hypothesis.append(el('p', '原因尚未记录；不能从修复方案反推根因。'));
  const proof = el('article', undefined, 'card');
  proof.append(el('h2', '实际证据'));
  (task.evidence || []).forEach(item => {
    proof.append(el('h3', text(item.id) + ' · ' + text(item.status)), el('p', text(item.summary)), el('p', origin(item), 'evidence-origin'), el('p', '来源：' + text(item.source)), el('p', '有效性：' + text(item.freshness)));
  });
  if (!(task.evidence || []).length) proof.append(el('p', '尚无运行证据，根因与修复效果均待验证。'));
  causes.append(hypothesis, proof); parent.append(causes);

  const fix = el('section'); fix.append(el('h2', '修复如何阻断问题'));
  (task.implementation || []).forEach(item => {
    const c = card(fix, item.title || '修复改动', item.description);
    const location = el('details'); location.append(el('summary', '查看代码位置'), el('pre', text(item.files))); c.append(location);
  });
  if (!(task.implementation || []).length) card(fix, '修复尚未记录', '先验证原因，再记录实际改动；设计不等于已经修复。');
  parent.append(fix);

  const regression = el('section', undefined, 'card');
  regression.append(el('h2', '原问题与回归是否都验证了'));
  const tests = (((task.stage_details || {}).testing || {}).items || []);
  tests.forEach(test => {
    regression.append(el('h3', text(test.case || test.title || test.id)), el('p', '预期：' + text(test.expected)), el('p', '实际：' + text(test.actual)), el('p', '状态：' + text(test.status) + ' · 记录类型：' + text(test.mode)), el('p', '证据：' + text(test.evidence_ids)));
  });
  if (!tests.length) regression.append(el('p', '尚无回归记录；需检查原始复现是否消失及相关行为是否保持。'));
  const focus = (task.workflow_summary || {}).focus_stage || task.focus_stage;
  if (['testing', 'acceptance'].includes(focus)) {
    const checks = (((task.stage_details || {}).acceptance || {}).items || []);
    list(regression, '人工核验', checks.length ? checks.map(item => [item.scenario, item.instruction, item.expected].filter(Boolean).join('；')) : task.acceptance || []);
  }
  parent.append(regression);
  const next = card(parent, '现在该做什么', (task.workflow_summary || {}).next_action || '补齐复现与根因证据，再判断修复效果。');
  next.classList.add('scene-action');
  if ((task.decisions || []).some(item => item.status !== 'confirmed')) {
    const button = el('button', '查看需要确认的问题'); button.type = 'button'; button.onclick = () => show('decisions'); next.append(button);
  }
}
