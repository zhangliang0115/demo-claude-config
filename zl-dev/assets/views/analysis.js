/* Read-only source analysis: statements never imply runtime or business acceptance. */
function renderAnalysisView(parent, task, ui) {
  const {el, text} = ui;
  const analysis = task.analysis || {}, assessment = task.analysis_assessment || {};
  const mode = analysis.mode === 'data_flow' ? 'data_flow' : 'business_logic';
  parent.dataset.layout = 'analysis-' + mode;
  parent.classList.add('analysis-view');
  const rows = key => Array.isArray(analysis[key]) ? analysis[key] : [];
  const evaluated = Array.isArray(assessment.sources) ? assessment.sources : [];
  const sources = evaluated.length ? evaluated : rows('sources').map(s => ({...s, status: 'unknown', reason: '尚无来源核对结果'}));
  const sourceById = new Map(sources.map(source => [source.id, source]));
  const sourcePanels = new Map();
  let sectionNumber = 0;
  function section(title, intro) {
    const box = el('section', undefined, 'document-section analysis-section');
    const heading = el('div', undefined, 'section-heading');
    heading.append(el('span', String(++sectionNumber).padStart(2, '0'), 'section-number'), el('h2', title));
    box.append(heading);
    if (intro) box.append(el('p', intro, 'analysis-intro'));
    parent.append(box);
    return box;
  }
  function empty(parent, message) { parent.append(el('p', message, 'analysis-empty')); }
  const statusLabels = {current: '当前源码匹配', stale: '源码已变化', unavailable: '来源不可读取', invalid: '来源无效', unknown: '来源未核对'};
  function sourceStatus(source) { return statusLabels[source && source.status] || statusLabels.unknown; }
  function references(parent, ids) {
    const line = el('div', undefined, 'analysis-references');
    line.append(el('span', '依据 ', 'analysis-ref-label'));
    if (!Array.isArray(ids) || !ids.length) line.append(el('span', '未记录源码依据', 'analysis-ref-missing'));
    (ids || []).forEach(identity => {
      const source = sourceById.get(identity), link = el('a', identity, 'analysis-source-ref');
      link.href = '#' + encodeURIComponent('analysis-source-' + identity);
      link.onclick = event => {
        const panel = sourcePanels.get(identity);
        if (!panel) return;
        event.preventDefault(); panel.open = true; panel.scrollIntoView({behavior: 'smooth', block: 'start'});
      };
      line.append(link, el('span', sourceStatus(source), source && source.status === 'current' ? 'analysis-ref-current' : 'analysis-ref-missing'));
    });
    parent.append(line);
  }
  const currentSources = ids => Array.isArray(ids) && ids.length > 0 && ids.every(identity => sourceById.get(identity)?.status === 'current');
  function factualState(parent, ids) {
    const current = currentSources(ids);
    parent.append(el('span', current ? '源码依据' : '依据待复核', 'analysis-tag ' + (current ? 'analysis-tag-fact' : 'analysis-tag-unknown')));
  }

  const boundary = section('本次分析边界', '只读追踪源码、配置与已提供材料；未执行项目或验证运行中的业务链路。');
  const scope = el('dl', undefined, 'analysis-scope');
  [['问题', analysis.question || task.why], ['范围', task.scope], ['分析方式', mode === 'data_flow' ? '数据来源、流转与字段转换' : '业务入口、条件规则与异常路径']].forEach(([label, value]) => {
    scope.append(el('dt', label), el('dd', text(value)));
  });
  boundary.append(scope);
  if (!analysis.conclusion) empty(boundary, '当前尚未形成分析结论，缺少材料不代表业务逻辑正确。');

  const steps = rows('steps');
  const flow = section(mode === 'data_flow' ? '已追到的数据流转' : '业务入口与主流程', '以下只连接已有来源的记录；未知环节单独列为断点，不推断调用已经成立。');
  const sequence = el('ol', undefined, mode === 'data_flow' ? 'analysis-data-flow' : 'analysis-logic-flow');
  steps.forEach((step, index) => {
    const item = el('li', undefined, 'analysis-flow-step');
    const heading = el('div', undefined, 'analysis-step-heading');
    heading.append(el('span', String(index + 1).padStart(2, '0'), 'analysis-step-number'), el('h3', text(step.title)));
    item.append(heading, el('p', text(step.description)));
    factualState(item, step.source_ids); references(item, step.source_ids); sequence.append(item);
  });
  flow.append(sequence);
  if (!steps.length) empty(flow, '尚未记录可追溯的入口与流转步骤。');

  if (mode === 'data_flow') {
    const mapping = section('字段映射与转换', '对照来源字段、目标字段和转换规则；缺失的写入来源或计算分支保留为断点。');
    const wrap = el('div', undefined, 'tablewrap analysis-mapping-table'), table = el('table'), head = el('thead'), header = el('tr');
    ['来源字段 / 数据', '目标字段 / 数据', '转换与过滤', '源码依据'].forEach(label => header.append(el('th', label)));
    head.append(header); table.append(head); const body = el('tbody');
    rows('mappings').forEach(row => {
      const tr = el('tr'); [row.from, row.to, row.transformation].forEach(value => tr.append(el('td', text(value))));
      const evidence = el('td'); factualState(evidence, row.source_ids); references(evidence, row.source_ids); tr.append(evidence); body.append(tr);
    });
    table.append(body); wrap.append(table); mapping.append(wrap);
    if (!rows('mappings').length) empty(mapping, '尚未记录字段映射；不能把同名字段当作已确认的数据传递。');
  } else {
    const rules = section('条件规则与异常分支', '从条件推到实际处理结果；源码可说明实现规则，不能替代业务规则的合理性判断。');
    const list = el('div', undefined, 'analysis-rule-list');
    rows('rules').forEach(rule => {
      const row = el('article', undefined, 'analysis-rule');
      const condition = el('div'), outcome = el('div');
      condition.append(el('span', '当满足', 'analysis-rule-label'), el('h3', text(rule.condition)));
      outcome.append(el('span', '代码会', 'analysis-rule-label'), el('p', text(rule.outcome)));
      const evidence = el('div', undefined, 'analysis-rule-evidence'); factualState(evidence, rule.source_ids); references(evidence, rule.source_ids);
      row.append(condition, outcome, evidence); list.append(row);
    });
    rules.append(list);
    if (!rows('rules').length) empty(rules, '本轮未单列条件规则；不据此推断所有正常、异常和边界分支已覆盖。');
  }

  const findings = section('事实、推断与未知', '分类来自分析记录；指纹匹配只说明当前文件与记录一致，不证明解释正确或业务已经运行验证。');
  const labels = {fact: '源码事实', inference: '推断', unknown: '未知'};
  ['fact', 'inference', 'unknown'].forEach(kind => {
    const records = rows('findings').filter(row => row.classification === kind);
    if (!records.length) return;
    const group = el('div', undefined, 'analysis-finding-group analysis-findings-' + kind);
    group.append(el('h3', kind === 'fact' && records.some(record => !currentSources(record.source_ids)) ? '事实记录 · 依据待复核' : labels[kind]));
    records.forEach(finding => {
      const row = el('article', undefined, 'analysis-finding');
      if (kind === 'fact') factualState(row, finding.source_ids);
      else row.append(el('span', labels[kind], 'analysis-tag analysis-tag-' + kind));
      row.append(el('p', text(finding.statement))); references(row, finding.source_ids); group.append(row);
    });
    findings.append(group);
  });
  if (!rows('findings').length) empty(findings, '尚未整理结论依据；不能从流程图自动推断事实成立。');

  const gaps = section('链路断点与未覆盖范围', '断点保留在当前结论中；补齐材料或追踪依据后再更新，不用猜测连接缺失环节。');
  rows('gaps').forEach(gap => {
    const row = el('article', undefined, 'analysis-gap');
    const disposition = {investigate: '待继续查证', needs_input: '需要补充材料', out_of_scope: '本轮范围外'}[gap.disposition || 'investigate'] || '待继续查证';
    row.append(el('span', text(gap.id) + ' · ' + disposition, 'analysis-gap-id'), el('h3', text(gap.description)), el('p', '下一步：' + text(gap.next_action)));
    gaps.append(row);
  });
  if (!rows('gaps').length) empty(gaps, '当前未记录断点；这不表示不存在未发现的分支或运行时差异。');

  const evidence = section('源码依据', '展开查看文件、行号和内容指纹。此页不会访问源码文件或业务接口；更新后的匹配状态由插件重新核对。');
  sources.forEach(source => {
    const detail = el('details', undefined, 'analysis-source'); detail.id = 'analysis-source-' + source.id;
    detail.append(el('summary', text(source.id) + ' · ' + text(source.path) + ' · ' + sourceStatus(source)));
    const data = el('dl');
    [['项目', source.project_path], ['文件', source.path], ['行号', source.line_start + '–' + source.line_end], ['核对状态', sourceStatus(source)], ['记录时 SHA256', source.sha256], ...(source.current_sha256 ? [['本次观察 SHA256', source.current_sha256]] : []), ...(source.current_line_count !== undefined ? [['本次文件行数', source.current_line_count]] : []), ['核对说明', source.reason || '当前记录未提供额外说明']].forEach(([label, value]) => {data.append(el('dt', label), el('dd', text(value)));});
    detail.append(data); sourcePanels.set(source.id, detail); evidence.append(detail);
  });
  if (!sources.length) empty(evidence, '尚无源码引用。补充文件与行号后再形成可核对结论。');
}
