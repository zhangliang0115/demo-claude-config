# 内部动作：ops

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`、`docs/team-workflow.md` 和 `docs/schema-reference.md`（后两者也相对插件根目录）。

用户参数：当前任务输入（由 go 路由提供）

创建 operations 任务，记录环境/目标、操作卡、授权范围、观察指标、停止条件、恢复办法。区分计划、已执行与验证完成。未经授权不做生产写操作。按固定 HTML 展示检查、结果和待决事项。

使用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"` 初始化/渲染任务。默认 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，按 schema 编辑 task.json。结束时 render 并 index 任务根目录，返回固定模板 HTML 绝对路径。
