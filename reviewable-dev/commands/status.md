---
description: 查看进度、过期证据与下一步
argument-hint: "[任务描述或任务目录]"
---

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：$ARGUMENTS

定位已有任务，运行 status，读取 task.json 和报告。总结已确认、已实现、已验证三类状态，指出证据过期、关键待决和阻塞项，给出一条最有价值的下一步。有必要时更新并 render。不执行无关代码修改。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `.reviewable-dev/tasks/<slug>/`。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。
