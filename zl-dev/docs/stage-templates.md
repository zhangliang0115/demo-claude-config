# 阶段专用展示协议

需要结构化记录或报告时使用 templates/stages.json 定义字段，以及 assets/stages.js 与 stages.css 的固定渲染。AI 只填写 task.json.stage_details；不得为任务另写 HTML、CSS、脚本或自定义字段。所有页面随 report.html 离线内嵌，不依赖 CDN。

## 每个阶段的共同结构

purpose（为什么做）、owner（谁负责）、summary（当前结论）、decision（需要人决定什么）、exit_criteria（交给下一阶段的条件）、items（结构化记录）。未确定填空字符串，不能编造。缺失内容在 UI 中明确展示，不自动判定通过。

items 必须有阶段内唯一 id 和 status：pending/in_progress/blocked/done。done 仅表示记录者声明条目处理完成，不等于人已批准或验证已通过。其余展示字段均为字符串；未知字段拒绝，避免不同 AI 发明不同格式。

## 固定阶段与字段

### requirements — 需求理解
核对原始描述与解释，明确边界和验收例子。

original：原始描述 | interpretation：理解结果 | boundary：范围与非目标 | example：验收例子

### solution — 方案设计
并排比较候选方案、交互路径和取舍。

name：方案名称 | approach：如何工作 | benefit：收益 | cost：成本与代价 | risk：风险 | flow：交互或架构流程

### handoff — 下发与接手
对照交出内容与接收者复述，暴露理解差异。

deliverable：交出范围与版本 | receiver：接收人 | readback：接收者理解 | gap：差异与疑问 | next_action：第一步

### implementation — 实施过程
对照计划与实际，解释变更和影响。

planned：计划切片 | actual：实际实现 | deviation：偏差与原因 | impact：影响范围 | source：代码位置

### review — 代码审查
按严重程度查看发现、修复和复查证据。

severity：严重程度 | finding：发现与成立条件 | source：代码位置 | fix：修复说明 | recheck：复查结果

### testing — 自动测试与 E2E
逐步查看预期、实际与证据；模拟不代表执行。

case：测试场景 | mode：simulation / recorded | environment：环境与前置条件 | expected：预期结果 | actual：实际结果 | source：日志或截图位置

### acceptance — 人工验收
人亲自核验关键场景；页面选择只生成草稿。

scenario：验收场景 | instruction：操作步骤 | expected：预期 | actual：人工实际观察 | reviewer：核验人 | result：接受 / 退回 / 未核验

### release — 发布与回滚
核对放行条件、观察指标、停止条件及恢复办法。

check：发布检查项 | environment：目标环境 | authorization：授权记录 | metric：观察指标及阈值 | stop：停止条件 | rollback：回退步骤 | actual：执行结果

### operations — 运维与复盘
沿事件时间线区分事实、假设、动作与恢复证据。

at：时间 | observation：事实与影响 | hypothesis：诊断假设 | action：动作及授权 | verification：恢复指标 / 用户路径 | followup：防复发行动及负责人

## 特殊字段与交互

- review.severity 为 P0/P1/P2/P3；提供严重度及状态筛选。
- testing.mode 为 simulation/recorded，必须明确；steps 为 action/expected/actual 字符串对象数组。步骤回放只展示保存的记录，不执行测试。截图和日志位置按文本展示，不加载远端不可信资源。
- evidence_ids 可关联已有 evidence.id，不允许悬空引用。真实测试仍需实际命令、环境、时间和结果证据。
- solution 展示结构化方案比较和流程说明，不声称自动生成了可运行产品原型。
- acceptance 的页面选择与备注只生成可复制反馈，并绑定 task_id、版本及阶段，不直接改变已确认记录。人明确回传后再核对版本并更新。
- release 的授权和执行结果必须分别填写；HTML 永远不会执行发布、回滚或生产命令。

## 各命令填写责任

start/spec → requirements；design/plan → solution；handoff/intake → handoff；build → implementation；review → review；verify → testing；handoff 最终交付时补 acceptance 和需要时的 release；incident/ops → operations，需要变更时补 release。

阶段完成不强制 render；重要事实按入口策略保存，确需结构化交付或用户明确要求时才生成报告，任务总览仅显式需要时 index。模板不足时修改插件版本并增加校验/测试，不在某个任务里偷偷修改渲染风格。

旧任务不含 stage_details 仍可打开，工作台显示待补齐。新 init 自动生成全部阶段骨架。已有任务按以下字段添加，不覆盖旧内容。
