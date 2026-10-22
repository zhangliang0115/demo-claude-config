---
description: 日常运维检查与受控变更
argument-hint: "[任务描述或任务目录]"
---

读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`、`docs/team-workflow.md` 和 `docs/schema-reference.md`（后两者也相对插件根目录）。

用户参数：$ARGUMENTS

创建 operations 任务，记录环境/目标、操作卡、授权范围、观察指标、停止条件、恢复办法。区分计划、已执行与验证完成。未经授权不做生产写操作。按固定 HTML 展示检查、结果和待决事项。

使用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"` 初始化/渲染任务。默认 `.reviewable-dev/tasks/<slug>/`，按 schema 编辑 task.json。结束时 render 并 index 任务根目录，返回固定模板 HTML 绝对路径。
