# 内部动作：handoff

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：当前任务输入（由 go 路由提供）

接手时先显式复述全局目标、本轮范围、交付契约与代码版本，并列出交接包、当前仓库和运行环境之间的版本差异；不一致时先澄清再实施。检查实际运行进程、端口和启动版本，不仅凭交接包认定服务仍在运行或已更新。

核对目标、场景演示、行为变化、实际实现、待决项和验证证据是否一致。区分历史操作结果、当前已核实事实与未确认结果，不能把历史成功记录当作当前状态。渲染 HTML，优先提供一分钟概览、人工验收步骤、关键代码位置及剩余风险。明确模拟不是真实运行。HTML 反馈是本地草稿，复制并由人明确发回后才可记录为决定。不得从本地勾选推断批准、发布或上线授权。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。

读取 `${CLAUDE_PLUGIN_ROOT}/docs/team-workflow.md`。填写 roles 与 handoffs（交出人、接收人、版本、未决问题），执行 `handoff <任务目录>` 生成跨工具 HANDOFF.md。不要只交聊天摘要；不得把尚未确认的假设改成硬性需求。接手者通过 `/zl-dev:go` 继续，按 HANDOFF.md 复述并核对实际状态。
