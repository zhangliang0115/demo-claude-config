# 内部动作：plan

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：当前任务输入（由 go 路由提供）

基于行为约定制定小切片计划，说明每片的可观察行为、涉及模块、风险和验证。给出可理解的主流程及少量关键取舍，保留范围边界。不默认引入新架构或依赖。只对重大或未授权决定请求确认，更新 HTML。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。
