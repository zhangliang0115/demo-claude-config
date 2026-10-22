---
description: 开始任务并生成可理解的 HTML 工作页
argument-hint: "[任务描述或任务目录]"
---

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：$ARGUMENTS

读取用户目标与项目约定，识别任务类型和风险。创建或复用任务目录，填写目标、范围、现状、具体场景和关键未知项。对低风险且授权明确的任务可继续实施并验证；关键业务未知先展示可比较的选项并询问。不要要求每次手工执行全部八个阶段。生成首版 HTML，说明下一步。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `.reviewable-dev/tasks/<slug>/`。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。
