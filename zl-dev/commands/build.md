---
description: 实施已授权切片并持续更新理解页面
argument-hint: "[任务描述或任务目录]"
---

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：$ARGUMENTS

读取确认的规则和当前切片，实施范围内代码变更，遵守项目风格。不把关键业务未知当默认值。同步更新真实实现步骤、改动位置和实现偏差，旧证据过期后重新验证。实际执行相关测试，完成后渲染 HTML；遇到缺少环境就记录未验证，不伪造通过。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。
