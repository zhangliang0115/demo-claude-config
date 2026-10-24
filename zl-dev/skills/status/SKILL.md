---
name: status
description: 查看任务或跨项目功能当前结果、阻塞和下一步，不开始开发。
argument-hint: "[任务名、任务目录，或留空查看当前任务]"
disable-model-invocation: true
user-invocable: true
---

用户输入：$ARGUMENTS

先定位当前会话任务及真实项目；需要候选时执行 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" locate --project "<项目绝对路径>"`。多个候选只列标题请用户选，不默选最近任务。明确功能目录则使用 `scripts/feature.py status`。

已有明确任务目录时使用 `reviewable.py locate "<任务目录>"` 或 `status "<任务目录>"`；`--project` 只能传业务源码项目路径，不能传 `~/.claude/zl-dev/.../tasks/...` 产出目录。

读取选中任务的事实和脚本 status 输出，检查已实现与已验证是否混用、证据是否过期。locate/status 仅只读；禁止调用会生成报告的 continue/render/index。report 为 null 时说明报告尚未生成，不自动补建。只读查看，不开始实现，不填满阶段、不加载所有工作协议。

按脚本派生的 primary_action、blockers 与 verification 说明当前行动，不从 focus_stage 自行推断就绪。当前失败和未解决 P0/P1 优先；done 的高风险发现仍须有当前、无矛盾的引用复查。区分 verification_source 的 claim、parsed_result 和 invalid；旧声明不是已解析证明，解析也不能证明业务覆盖或人工签字。

失败与过期可能指向同一条历史证据，不能直接相加。当前核验回执引用了新的结果文件时，沿回执核对统计与版本，不因旧记录过期就断言新回执缺少明细。

回复：一句话说清任务目标；说明已完成、当前阻塞/待决（至多三项）；给出一条具体下一步及负责人；附选中任务当前阶段 report.html 或功能 feature.html 的绝对路径，不能返回 examples/index.html 或全部阶段合集作为当前任务报告。无法确认的信息标记待核实。用户要继续修改时用 `/zl-dev:go`，不引导调用内部阶段命令。

检查 handoff.freshness；stale/unknown/missing 时提示用 go 重新核对后显式导出，先保留手工补充，status 不自动生成或覆盖 HANDOFF.md。
