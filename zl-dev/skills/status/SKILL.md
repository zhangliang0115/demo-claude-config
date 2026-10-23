---
name: status
description: 查看任务或跨项目功能当前结果、阻塞和下一步，不开始开发。
argument-hint: "[任务名、任务目录，或留空查看当前任务]"
disable-model-invocation: true
user-invocable: true
---

用户输入：$ARGUMENTS

先定位当前会话任务及真实项目；需要候选时执行 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" continue --project "<项目绝对路径>"`。多个候选只列标题请用户选，不默选最近任务。明确功能目录则使用 `scripts/feature.py status`。

读取选中任务的事实和脚本 status 输出，检查已实现与已验证是否混用、证据是否过期。只读查看，不开始实现，不填满阶段、不加载所有工作协议。

回复：一句话说清任务目标；说明已完成、当前阻塞/待决（至多三项）；给出一条具体下一步及负责人；附已有 report.html 或 feature.html 的绝对路径。无法确认的信息标记待核实。用户要继续修改时用 `/zl-dev:go`，不引导调用内部阶段命令。
