# 入口与按需工作流程

用户只用 `/zl-dev:go`（做事/继续）和 `/zl-dev:status`（看状态）；其余是内部资料，不是用户命令。只看已有记录、结论或报告时读 [quick-read.md](quick-read.md)，不必读本页；但短查询不能绕过本页的写入与授权边界。本页用于推进工作、处理反馈/决定、实质调查和改变会话关联，是完整工作流与写入规则的当前来源。内部资料提到旧阶段命令时视为动作名，不要求用户调用。

所有脚本在 `${CLAUDE_PLUGIN_ROOT}/scripts/`。它是插件目录，不是业务项目：先用 `pwd`、`git rev-parse --show-toplevel` 确认业务项目，以其真实路径作为 `--project`。改源码前核对目标文件属于该项目；即使任务是改插件本身，也不修改已加载插件的安装目录。任务默认存于 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，路径取 CLI 返回值，不手算哈希。

## 1. 定位任务

- 先判断意图。普通解释、无新事实的追问：直接回答，不建任务、活动或 HTML，不改关联。
- 本轮明确给出的任务/功能优先。明确的新事项不复用旧焦点；只有一个历史任务也只是候选，不自动接入。
- 新建：`reviewable.py init <slug> --project <项目> --title <标题> --kind <类型> --no-render`，从返回的 `task_dir` 取目录。
- 空输入或“继续”：只从本会话、本项目的有效关联恢复，不调用省略目标的旧 continue 猜任务（其无目标候选输出只为旧 CLI 兼容，不当会话绑定）。task 用 `reviewable.py continue <target.path> --project <target.project_path> --no-render`；feature 用 `feature.py locate/status <target.path>`。无关联、索引损坏或目标失效时说明缺口，必要时按标题让用户选，不猜最近任务，不把旧关联静默改绑到猜测目标。
- 创建或关联失败时说明未完成、原焦点未切换，不把旧任务当成本轮新目标。
- status 的明确目标只覆盖本次查询；无明确目标才 resolve。status 不 bind/clear、不修复索引；查看 B 不把焦点 A 切到 B。
- 子代理只用显式分配的任务，不改父会话焦点。关联不是权限、所有权或代码隔离，也不继承其他 Agent 的修改、生产或对外权限。

### 会话关联

技能正文提供 `${CLAUDE_SESSION_ID}` 展开值，host 固定 `claude-code`；不要假设 Bash 里有同名变量。ID 为空、未展开或 unknown 时不写关联，改用明确任务路径，不用 PID/目录伪造身份。其他工具只有提供可靠会话标识时才用各自 host 命名空间。细节见 [session-context.md](session-context.md)。

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" resolve --host claude-code --session "<已展开ID>" --project "<项目或总功能工作区>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" bind --host claude-code --session "<已展开ID>" --project "<同一范围>" --target-kind task --target "<任务绝对目录>" --expect-revision "<resolve 返回的 context_revision>"
```

- 只有 `state=bound` 的 target 可用于无参数续作。target 为 `{kind,path,id,title,project_path}` 或 null。
- bind/clear 只在 go 中使用，且只在创建成功、明确接手或切换目标并核对后保存关联；status 永不 bind/clear。版本冲突先重读核对，不盲目重试。bind/clear 不修改任务记录、代码或报告。clear 只在用户要求忘记关联时用，不删任务。
- 只要求关联/切换、且目标类型、绝对路径、项目/工作区都已明确时：resolve 一次；已是同一目标就直接确认，否则 CAS bind 一次；以 bind 返回的 state=bound 与 target 文字确认后结束，不再 resolve 二次验证。不列目录、不扫描插件目录或源码、不读脚本自行重算索引、不读任务全文、不调 continue/render/index、不跑业务测试、不进入开发。缺字段或返回异常时才针对问题补查，不把失败当成功。

## 2. 按需读取动作

动作文件在 `docs/internal-actions/`，只读本轮需要的动作；已在上下文中的当前版本不重复读。上下文丢失、插件版本变化或遇到真实矛盾时重读。历史 go-design 文档不是当前执行指令。

| 本轮事项 | 读取 | 仅在需要时追加 |
|---|---|---|
| 解释现有逻辑/数据来源，不改行为 | analyze.md | 字段不清时 analysis-workflow.md |
| 模糊需求、行为边界 | start.md、spec.md | |
| 方案取舍 | design.md、plan.md | |
| 实施（行为已明确） | build.md | 编辑代码前 execution-context.md |
| 查遗漏与反例（交付前或高风险切片后） | review.md | |
| 实际验证（有可运行实现后） | verify.md | 执行前 execution-context.md（已持有 write 活动则复用） |
| 换人/换工具（单人续作不自我交接） | handoff.md、intake.md | 角色真的变化时 team-workflow.md；运行依赖存在才查服务 |
| 生产事件 / 日常运维 | incident.md / ops.md | |
| 多个仓库同一功能 | cross-project.md，先整体设计 | 实施前 preflight |

新增字段才读 schema-reference.md；专项展示才读 stage-templates.md。workflow.md 是扩展参考，不是必读中转。减少读取不能省略源码、当前事实、CAS、证据或权限核对。

## 3. 推进工作

- 先读项目的 CLAUDE.md/AGENTS.md 和相关源码，不臆造工具链。缺陷先复现，或记录无法复现的条件。
- 开发顺序：探索 → 按需计划 → 实施 → 实际验证。小改动不需要计划审批。关键业务未知集中提问；已授权的工作持续推进，不逐阶段等“继续”。
- 只读分析按 analyze.md，结束于可追溯的解释和明确断点，不要求实现、测试或人工验收。
- 生产默认只读诊断。写操作须有具体授权、对象范围、停止条件和恢复方法；已有同范围授权不重复问。
- 复核以源码、需求和测试为准，实现者说明只是线索。没有独立代理时标明自审。使用独立代理须符合宿主能力和本轮授权，不因插件提到 reviewer 就绕过环境限制。
- 必要事实：目标/原因、范围、具体行为与场景、实际实现、验证、待决问题。stage_details 只补有信息量的内容。模拟、真实测试、人工接受分开标注。固定渲染器决定页面风格，不为某个任务另造 HTML。
- 证据绑定代码与行为：改行为必须重验，补写报告不等于重新测试。页面草稿不代表授权，AI 不得自行勾选人工接受。

## 4. 保存事实

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" locate "<任务目录>" --project "<真实项目>"
# 读取完整 task.json，把合并后的完整 JSON 写到系统临时目录，然后：
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" update "<任务目录>" --project "<绑定项目>" --from-file "<临时JSON>" --expect-revision "<task_revision>"
```

- locate/status 只读：返回标题、阶段、task_revision、指纹和已有报告路径；报告不存在时 report 为 null，不补建，也不调 continue/render/index 或建目录。status 只用 locate 和 status。go 恢复用 `continue --no-render`；旧的无标志 continue 仍会渲染，status 不调用。
- 路径用绝对路径直接写在命令里；CLI 收到空目录参数会报错。
- update 校验 schema、项目绑定和版本；冲突时拒绝，需重读合并。不能改 id 或 project_path。update 不 render。
- `--expect-fingerprint` 额外核对代码与行为契约；fingerprint 为 null 时不能声称已核对代码版本。
- task.json、feature.json、报告和会话记录只能经 CLI 修改；插件 hook 会拒绝直接改写。写入被拒绝时保留原记录，如实报告失败和待保存内容的位置，等待该范围的权限解决；不换工具、路径或副本绕过，不建议全局 bypass，不声称未保存的内容已落盘。外部编辑器不遵守 CLI 文件锁，不能并发直接编辑。
- 已有 revision 的证据保留原 id，不改绑新指纹；重跑新增独立证据 id 并保留旧记录；也可清空 revision 显式标为未绑定。不能用改 id、删旧记录或先清空再绑来伪装重跑。
- 旧任务缺少项目绑定时先人工核对，不猜测补绑。

## 5. 产出：回复、事实、HTML 相互独立

- 目标/范围变化、关键决定、委托、实际实现和证据要及时经 CAS 保存，与是否生成 HTML 无关。
- 默认文字回复：普通解释、追问、进度、内部动作、小切片、简单确认、小修结果。不逐动作 render/index，不因“阶段完成”强制建页，不要求用户每轮选择模式。避免回灌完整报告或无必要的全量 JSON 往返，但不因此放宽证据、版本和授权校验。
- 有实际阅读价值时才生成或复用报告：复杂方案比较、成批验收、需要结构化阅读的阶段成果、正式交接，或用户明确索要。
- 用户索要报告：先核对事实和已有 report_state。current 直接复用；missing/stale/unknown 才 render 并核对链接，不编造页面或执行结果。缺报告不阻塞任务；模板变化不重跑业务验证。用户只要文字时尊重。
- 事实已更新但未渲染时，旧报告是历史快照（保留路径供追溯），不称当前；missing 说明尚无报告。
- 生产紧急处置先推进已授权动作并保留现场证据，不为做页面阻塞。跨项目 feature.html 同样按需，不在每个子动作后 sync/render。
- 链接必须是实际存在的文件绝对路径；未启动并验证服务时不编造 localhost 地址。

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" render "<任务目录>"   # 仅本轮确需 HTML 时，保存成功后
```

render 会核对事实、评估、模板和现有 HTML；内容一致时不重写。发布冲突时保留已有页面，不用 Write/cp 或改 HTML 绕过；事实已保存而报告未发布时分别说明，不把旧链接称为新交付；重读状态后按需再生成，不无限重试，不重跑业务验证。细节见 [report-publishing.md](report-publishing.md)、[report-reuse.md](report-reuse.md)。

## 6. 报告内容

- 页面布局由 kind 和 focus_stage 决定（assets/views/，见 scenario-layouts.md）。只交付当前阶段的 report.html，不提供演示总览、全阶段合集或切换历史阶段的控件；phase_sections 按 focus_stage 限定。examples/ 只用于比较模板。跨项目整体设计页另行提供，不替代当前阶段交付。先核对类型和阶段，不把所有事项套成同一目录。
- 标题写业务对象和动作；why 写人当前的困难；summary 写要改变的行为；scope 写本轮范围。
- 待决事项给出 reason、options、推荐依据和 impact（impact 有证据才写）。技术方案与业务问题分开排优先级，不用“理解方案、核对风险”之类通用话。
- 阶段页用 changes 展示最多三条本轮变化，其余按需展开。记录实际差异和保持项，不从业务 before 字段猜旧实现版本；跨版本接手核对保存的契约与 Git 历史。
- 已有具体检查项的验收/发布阶段，检查项和反馈控件放在主内容区。

## 7. 验证与验收

- 验证读 verify.md，优先用内部 verify 执行项目已有的 unittest/JUnit 并绑定行为。先确定 acceptance_setup（环境、准备、入口、起始数据、停止方法）和结构化验收项的预期。缺少就说明，不编造服务或命令。
- 有 `stage_details.acceptance.items` 时以其为准，不再维护旧 acceptance 字符串。actual/reviewer/result/reviewed_revision 是核验记录，不改变行为指纹；新草稿保持未选择。AI 扮演测试角色标 `reviewer_kind=ai`；人工来源不明确标 unknown，不能替人签字。
- primary_action 与 blockers 由脚本派生。当前失败和 P0/P1 不能被布局或展示偏好掩盖。高风险发现标 done 后仍需引用当前、无矛盾的通过复查。claim（模型声明）、parsed_result（已解析回执）、invalid（不可采信）不能混为已验证。
- 人工结果：只有人明确回传并核对页面版本后，才记录原意、来源、reviewed_revision 和 result_status（pass/fail/blocked/not_checked）。旧自由文本、status=done 或 AI 的 pass 不能推断人工接受。reviewer_kind=human 是记录来源，不是身份认证。当前 fail/blocked 先由 AI 调查，失败事实不依赖接受授权。本版全部项目已被人工或受托 AI 验收 pass 后不再催验，没有真实待决事项时显示当前无需人处理；沿用已有授权，不新增放行关卡；报告不授予发布或生产权限。历史结果保留，但不代替本版核验。
- 委托 AI 验收：“帮我跑验收测试”只委托检查；“按这些标准替我验收”才允许 AI 在范围内判断。先核对用户原话与具体条目；不把 source 当身份认证，不从 AI 自述或模糊授权推断委托。把委托写入对应 `stage_details.acceptance.items` 的 `acceptance_delegation`：

```json
{"kind":"acceptance","revision":"<本版代码/行为指纹>","source":"用户原话：按这些标准替我验收","criteria":"本条标准及委托范围"}
```

  执行后保留 reviewer_kind=ai、实际观察、result_status 和 reviewed_revision。委托只绑定明确被委托的条目，不适用于 release，不授予发布或对外操作权限。指纹变化时先核对原委托是否仍覆盖本版；本版委托有效而结果缺失或过期时由 AI 继续执行。同范围可保留原始来源、更新绑定并实际重验，不把旧通过改绑为新结果；实质变化只澄清缺失范围，不一律要求人工重做。当前失败、证据缺口和未解决 P0/P1 不被委托覆盖。

## 8. 时效与反馈

- locate/status 返回 report_state 和 handoff.freshness（current/stale/unknown/missing），核对任务身份、记录版本、代码/行为版本和派生评估。stale/unknown 不称当前；status 只说明，不修复。回执日志损坏也会让评估变化。交接包 stale/unknown/missing 时用 go 重新核对并按需显式导出。离线 HTML 不知道外部数据已变化。
- HANDOFF.md 生成区之外的人工补充保留；旧格式先备份为唯一 legacy 文件并给出新包位置，不静默丢弃；接手包说明随包 HTML 是否当前。current 不证明服务在运行，也不是执行授权。
- 页面反馈带任务、代码/行为版本、task_revision、assessment_revision 和阶段。先用只读 locate 核对；版本不同时指出差异，对受影响条目重新确认；不能只因行为指纹相同就接受旧反馈（待决项或选项可能已变），不把旧判断当新批准。缺版本标未知；只采用用户实际填写的内容，未填写项保持未知。
