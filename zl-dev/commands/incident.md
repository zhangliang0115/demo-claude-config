---
description: 生产问题只读诊断、止损建议与恢复验证
argument-hint: "[任务描述或任务目录]"
---

读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`、`docs/team-workflow.md` 和 `docs/schema-reference.md`（后两者也相对插件根目录）。

用户参数：$ARGUMENTS

按 docs/team-workflow.md 生产事件协议处理。创建 incident 任务，记录影响、时间线、事实、假设、负责人。默认只读诊断，脱敏资料。写操作必须具备明确授权和范围、停止条件、回退办法；已有具体授权不重复询问。恢复要有实际用户路径或指标证据，不能用重启成功代替恢复。

使用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"` 初始化/渲染任务。默认 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，按 schema 编辑 task.json。结束时 render 并 index 任务根目录，返回固定模板 HTML 绝对路径。
