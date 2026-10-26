# task.json v1 数据约定

Python 3.9+，UTF-8 JSON 对象。以 scripts/reviewable.py 的 validate 为基础结构校验，以下语义仍需人工与 AI 核对。

必填：version=1；id/title 非空字符串；kind 为 feature/change/bugfix/refactor/performance/migration/upgrade/incident/operations/analysis。
summary/why/scope/stage/rollback 为字符串。changes/risks/acceptance 为字符串数组。

对象数组字段（无内容用 []）：
- behaviors: id（唯一）、before、after、status。明确规则已确认/已实现是不同事实；验证状态由 evidence 单独呈现。
- scenarios: title、kind（simulation/recorded）、steps（action/result 对象数组）。recorded 只能来自真实记录。
- implementation: title、description、files（路径或路径数组）。
- decisions: id、question、recommendation、status（pending/confirmed）、owner、source、at。confirmed 需人的明确依据。
- evidence: id、behavior_ids（必须引用存在行为）、status（passed/failed/blocked/not_run）、command、summary、revision、source、executed_at；可加 actor/environment。source 是原始记录位置，页面不自动执行或读取路径。
- roles: role、owner、responsibility、accepts。
- assumptions: id、statement、basis、status（pending/confirmed/refuted）、owner、check。
- design: id、title、description、alternatives、tradeoffs、status。
- handoffs: id、from、to、deliverable、readback、open_questions、status（pending/accepted/rejected）、actor、at。
- timeline: at、actor、action、reason、impact。
- operations: id、type、environment、impact、observation、hypothesis、action、authorization、stop_condition、rollback、result、verification、status、owner。

## CLI
```
python3 scripts/reviewable.py init /任务目录 --title "任务标题" --kind feature
python3 scripts/reviewable.py render /任务目录
python3 scripts/reviewable.py status /任务目录
python3 scripts/reviewable.py fingerprint /任务目录
python3 scripts/reviewable.py handoff /任务目录
python3 scripts/reviewable.py index /任务根目录
```
init 不覆盖既有 task.json。为兼容旧 CLI，不带标志的 init/continue 保留生成报告的行为；go 默认使用下述 --no-render。render 固定生成 report.html；index 刷新子任务及 index.html；handoff 固定生成 HANDOFF.md。

## 延后生成报告（内部 CLI）

`--no-render` 仅适用于 `init` 和 `continue`，其他命令使用此标志会拒绝执行。go 默认新建/恢复使用该标志；旧的无标志返回行为保持兼容，用户仍只用 go/status。

```sh
python3 scripts/reviewable.py init cancel-order --project /workspace/orders --title "取消订单" --kind feature --no-render
python3 scripts/reviewable.py continue /真实任务目录 --project /workspace/orders --no-render
```

init 只创建必要 task.json，返回定位 JSON，不创建 HTML；continue 返回当前行动、已有报告路径及 current/stale/unknown/missing 状态，不写报告。重要事实与证据仍及时保存。需要页面时显式调用 render；未生成报告不影响纯文字工作的完成，不能伪造链接或把历史快照称为当前。

## 证据新鲜度
fingerprint 绑定 Git 工作区内容与行为约定（含场景、验收、假设、方案、交接及操作计划）。没有 Git 时 UNKNOWN，不能声称当前有效。验证前后计算指纹，完全相同才绑定 evidence.revision；指纹变化必须重新验证，不能只刷新指纹。指纹匹配不证明命令实际运行。
报告是生成时快照，不会自动监控文件变化。修改后需核对报告时效；只有需要交付新页面时才重新 render，status 只读核对，不强制生成。忽略文件与外部系统不在源码指纹保证范围，应额外记录环境及外部版本。task 目录中的日志不参与源码指纹，需人工核对真实性。

## 反馈
HTML 生成可读的反馈文本，填写后点“复制给 AI”并粘贴到会话，不直接改 task.json，不代表审批或接收。人把草稿交回会话后核对任务与版本，再记录明确授权。跨工具接手包不包含凭据，不自动执行任何命令。

## stage_details 扩展
可选对象，键只能取 templates/stages.json 中的九个阶段。新任务默认有骨架。字段、枚举、步骤与证据引用由 validate 强制校验；具体见 [阶段模板协议](stage-templates.md)。stage_details 内容变化会使旧证据需要重新核对；HTML 中的草稿修改不写回文件。

## 用户级项目存储（0.5.0）

新任务的 `project_path` 保存原项目真实绝对路径。产出目录在用户 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`；代码指纹读取 project_path 的源码，不能对 `.claude` 目录计算代码指纹。项目不存在时返回未知，不回退到其他仓库。旧任务缺少绑定时仍按原任务所在 Git 仓库定位。

```sh
python3 scripts/reviewable.py init cancel-order --project /workspace/orders --title "取消订单" --kind feature
python3 scripts/reviewable.py render cancel-order --project /workspace/orders
python3 scripts/reviewable.py status cancel-order --project /workspace/orders
```

位置参数是简单 slug 时按用户目录解析，`--project` 省略时使用当前目录；传入绝对路径或含路径分隔符的路径则继续支持原显式目录。日常插件必须使用默认用户目录，仅在用户明确指定旧目录或测试示例时使用显式路径。slug 不得为 . 或 ..。

跨项目 features 使用 `--workspace` 指定总任务归属，子任务分别使用自己的 `--project`。用户目录任务跨机器交接时更新 project_path/workspace_path 和关联 task_path；重新绑定后旧证据必须重新核验。所有历史任务保留，不会自动复制、移动或删除。

`reviewable.py index --project /项目绝对路径` 会生成该项目 tasks/index.html。跨项目 CLI 的 JSON 响应带 output_dir，供后续定位；render 则直接返回 feature.html 的绝对路径。不要用 shell 引号包裹 `~` 来期望 shell 展开；优先使用 slug + --project/--workspace 或脚本返回的绝对路径。

## 0.6.0 路由与证据
continue [任务目录或 slug] --project /项目路径 [--no-render]：省略任务时仅在恰好一个任务的情况下恢复；0 或多个返回候选清单。不会执行开发命令。返回 next_action 与 step（understand/decide/implement/verify/accept），供 AI 继续；accept 表示待人工核验，不是已验收。

workflow_summary 是渲染时计算结果，不让 AI 填写完成度。指纹仅使用 semantic_contract 明确选择的行为字段；阶段 testing/review 的结果、handoffs、人员和展示摘要不参与。阶段 requirements/solution 的核心内容及 acceptance 预期仍参与。旧证据需重新验证。

时间展示统一为 `yyyy-MM-dd HH:mm:ss`，时区 Asia/Shanghai（UTC+8）。原始数据保留带时区的 ISO 时间，页面与复制反馈格式化显示，不改变证据记录本身。

## 显式执行与可重新核算的测试回执

内部 CLI（不是新增斜杠命令）：

```bash
python3 scripts/reviewable.py verify /任务目录 --project /源码项目 --format unittest --behavior B1 --timeout 120 -- python3 -m unittest discover -s tests
python3 scripts/reviewable.py verify /任务目录 --project /源码项目 --format junit --behavior B1 --behavior B2 --result-file /本次唯一结果路径.xml -- pytest --junitxml=/本次唯一结果路径.xml
```

只执行调用者显式提供的 argv，以绑定项目为 cwd、shell=False；不会从 task.json、HTML 或 prepare_command 读取并运行命令。调用者仍须检查实际测试的环境和外部连接。JUnit 结果必须为本轮新文件；建议放在源码外或 Git 忽略的测试输出目录，避免结果文件本身改变源码指纹。执行不保证测试真正覆盖所引用行为。

每次运行在任务 `runs/verify-<唯一ID>/` 保留 stdout.log、stderr.log、receipt.json；JUnit 额外保存 result.xml。超时结束本次进程组并保留记录。回执记录 argv/cwd、开始结束时间、进程退出码、运行前后任务 revision 与代码/行为指纹、task 身份、行为引用、日志 SHA256 和解析统计。只在指纹和任务 revision 稳定时，以 CAS 追加独立 evidence，不修改已有证据，不渲染 HTML；冲突时只保留回执。返回 0 必须已追加证据、非零测试实际通过、没有跳过且版本稳定。

支持 unittest 的唯一 Ran N + OK/FAILED 摘要及 JUnit 的实际 testcase；0 项、跳过项、未知格式、缺摘要、非零退出、超时均不能成为 passed。单个输入文件只解析前述 16 MiB 上限以内的完整内容，超出则不解析，不记通过；这个限制不限制子进程写盘量，执行期间的原始 stdout/stderr 可能很大。部分 skip 也采用保守策略，不记 passed；如需单独证明未跳过的相关行为，应显式选择并重跑独立检查，不能隐藏跳过项。输出中的测试名或日志可以被程序伪造；**日志解析不等价业务覆盖或身份认证，不抵抗有本地写权限者同时伪造日志与回执**。

新增 evidence 可引用 `verification_receipt: {path: "runs/verify-.../receipt.json", sha256: "..."}`。报告/status 的 assessed 会重新检查回执哈希、任务与行为身份、原始日志哈希并重新解析；派生 `verification_source` 为 `parsed_result`、`claim`（旧记录/仅模型声明）或 `invalid`。合法解析派生 `parsed_result={format,counts:{total,passed,failed,errors,skipped},status}`；模型手填这两项会被覆盖。无效回执保留 `claimed_status`，有效 status 降为 not_run，不能使任务就绪。读取不会执行测试或改写文件。

## 可选人工核验上下文

`acceptance_setup` 可选对象，只允许字符串字段 `environment/prepare_command/entry_url/baseline/stop/notes`。entry_url 仅 http/https 或空；命令只展示，绝不自动执行。这些前置约定参与行为指纹，改变后旧证据过期。

acceptance、release 阶段条目可选 `reviewed_revision`（字符串）、`reviewer_kind`（human/ai/unknown，旧记录默认 unknown）、`verification_mode`（manual/assisted/automated，旧记录默认 manual）。执行者与核验方式不能由页面替人认证。核验版本、执行者、actual/result 等反馈元数据不参与行为指纹；已定义的场景、操作与预期仍参与。

## 页面快照与明确人工结果

render 派生 task_revision（task.json 精确字节版本）与 assessment_revision（忽略生成时间后的确定性评估版本），反馈复制携带两者及原代码/行为指纹。它们不应手填到 task.json。report_state 在只读 locate/status 中说明 current/stale/unknown/missing；路径存在不代表当前。生成时间不用于判定时效。

acceptance/release 条目可选 result_status: pass/fail/blocked/not_checked，作为明确结果，与展示文本 result 分开；不参与行为指纹。只有有当前指纹、reviewed_revision 匹配、reviewer_kind=human 的显式结果参与本版人工判断。自由文本与 status=done 不自动转译；AI 角色记录不会成为人工签字。核验接受不等于发布批准。

非空 release.items 的 id/check/environment/metric/stop/rollback 属于发布核验契约，变化会使旧证据及人工结论过期；authorization 与实际观察仍是记录元数据。空 release 不改变原有契约形状，避免未使用发布阶段的旧任务因升级无谓失效。

## 受托 AI 验收（仅 acceptance）

条目可选 `acceptance_delegation`，只允许四个必填字段：`kind="acceptance"`、非空字符串 `revision`、`source`（用户明确委托原话）与 `criteria`（本条标准与委托范围）。仅委托检查不填写。它是来源记录，不是身份认证，不授予发布权限，release 条目不接受此字段。委托元数据不改变代码/行为指纹，但改变精确记录及评估版本。

派生 `acceptance_verification` 将当前人工结果与本版明确受托 AI 结果分开保留；普通 AI pass 不会算接受，`human_verification` 不变。当前 AI fail/blocked 无论是否被委托都形成待 AI 调查的阻塞。有效委托但结果未执行/过期由 AI 继续；委托绑定旧指纹时仅派 AI 核对适用范围，不直接接受旧结果。全部项目当前验收通过后无真实待决问题则 `action_owner=none`，不要求人重复验收，不生成新发布批准；后续沿用已有授权。

## 会话恢复索引（不属于 task.json）

内部 session_context.py 的 resolve/bind/clear 按 host、可靠 session ID 和项目/工作区作用范围管理焦点，详见[关联协议](session-context.md)。resolve 返回 context_revision、state、action 和 target；context_revision 仅用于关联 CAS，不能替代任务/功能 revision 或代码指纹。关联变更不修改 task/feature、证据或报告；状态查询不写索引。旧任务无需加 session 字段，不自动迁移、复制或重绑。

## 只读源码分析（0.18）

kind=analysis 使用固定 analysis 阶段和顶层 analysis 对象，不按开发/验收状态派生；字段与来源工具见 [analysis-workflow.md](analysis-workflow.md)。来源元数据由 analysis.py source 读取实际文件取得，不手编哈希。推断/未知不能冒充事实，source_ids 必须存在。来源当前状态重新计算，观察变化参与 assessment；旧九类业务指纹保持兼容。通用 verify 不执行 analysis 任务，需运行验证时另行明确范围。

## HTML 展示版本（0.20）

HTML 内嵌 provenance.template_revision 由实际素材字节和 per-kind 渲染协议派生，不手填 task.json/feature.json，不参与业务 assessment_revision。report_state 另外提供 template_revision/current_template_revision/template_freshness，旧页缺值为 unknown，素材不同为 stale；整体 freshness 还须核对事实、代码、评估和实际页面。模板当前不能代替业务版本或验证。详见 [report-reuse.md](report-reuse.md)。
