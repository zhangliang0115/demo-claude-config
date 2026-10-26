# 两个入口与按需工作流程

用户只需 `/zl-dev:go`（做事/继续）和 `/zl-dev:status`（看状态）。其余动作是插件内部资料，不注册斜杠命令。旧版阶段命令已撤下；旧任务数据和 CLI 仍可继续使用。

## 任务定位与会话关联

用户仍只需 go/status。长期 task/feature 保持跨会话事实；会话关联只是当前工具会话在某个项目或工作区的焦点，不是权限、任务所有权或代码隔离。

- 先判断本轮意图。普通概念解释和无新事实的追问不创建任务、不 bind/clear。明确新事项不复用旧焦点，也不因唯一历史任务自动接入。
- 本轮明确任务/功能引用优先于旧关联。go 先核对实际目标的项目绑定，只有创建成功、明确接手或切换目标后才保存关联。新建使用 `reviewable.py init <slug> --project <真实项目> --title <标题> --kind <类型> --no-render`，从返回 JSON 的 task_dir 取真实目录，不手算路径哈希。
- 空输入或“继续”：仅从本会话、本项目的有效关联恢复，不调用省略目标的旧 continue 来猜任务。task 使用 `reviewable.py continue <target.path> --project <target.project_path> --no-render`；feature 使用 `feature.py locate/status <target.path>`，后续按需要推进。
- 无关联、索引损坏或目标失效时，返回实际缺口并在必要时按标题消歧。即使只有一个历史任务也只能视为候选，不默认为本会话目标；明确新目标可经核对后重新 bind，不静默把旧关联改绑到猜测目标。
- status 的明确目标只覆盖本次查询；无明确目标才 resolve，始终不 bind/clear、不修复索引。查看 B 不会把原焦点 A 切换到 B。
- 子代理可能共享父会话标识；只使用显式分配的 task/feature，不修改父会话焦点。会话关联不继承另一个 Agent 的修改、生产或对外操作权限。
- 所有工具位于 `${CLAUDE_PLUGIN_ROOT}/scripts/`，任务默认输出 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`。源码仍在业务仓库。写入被拒绝时如实报告，不能换工具/路径绕过。创建或关联失败需说明未完成且原焦点未切换，不能把旧任务当成本轮新目标。

### 内部关联调用

Claude Code 的 go/status 技能正文提供 `${CLAUDE_SESSION_ID}` 展开值，host 固定为 `claude-code`。详细协议与边界按需读 [session-context.md](session-context.md)。不要假设 Bash 自动有同名变量；ID 仍是占位符、空或 unknown 时，不调用关联写入、不猜 PID/目录，回退到明确任务引用。其他工具只有提供可靠会话标识时才使用各自 host 命名空间。

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" resolve --host claude-code --session "<技能中已展开的本会话ID>" --project "<任务项目或总功能工作区>"
# go：明确核对目标后，使用刚才 resolve 返回的 context_revision（missing 或哈希）
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" bind --host claude-code --session "<已展开ID>" --project "<同一作用范围>" --target-kind task --target "<已核对任务绝对目录>" --expect-revision "<context_revision>"
```

resolve 返回 state、action、context_revision 及 target；只有 state=bound 的 target 才可用于无参数续作。target 为 `{kind,path,id,title,project_path}`，不存在时是 null。bind/clear 是 go 的显式关联变更，版本冲突先重读并核对目标，不盲目重试覆盖。它们不修改 task.json/feature.json、代码或报告。clear 仅在用户明确要求忘记当前关联时使用，不删任务。旧 reviewable CLI 的无目标候选行为为兼容保留，go/status 不将其当会话绑定。

### 仅关联或切换时立即收尾

用户只要求改变本会话焦点，未请求继续业务时，走最短路径：

1. 确认用户给出的目标类型、绝对路径及项目/工作区作用范围。信息已明确时，bind 本身会核验目标事实记录，不必额外扫描源码或反复读取整个任务；缺少必要字段时只补查该目标的元数据。
2. 调用一次 resolve 获取当前 target 和 context_revision。若已是同一有效目标，直接依据返回值确认，不重复 bind。
3. 需要改变时调用一次 CAS bind；以返回的 state=bound、target.kind/path/id/project_path 与 context_revision 确认成功，文字说明当前焦点后结束，不再用第二次 resolve 验证同一次成功返回。

无异常且现成字段足够时，不扫描插件目录、不读取脚本自行重算索引、不调用 continue/render/index，不执行业务测试或重走需求/设计/开发流程。这不是每轮强制工具清单，只适用于确需建立或切换关联的请求。冲突、失效、权限拒绝或返回状态不符合预期时如实说明，并仅针对实际问题重读/调查；不能省略错误或把失败当成功。

## 按需读取内部资料

| 当前问题 | 内部动作文件 | 读取时机 |
|---|---|---|
| 理解现有业务逻辑、数据来源/流转，只分析不改变行为 | analyze.md；需要字段时读 analysis-workflow.md | 目标是解释现状时优先，短问题不强建任务 |
| 模糊需求、行为边界 | start.md、spec.md | 需要明确开发目标行为时 |
| 方案和取舍 | design.md、plan.md | 有实质设计决策时 |
| 实施 | build.md；execution-context.md | 行为已明确且将编辑代码时核对实际 checkout / 活动 |
| 查遗漏与反例 | review.md | 交付前或高风险切片后 |
| 实际验证 | verify.md；execution-context.md | 有可运行实现后；已持有 write 活动时复用，不重复登记 |
| 换人或换工具 | handoff.md、intake.md | 确有交接时；单人不自我交接 |
| 生产事件 | incident.md | 故障诊断和恢复 |
| 日常运维 | ops.md | 检查、变更、维护 |
| 同一功能涉及多个仓库 | docs/cross-project.md | 识别相关项目后先整体设计 |

动作文件位于 docs/internal-actions/。它们保留详细操作参考，不是用户必须逐步调用的流程。内部提到旧阶段命令时视为动作名称，不要求用户调用。文件中的旧“必须加载全部文档”措辞由本入口的按需读取规则替代。

## 每轮保持轻量

只读分析遵循 analyze.md，结束于可追溯解释和明确断点；不要求 implementation、测试或人工验收。其他开发任务遵循探索现状、按需要计划、实施和实际验证的顺序。小改动无需单独计划审批；不明确的关键业务决定集中问，已授权事项持续推进。需要数据字段时读 init 骨架及 docs/schema-reference.md；需要专项展示时读 docs/stage-templates.md；真正交接时读 docs/team-workflow.md。不要每轮加载全部资料。

事实最小集为目标/原因、范围、具体行为和场景、实际实现、验证及待决问题。stage_details 只补有信息价值的内容。固定渲染器决定页面风格，不针对某个任务另造 HTML；模拟场景、真实测试与人工接受必须分开标注。

复核用实际源码、需求和测试；实现者说明仅是线索。无独立代理就标明自审。证据绑定代码与行为，改行为必须重验，补写报告不构成重新测试。页面草稿不代表授权，人工接受不得由 AI 自行勾选。

## 按需产出，不强制每轮 HTML

对话回复、必要事实保存与 HTML 是三个独立动作。目标/范围变化、关键决定、委托、实际实现及证据应及时通过 CAS 保存；是否渲染不影响这些责任。

- 普通解释、追问、进度查询、内部动作和连续小切片默认文字回复，不逐动作 render/index，也不因“阶段完成”强制生成。
- 复杂方案比较、成批验收、需要结构化阅读的阶段成果或正式交接，有实际阅读价值时才生成或复用当前有效报告。简单确认、小修结果可文字交付；不要求用户每轮选择模式。
- 用户明确只要文字时尊重其要求。用户明确索要报告时，先核对事实和已有 report_state；当前有效则可复用，缺失或过期则实际生成并核对链接，不编造页面或已执行结果。
- 事实已更新但本轮未渲染时，已有报告可能过期；需要提及链接时如实称历史快照，missing 时说明尚无报告。未产出 HTML 不等于本轮工作未完成。
- 报告仍使用固定模板。HTML 由本地 Python 渲染，不能以文件字节数推算模型 token；避免重复加载全部指引、回灌完整报告或无必要的全量 JSON 往返，不因此放宽证据、版本及授权校验。
- 生产紧急处置先推进已授权动作并保留现场证据，不能为制作页面阻塞处置。跨项目 feature.html 同样按需，不在每个子动作结束时 sync/render 总览；需要汇总或实施前核对时才使用对应工具。

## 验证与当前行动

按需读取 internal-actions/verify.md，优先用内部 verify 执行现有 unittest/JUnit 检查并绑定已有行为；用户仍只用 go/status。先确定 acceptance_setup 的环境、准备、入口、起始数据与停止方法，以及结构化验收项的预期，再运行验证。没有记录就说明缺失，不编造可用服务或命令。

有 stage_details.acceptance.items 时以其为准，不重复维护旧 acceptance 字符串。actual/reviewer/result/reviewed_revision 是核验记录，不改变行为指纹；新草稿保持未选择。AI 扮演测试角色须标 reviewer_kind=ai，真实人工依据不明确则 unknown，不能替人签字。

primary_action 与 blockers 由脚本派生，focus_stage 仅决定阅读材料。当前失败及 P0/P1 不被待决布局或展示偏好掩盖；高风险发现标 done 后仍需引用当前、无矛盾的通过复查。claim 为模型声明，parsed_result 为已解析回执，invalid 不可采信；三者不混为已验证。

## 从页面接收反馈
用户可在 HTML 填写意见，直接复制可读反馈并粘贴到当前 AI 会话，无需下载 JSON。文本包含任务、代码/行为版本、页面记录版本 task_revision、页面评估版本 assessment_revision 和阶段。先用只读 locate/status 核对任务及这些版本；记录版本不同也可能只是待决问题、选项或实际观察已更新，不能只因行为指纹相同就接受旧反馈。指出差异并针对受影响条目重新确认，不把旧判断默认为对新问题的批准。旧格式缺版本时标未知。只将用户明确填写的选择或意见作为输入，未填写项保持未知。

页面选择由 kind 与当前 focus_stage 决定，使用内置 assets/views/ 的事项专用布局；先核对类型和阶段。具体见 scenario-layouts.md。不能把所有事项套成需求/设计/验收相同目录。

## 首屏的具体主题
标题用业务对象和动作，why 说明当前人的困难，summary 说明实际准备改变的行为，scope 说明本轮范围。当前决定必须给出背景 reason、可选范围 options、推荐依据和确认后的影响 impact（有证据才填写），不要用“理解方案、核对风险”等通用提示代替任务内容。技术方案与业务待决问题不能混在同一优先级，让人不知道应选择哪一个。示例应让读者能用一句话复述“在做什么、这次要我决定什么”。

## 一次只交付当前阶段
需要 HTML 时向用户提供当前任务 report.html；本轮仅文字交付无需附报告。不提供演示总览或把全阶段材料汇总成工作页。phase_sections 按 focus_stage 限定补充材料；阶段专用内容只读取当前阶段，不提供切换历史阶段的控件。examples/index.html 仅用于比较插件模板。多人或跨项目依赖需要整体设计页时另行提供功能总览，不能替代当前阶段交付。

## 实测暴露的路径与交付约束

- CLAUDE_PLUGIN_ROOT 是指引、脚本与模板所在目录，不是待开发项目。首次执行先用 pwd、git rev-parse --show-toplevel 确认业务项目，将其真实路径作为 --project。源码修改前核对目标文件属于该项目；即使任务是修改插件本身，也不能自动修改已加载插件的安装目录。
- 本地报告必须返回实际存在的文件绝对链接。未启动并验证 HTTP 服务时，禁止编造 localhost 地址，尤其不能用 localhost:0 占位。
- 验收或发布阶段已有具体检查项时，检查项及反馈控件应直接出现在主内容区；不要让读者先读完整排障历史再去补充材料找操作。

## 只读定位与安全更新

`/zl-dev:status` 只使用 `reviewable.py locate [任务目录] --project <真实项目>` 和 `status`。locate 返回标题、当前阶段、task_revision、指纹和已有报告路径；报告不存在时 report 为 null，不补建。它不会调用 continue/render/index，也不创建任务目录。go 恢复使用 `continue --no-render`，不重写报告；旧的无标志 continue 为兼容仍会重新渲染，status 不调用它。

修改记录时先运行 locate，读取完整 task.json，将合并后的完整 JSON 保存到系统临时目录，然后执行：

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" update "<真实任务目录>" --project "<绑定项目绝对路径>" --from-file "<临时JSON路径>" --expect-revision "<locate返回的task_revision>"

# 仅本轮确需 HTML 时，保存成功后执行：
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" render "<真实任务目录>"
```

update 使用既有 schema 校验，只允许更新已有、绑定到指定项目的任务，不能改变 id 或 project_path；版本冲突时拒绝覆盖，必须重新读取并合并。可增加 `--expect-fingerprint "<locate返回的fingerprint>"` 检查当前代码及行为契约；它不同于 task_revision，证据和说明变化也会改变 task_revision。fingerprint 为 null 时不能声称已核对代码版本。update 本身不 render；更新失败不执行 render。

在 macOS/Linux 上，同目录临时文件和原子替换保护旧数据，协作 CLI 写入使用文件锁；外部编辑器不遵守锁，不能并发直接编辑 task.json。旧任务缺少绑定时需先人工核对，不能猜测补绑。CLI 不绕过系统权限或 agent 权限：项目外的 ~/.claude/zl-dev 产出访问可能需要对具体任务目录授权；非交互 Claude CLI 的 acceptEdits 不保证自动允许项目外读写或 Bash。拒绝时保留原记录，如实返回失败及待保存内容位置，等待该范围的权限解决，不建议全局 bypass。禁止改用 Write、cp、其他命令或工作区副本规避明确的权限拒绝，也不能声称未保存内容已落盘。

已有非空 revision 的证据必须保留原 id，不能改绑到新指纹；重跑后新增独立证据 id 并保留旧记录，也可清空 revision 显式标为未绑定。此检查防止误改已有记录，无法证明测试实际执行或防止恶意伪造新证据；不得通过改 id、删除旧记录或先清空再重绑来伪装重跑。

locate/status 返回 HANDOFF.md 的 handoff.path 与 freshness（current/stale/unknown/missing），同时核对精确任务版本和代码/行为指纹；发现过期、旧格式未知或缺失时，用 go 重新核对并按需显式导出，先保留手工补充，status 不自动修复或覆盖交接材料。

## 页面与交接资料的时效

locate/status 返回 report_state（current/stale/unknown/missing），核对报告的任务身份、精确记录版本、代码/行为版本及派生评估。回执日志损坏也可能使评估变化，即使 task.json 与源码未改。保留旧 report 路径供追溯，但 stale/unknown 不能称为当前报告；status 只说明问题，不自动 render。go 仅在本轮需要报告时核对后重新生成；否则文字说明实际状态，不把旧页称当前。离线 HTML 不能自行知道外部数据已变化。

HANDOFF.md 的生成区由明确标记管理，人工补充写在标记之外并保留；旧格式先备份到唯一 legacy 文件，新包给出位置，不能静默丢弃。接手包展示同一派生当前行动与阻塞，并说明随包 HTML 是否当前；current 仍不证明服务正在运行，也不是执行授权。

## 人工结果如何推进

仅在人明确回传并核对页面版本后，记录其原意、核验人来源、reviewed_revision（被观察的代码/行为指纹）及 result_status（pass/fail/blocked/not_checked）。reviewer_kind=human 是记录来源，不是身份认证；AI 测试角色仍为 ai。旧 result 自由文本、status=done 或 AI 的 pass 不能推断人工接受。当前 human 或 ai 的 fail/blocked 先由 AI 调查复核，失败事实不依赖接受授权。全部本版项目由人工或明确受托 AI 验收 pass 后停止重复催验，没有真实待决事项则显示当前无需人处理；后续沿用已有授权，不新增放行关卡，报告不执行发布或授予生产权限。历史结果保留，但不代替本版核验。

阶段页使用已有 changes 直接展示最多三条本轮变化，剩余按需展开；记录实际差异和保持项，不从业务 before 字段猜测某个旧实现版本。跨版本接手应核对保存的契约与 Git 历史。

## 明确委托 AI 验收

“帮我跑验收测试”只委托检查，不能推断接受结果。“按这些标准替我验收”才允许在约定范围内由 AI 判断结果是否满足标准。先核对原始用户表述与具体条目；AI 将明确委托保存到 `stage_details.acceptance.items` 对应条目的 `acceptance_delegation`，用户无需填 JSON：

```json
{"kind":"acceptance","revision":"<本版代码/行为指纹>","source":"用户原话：按这些标准替我验收","criteria":"本条标准及委托范围"}
```

只绑定明确被委托的条目，实际执行后保留 `reviewer_kind=ai`、实际观察、`result_status` 和 `reviewed_revision`。不把 source 当身份认证，也不从 AI 自述或模糊授权推断委托。该对象仅适用于本条验收，不允许填入 release 条目，不授予发布或对外操作权限。`human_verification` 保留人工来源语义，`acceptance_verification` 分别投影人工与受托 AI 结果。

本版委托有效而结果缺失或过期时由 AI 继续执行；代码/行为指纹变化时先由 AI 核对原委托是否仍覆盖本版范围和标准。同范围可保留原始来源、更新委托绑定并实际重验；实质变化仅澄清缺失的范围，不能一律要求人工重做，也不能将旧通过记录改绑为新结果。现有检查失败、证据缺口和未解决 P0/P1 不被委托覆盖。

## 报告发布冲突

按需 render 会在发布前核对当前事实、证据评估与 HTML 版本，并与协作事实写入共用锁。旧缓存或晚到结果冲突时保留已有页面；不要改用 Write/cp 或直接编辑 HTML 绕过。必要事实已保存但报告未发布时分别说明，不能把旧链接称为新交付。先用只读 locate/status 核对最新页面；有有效新页面可复用，仍需报告时重新读取当前状态后再按需生成，不无限重试、不因此重跑业务验证。详细边界见 [report-publishing.md](report-publishing.md)。
