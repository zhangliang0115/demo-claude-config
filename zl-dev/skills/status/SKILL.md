---
name: status
description: 查看任务或跨项目功能当前结果、阻塞和下一步，不开始开发。
argument-hint: "[任务名、任务目录，或留空查看当前任务]"
disable-model-invocation: true
user-invocable: true
---

用户输入：$ARGUMENTS

宿主：claude-code；本会话 ID：`${CLAUDE_SESSION_ID}`。仅使用宿主展开值；未展开、为空或不可用时不编造会话身份。

先定位真实项目及本轮明确目标。显式指定任务/功能时直接只读查询它；这是临时查看，不改变本会话原焦点。无显式目标时按 docs/entry-workflow.md 的会话关联规则调用 session_context.py resolve，仅 state=bound 时使用 target.kind/path。unbound/invalid_index/invalid_target 不猜唯一或最近任务，简短说明缺口并列候选标题供指定；宿主 ID 不可用时仅使用明确任务引用。status 绝不 bind/clear，也不创建、修复会话关联；需要切换焦点由 go 处理。子代理只查询显式分配目标。优先使用紧凑 locate，只有需要具体证据才追加 status；target.kind=feature 时使用 feature.py locate/status。

已有明确任务目录时使用 `reviewable.py locate "<任务目录>"` 或 `status "<任务目录>"`；`--project` 只能传业务源码项目路径，不能传 `~/.claude/zl-dev/.../tasks/...` 产出目录。

读取选中任务的事实和脚本 status 输出，检查已实现与已验证是否混用、证据是否过期。locate/status 仅只读；禁止调用会生成报告的 continue/render/index。report 为 null 时说明报告尚未生成，不自动补建。只读查看，不开始实现，不填满阶段、不加载所有工作协议。

按脚本派生的 primary_action、blockers 与 verification 说明当前行动，不从 focus_stage 自行推断就绪。当前失败和未解决 P0/P1 优先；done 的高风险发现仍须有当前、无矛盾的引用复查。区分 verification_source 的 claim、parsed_result 和 invalid；旧声明不是已解析证明，解析也不能证明业务覆盖或人工签字。

失败与过期可能指向同一条历史证据，不能直接相加。当前核验回执引用了新的结果文件时，沿回执核对统计与版本，不因旧记录过期就断言新回执缺少明细。

回复：一句话说清任务目标；说明已完成、当前阻塞/待决（至多三项）；给出一条具体下一步及负责人；若报告存在，按其时效附选中任务 report.html 或功能 feature.html 的绝对路径；missing 时说明尚未生成，不要求先补报告；不能返回 examples/index.html 或全部阶段合集作为当前任务报告。无法确认的信息标记待核实。用户要继续修改时用 `/zl-dev:go`，不引导调用内部阶段命令。

检查 handoff.freshness；stale/unknown/missing 时提示用 go 重新核对后显式导出，先保留手工补充，status 不自动生成或覆盖 HANDOFF.md。

检查 report_state；stale/unknown 时将旧链接明确称为历史快照，不声称页面为当前状态，也不自动生成。说明用 go 核对后更新。人工反馈依据 workflow_summary.human_verification；本版退回交 AI，已记录全部人工通过不重复催第一项、不推断发布授权。

locate 的 primary_action/blockers/verification/human_verification 是顶层字段，status 则位于 workflow_summary 下；两个命令顶层均直接提供 task_revision/assessment_revision。使用脚本绝对路径直接调用，不 cd 到插件目录、不用相对路径或 head 截断 JSON。现成字段足以判断时不要扫描 runs 或阅读脚本源码自行重算版本。

用户关注工作区、并行任务或执行冲突时，按需读 docs/execution-context.md 并调用 workspace.py inspect/status；仅返回实际路径、Git本机关系与已登记活动，observation_unstable=true 时说明观察可能变化。状态未知不能当空表，无活动也不能宣称没有外部写入。status不begin/end、不自动创建worktree，不让活动状态替代业务完成状态。
