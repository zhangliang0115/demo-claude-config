# 内部动作：design

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`、`docs/team-workflow.md` 和 `docs/schema-reference.md`（后两者也相对插件根目录）。

用户参数：当前任务输入（由 go 路由提供）

读取原始需求与源码，生成事实/假设清单、方案选项、取舍和具体使用场景。补充 roles、assumptions、design。允许推荐合理方案，但关键业务假设必须由人确认。用模板生成 HTML，绝不把模拟当已实现。

使用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"` 初始化/渲染任务。默认 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，按 schema 编辑 task.json。结束时 render 并 index 任务根目录，返回固定模板 HTML 绝对路径。
