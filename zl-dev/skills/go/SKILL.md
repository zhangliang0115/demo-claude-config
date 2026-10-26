---
name: go
description: 描述需求、问题或反馈，理解现状后推进开发和运维，按需生成固定交互式说明页。
argument-hint: "[需求、反馈、任务名，或留空继续]"
disable-model-invocation: true
user-invocable: true
---

用户输入：$ARGUMENTS

宿主：claude-code；本会话 ID：`${CLAUDE_SESSION_ID}`。这是技能正文替换值，不是要求读取同名 shell 环境变量。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`。你负责定位、推进和记录，用户无需选择阶段或填表。

1. 先区分普通问答、新事项、明确目标与续作。普通解释、追问和进度回复不为产出报告新建任务或写会话关联。明确新事项不得先沿用旧焦点；本轮明确任务/功能引用优先。空输入或“继续”先按 entry-workflow.md 的会话关联流程只读 resolve：仅 state=bound 时使用返回的 target.kind/path；无关联或失效时消歧，不能因项目只有一个历史任务就自动续作，也不选最近任务。go 在已核对的目标被创建、接手或明确切换后，用 context_revision 做 CAS bind；用户无需维护 ID。任务恢复显式调用 `reviewable.py continue "<target.path>" --project "<任务项目>" --no-render`，整体功能用 feature.py 的只读定位/状态。无可靠会话 ID 时用明确任务引用，不伪造绑定；子代理只处理显式分配目标，不切换父会话焦点。
仅关联/切换的短路径：用户只要求“把本会话关联到/切换到某任务”，未要求推进业务时，核对明确目标的类型、路径与作用范围 → resolve → 必要时用返回的 context_revision 做一次 CAS bind → 以返回的 state=bound、target 和 context_revision 确认后文字结束。相同有效焦点不重复 bind。字段足够且无异常时，不扫描插件目录、不读取脚本重算、不反复查询，也不调用 continue/render/index 或业务验证；下列开发/验证要求不适用于这个纯关联操作。真实错误需说明，必要时才针对错误调查。

2. 用户目标是解释现有业务或追踪数据且未要求改变行为时，按 docs/internal-actions/analyze.md 走 kind=analysis 的独立只读流程；短问题可直接答，不为格式创建任务，不套实施/测试/验收。仅开发前需要分析时仍沿原开发目标，不按关键词强行改类型。其他开发任务按探索 → 计划 → 实现 → 验证。先读取项目约定和必要源码，用具体输入/操作/输出说明你理解的目标；按风险决定是否需要计划，小改动直接推进。仅集中询问影响结果的关键未知；其余明确授权工作继续。不要每阶段等待“继续”。
3. 跨项目只读追踪按 analysis-workflow.md 声明额外源码范围，不创建实施分工或执行 preflight。涉及开发或共享规则变更且已识别多个仓库时按需读取 `docs/cross-project.md`，先读各项目实际能力并整体设计，再拆实施任务；单人和多人共用同一方案。共享规则变化先保存新版总方案与各项目绑定，再运行 feature.py preflight；失败时不得开始依赖这些约定的实施。preflight 是只读检查，不能代替人工决定，也不能技术上拦截任意代码编辑。
4. 开始持续实施、审查或实际测试前，按需读 `docs/execution-context.md`，核对真实 checkout 与已登记活动。编辑/验证前用 workspace.py 申请 write/verify 活动；冲突先解决执行位置或串行安排，不把不同任务目录视为代码隔离。只读分析仅可 read。活动不授予权限、不自动建 worktree；结束时核对已停止后结束本会话活动，异常遗留不自动过期。普通问答、状态查询和仅关联不新增活动。缺可靠会话ID不伪造登记，按 execution-context.md 的明确任务/单执行者回退处理，不把登记当授权门禁。

只读取当前需要的 `docs/internal-actions/<动作>.md`，不预加载所有阶段。发现缺陷先复现；生产问题先只读诊断，写操作必须具备具体授权、范围、停止条件和恢复方法。只做本轮相关改动。
5. 先确定环境准备与结构化验收预期，再实际验证。优先按 docs/internal-actions/verify.md 用内部 verify 执行项目已有 unittest/JUnit 并绑定相关行为，不能为获得通过摘要而造空测试。其他检查保留真实来源，区分模型声明与解析回执。界面变更操作真实控件；独立审查可用时调用 reviewer，否则标明自审。当前失败与未解决 P0/P1 先修复重验，不因展示阶段或布局待决转给人兜底。人工观察和本次草稿分开，AI 测试角色标 ai，不代人勾选通过。接收反馈时核对 task_revision 与 assessment_revision，不只比较代码/行为指纹；人明确反馈后按其原意记录 result_status 和 reviewed_revision，旧页反馈先说明变化并重新核对。当前人工或 AI 的明确失败先调查复核。仅“跑测试”不等于委托接受结果；用户明确委托按标准代验时，按 entry-workflow.md 记录本条 acceptance_delegation 并由 AI 执行，不冒充人工。全部本版验收已记录后不要求重复核验或新增放行问题，后续沿用已有授权；报告本身不自动发布。
6. 先 locate 取得 task_revision，将完整新数据写入临时 JSON，再用 reviewable.py update --from-file 和 --expect-revision 校验、原子更新，必要事实及时保存，HTML 按 entry-workflow.md 的产出策略独立决定。写入被权限拒绝时如实报告，不能改用 Write/cp 或换路径绕过。同步更新标题、概述与实际实现说明，避免修复后仍描述为待修；不要据此改写目标或把旧证据改绑为当前。明确 focus_stage，只呈现当前阶段；其他阶段记录留在数据中。只有确需报告时才 render 当前任务 report.html，不能用 examples/index.html 或所有阶段合集代替。普通问答、内部步骤及简单阶段成果可文字交付，不逐动作 render/index。最终核对必要记录已实际保存；本轮无需 HTML 不影响工作完成。用户明确要求报告时必须核对生成成功及真实链接；缺失或过期报告如实说明，不把旧页当新交付。用任务类型和阶段说明“是什么、为什么、目前发生了什么、下一步谁做什么”，不要求填满所有阶段。返回本轮实际结果、适用的验证和一条下一步；本轮生成或复用报告时才附绝对链接。人未核验不能宣称人工验收通过。

例：`/zl-dev:go 给订单列表增加客户筛选，翻页保持条件。先看现有实现，完成后验证筛选与翻页。`
例：`/zl-dev:go 生产订单查询超时，先只读排查，给出影响、证据和建议；不要修改生产。`
例：`/zl-dev:go 管理台支持取消订单，相关仓库 /workspace/admin 和 /workspace/orders。先整体理解和设计，再确定各项目改动。`
