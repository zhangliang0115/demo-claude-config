---
description: 把模糊需求变成可比较的方案与固定场景模板
argument-hint: "[任务描述或任务目录]"
---

读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`、`docs/team-workflow.md` 和 `docs/schema-reference.md`（后两者也相对插件根目录）。

用户参数：$ARGUMENTS

读取原始需求与源码，生成事实/假设清单、方案选项、取舍和具体使用场景。补充 roles、assumptions、design。允许推荐合理方案，但关键业务假设必须由人确认。用模板生成 HTML，绝不把模拟当已实现。

使用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"` 初始化/渲染任务。默认 `.reviewable-dev/tasks/<slug>/`，按 schema 编辑 task.json。结束时 render 并 index 任务根目录，返回固定模板 HTML 绝对路径。
