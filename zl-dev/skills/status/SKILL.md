---
name: status
description: 只读查看当前任务或跨项目功能的目标、进展、缺口和下一步。
argument-hint: "[任务或功能目录，或留空查询已有会话焦点]"
disable-model-invocation: true
user-invocable: true
---

用户输入：$ARGUMENTS

宿主：claude-code；本会话 ID：`${CLAUDE_SESSION_ID}`。仅用宿主展开值，未展开或不可用时不伪造身份。

本入口固定 mode=status，按 `${CLAUDE_PLUGIN_ROOT}/docs/quick-read.md` 查询；当前版本已加载则沿用，不先读完整 entry/workflow/team/schema。即使用户提到过期报告，本入口也不 render、不保存事实、不改关联或执行操作。需要做事时说明应从 go 处理，不在 status 内静默推进。

优先一次 locate，用 task_brief/feature_brief、派生当前行动和 report_state 回答；字段足够时不先 ls、读 task.json、HTML 或源码再确认。明确目标仅覆盖本轮查看，缺目标按已有可靠会话 resolve，不猜唯一或最近任务。实际版本或身份问题必须说明，不能为了减少工具量省略错误。

用户明确关注共享工作区或活动冲突时，才按需读 docs/execution-context.md 并只读 inspect/status；不 begin/end，不把登记或无登记当成业务进展/隔离证明。不要为普通进度查询追加交接、活动或源码扫描。
