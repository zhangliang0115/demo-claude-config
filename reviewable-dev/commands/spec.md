---
description: 明确行为约定、样例和待决事项
argument-hint: "[任务描述或任务目录]"
---

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：$ARGUMENTS

读取相关实现和测试，将当前行为与目标行为分开。为规则和场景建立稳定 ID，提供正常、异常、边界例子，记录依据。识别历史数据、权限、重复请求和并发影响。只将用户已确认的业务决定标为确认；其余保留待决。生成 HTML，让人通过场景理解规则。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `.reviewable-dev/tasks/<slug>/`。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。
