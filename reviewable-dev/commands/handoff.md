---
description: 交付交互式理解与人工验收页面
argument-hint: "[任务描述或任务目录]"
---

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：$ARGUMENTS

核对目标、场景演示、行为变化、实际实现、待决项和验证证据是否一致。渲染 HTML，优先提供一分钟概览、人工验收步骤、关键代码位置及剩余风险。明确模拟不是真实运行。HTML 反馈是本地草稿，导出且由人明确发回后才可记录为决定。不得从本地勾选推断批准、发布或上线授权。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `.reviewable-dev/tasks/<slug>/`。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。

读取 `${CLAUDE_PLUGIN_ROOT}/docs/team-workflow.md`。填写 roles 与 handoffs（交出人、接收人、版本、未决问题），执行 `handoff <任务目录>` 生成跨工具 HANDOFF.md。不要只交聊天摘要；不得把尚未确认的假设改成硬性需求。下位人员使用 intake 或直接按 HANDOFF.md 复述并核对。
