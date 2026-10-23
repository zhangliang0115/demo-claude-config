# 内部动作：start

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：当前任务输入（由 go 路由提供）

读取用户目标与项目约定，识别任务类型和风险。创建或复用任务目录，填写目标、范围、现状、具体场景和关键未知项。对低风险且授权明确的任务可继续实施并验证；关键业务未知先展示可比较的选项并询问。不要要求每次手工执行全部八个阶段。生成首版 HTML，说明下一步。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。

若一个功能涉及多个项目，先读取 `${CLAUDE_PLUGIN_ROOT}/docs/cross-project.md` 并按 feature 流程执行：识别项目后整体设计，再拆项目任务。不得让各项目从模糊需求独立设计，也不要求先指定多人角色。
