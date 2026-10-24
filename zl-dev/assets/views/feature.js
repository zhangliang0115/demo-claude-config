/* Phase-specific editorial documents; controls remain in the shared decision rail. */
function renderFeatureView(parent, task, ui) {
  const {el, text} = ui;
  const stage = (task.workflow_summary || {}).focus_stage || task.focus_stage || 'requirements';
  parent.dataset.layout = 'feature-' + stage;
  const items = key => ((task.stage_details || {})[key] || {}).items || [];
  let number = 0;
  function section(title, intro) {
    const box=el('section',undefined,'document-section'),heading=el('div',undefined,'section-heading');
    heading.append(el('span',String(++number).padStart(2,'0'),'section-number'),el('h2',title));box.append(heading);
    if(intro)box.append(el('p',intro,'section-intro'));parent.append(box);return box;
  }
  function row(parent,label,value){if(value===undefined||value===null||value==='')return;const r=el('div',undefined,'document-row');r.append(el('strong',label),el('p',text(value)));parent.append(r);}
  function stories(title) {
    const box=section(title),scenarios=task.scenarios||[];
    if(!scenarios.length){box.append(el('p','尚未记录具体操作路径。','muted'));return;}
    const controls=el('div',undefined,'scene-buttons'),flow=el('ol',undefined,'journey-list'),caption=el('p',undefined,'journey-caption');
    function draw(index){flow.replaceChildren();[...controls.children].forEach((b,i)=>{b.classList.toggle('active',i===index);b.setAttribute('aria-pressed',String(i===index));});const s=scenarios[index];caption.textContent=s.kind==='simulation'?'预期流程 · 设计模拟，尚不代表已实现':'记录回放 · 请结合原始证据核对';(s.steps||[]).forEach((step,i)=>{const r=el('li'),copy=el('div',undefined,'journey-copy');copy.append(el('h3',text(step.action)),el('p',text(step.result||step.expected)));r.append(el('span',String(i+1).padStart(2,'0'),'journey-number'),copy);flow.append(r);});}
    scenarios.forEach((s,i)=>{const b=el('button',s.title||'场景 '+(i+1));b.type='button';b.onclick=()=>draw(i);controls.append(b);});
    if(scenarios.length>1)box.append(controls);box.append(caption,flow);draw(0);
  }
  function behavior(){const box=section('业务变化与保持项'),rows=el('div',undefined,'document-rows');(task.behaviors||[]).forEach(b=>{const item=el('div',undefined,'behavior-comparison');item.append(el('span',text(b.id),'muted'));row(item,'原来',b.before);row(item,'现在',b.after);if(b.status)item.append(el('p',text(b.status),'muted'));rows.append(item);});box.append(rows);if(!(task.behaviors||[]).length)box.append(el('p','尚未记录具体行为约定。','muted'));}
  function evidence(){const box=section('验证结果','仅实际执行的记录支持验收；演示不等于验证通过。');(task.evidence||[]).forEach(e=>{const r=el('div',undefined,'evidence-line');r.append(el('span',text(e.status)+' · '+text(e.freshness),'badge'),el('h3',text(e.summary)));r.append(el('p',evidenceOrigin(e),'evidence-origin'));const d=el('details');d.append(el('summary','核对执行记录'));if(e.verification_source==='parsed_result'&&e.parsed_result)row(d,'解析结果',e.parsed_result);row(d,'命令',e.command);row(d,'版本',e.revision);r.append(d);box.append(r);});if(!(task.evidence||[]).length)box.append(el('p','尚无执行证据。','muted'));items('testing').forEach(t=>{const r=el('div',undefined,'document-row');r.append(el('strong',text(t.case)));row(r,'预期',t.expected);row(r,'实际',t.actual);box.append(r);});}
  if(stage==='requirements'){
    const box=section('需求是这样理解的');items('requirements').forEach(r=>{row(box,'原始描述',r.original);row(box,'当前理解',r.interpretation);row(box,'待明确边界',r.boundary);});if(!items('requirements').length)box.append(el('p',text(task.why||task.summary)));
    stories('用户将如何操作');behavior();
  }else if(stage==='solution'){
    stories('用户将如何操作');
    const box=section('建议这样实现'),designs=task.design||[];
    designs.forEach((d,i)=>{const line=el('article',undefined,'design-line');line.append(el('span',String(i+1).padStart(2,'0'),'design-number'),el('h3',text(d.title)),el('p',text(d.description)));if(d.tradeoffs)row(line,'取舍',d.tradeoffs);if(d.alternatives){const detail=el('details');detail.append(el('summary','其他选择与比较'),el('p',text(d.alternatives)));line.append(detail);}box.append(line);});
    items('solution').forEach(d=>{const line=el('article',undefined,'design-line');line.append(el('h3',text(d.name)));row(line,'路径',d.flow);row(line,'实现',d.approach);row(line,'收益',d.benefit);row(line,'代价',d.cost);row(line,'风险',d.risk);box.append(line);});
    if(!designs.length&&!items('solution').length)box.append(el('p','方案尚未记录，需要先核对现有系统。','muted'));
    behavior();
  }else if(stage==='testing'||stage==='acceptance'){
    const box=section('按这些步骤验收');if(!items('acceptance').length){const steps=el('ol',undefined,'acceptance-list');(task.acceptance||[]).forEach(a=>steps.append(el('li',text(a))));box.append(steps);}
    items('acceptance').forEach(a=>{const line=el('article',undefined,'document-rows');line.append(el('h3',text(a.scenario)));row(line,'操作',a.instruction);row(line,'预期',a.expected);row(line,'实际',a.actual);row(line,'结果',a.result);box.append(line);});stories('核对完整业务路径');evidence();
  }else{
    const box=section('本轮实际完成的内容');items('implementation').forEach(r=>{const line=el('article',undefined,'design-line');line.append(el('h3',text(r.planned)));row(line,'实际',r.actual);row(line,'偏差',r.deviation);row(line,'影响',r.impact);row(line,'代码位置',r.source);box.append(line);});(task.implementation||[]).forEach(r=>{const line=el('article',undefined,'design-line');line.append(el('h3',typeof r==='string'?r:text(r.title)));if(typeof r!=='string'){line.append(el('p',text(r.description)));row(line,'代码位置',r.files);}box.append(line);});if(!box.querySelector('article'))box.append(el('p','尚无实施记录。设计方案不代表已经实现。','muted'));behavior();evidence();
    if(items('review').length){const review=section('审查发现');items('review').forEach(r=>{const line=el('article',undefined,'design-line');line.append(el('h3',text(r.severity)+' · '+text(r.finding)));row(line,'位置',r.source);row(line,'修复',r.fix);row(line,'复查',r.recheck);review.append(line);});}
  }
}
