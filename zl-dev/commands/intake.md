---
description: 接收他人的方案并复述确认
argument-hint: "[任务描述或任务目录]"
---

读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`、`docs/team-workflow.md` 和 `docs/schema-reference.md`（后两者也相对插件根目录）。

用户参数：$ARGUMENTS

读取 HANDOFF.md、task.json 与当前项目约定，核对代码和资料版本。填写 handoffs 的接收者复述、范围、疑问和第一步。不同工具/模型不影响字段结构。接收人未明确确认前不得标 accepted。发现矛盾先记录并找对应负责人，不静默重设计。

使用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"` 初始化/渲染任务。默认 `.zl-dev/tasks/<slug>/`，按 schema 编辑 task.json。结束时 render 并 index 任务根目录，返回固定模板 HTML 绝对路径。
