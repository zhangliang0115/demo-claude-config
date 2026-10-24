# 两个入口与按需工作流程

用户只需 `/zl-dev:go`（做事/继续）和 `/zl-dev:status`（看状态）。其余动作是插件内部资料，不注册斜杠命令。旧版阶段命令已撤下；旧任务数据和 CLI 仍可继续使用。

## 任务定位

- 新描述先判断是否延续当前明确任务。只有一个历史任务也不能据此自动接入新需求。
- 无参数或明确说“继续”：运行 reviewable.py continue --project，单个任务可继续，多个任务按标题简短询问。
- 使用返回的真实任务路径，不手算项目路径哈希。不确定是否延续时只问一个简短问题。
- 新建：reviewable.py init <slug> --project <真实项目绝对路径> --title <标题> --kind <类型>。读取生成 task.json 后按下述安全更新流程维护，render 更新。
- 所有工具位于 `${CLAUDE_PLUGIN_ROOT}/scripts/`，默认输出 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`。源码仍在业务仓库。脚本参数用独立参数和正确引号，不能将需求拼成可执行代码。

## 按需读取内部资料

| 当前问题 | 内部动作文件 | 读取时机 |
|---|---|---|
| 模糊需求、行为边界 | start.md、spec.md | 缺少目标行为时 |
| 方案和取舍 | design.md、plan.md | 有实质设计决策时 |
| 实施 | build.md | 行为已明确后 |
| 查遗漏与反例 | review.md | 交付前或高风险切片后 |
| 实际验证 | verify.md | 有可运行实现后 |
| 换人或换工具 | handoff.md、intake.md | 确有交接时；单人不自我交接 |
| 生产事件 | incident.md | 故障诊断和恢复 |
| 日常运维 | ops.md | 检查、变更、维护 |
| 同一功能涉及多个仓库 | docs/cross-project.md | 识别相关项目后先整体设计 |

动作文件位于 docs/internal-actions/。它们保留详细操作参考，不是用户必须逐步调用的流程。内部提到旧阶段命令时视为动作名称，不要求用户调用。文件中的旧“必须加载全部文档”措辞由本入口的按需读取规则替代。

## 每轮保持轻量

遵循探索现状、按需要计划、实施和实际验证的顺序。小改动无需单独计划审批；不明确的关键业务决定集中问，已授权事项持续推进。需要数据字段时读 init 骨架及 docs/schema-reference.md；需要专项展示时读 docs/stage-templates.md；真正交接时读 docs/team-workflow.md。不要每轮加载全部资料。

事实最小集为目标/原因、范围、具体行为和场景、实际实现、验证及待决问题。stage_details 只补有信息价值的内容。固定渲染器决定页面风格，不针对某个任务另造 HTML；模拟场景、真实测试与人工接受必须分开标注。

复核用实际源码、需求和测试；实现者说明仅是线索。无独立代理就标明自审。证据绑定代码与行为，改行为必须重验，补写报告不构成重新测试。页面草稿不代表授权，人工接受不得由 AI 自行勾选。

## 验证与当前行动

按需读取 internal-actions/verify.md，优先用内部 verify 执行现有 unittest/JUnit 检查并绑定已有行为；用户仍只用 go/status。先确定 acceptance_setup 的环境、准备、入口、起始数据与停止方法，以及结构化验收项的预期，再运行验证。没有记录就说明缺失，不编造可用服务或命令。

有 stage_details.acceptance.items 时以其为准，不重复维护旧 acceptance 字符串。actual/reviewer/result/reviewed_revision 是核验记录，不改变行为指纹；新草稿保持未选择。AI 扮演测试角色须标 reviewer_kind=ai，真实人工依据不明确则 unknown，不能替人签字。

primary_action 与 blockers 由脚本派生，focus_stage 仅决定阅读材料。当前失败及 P0/P1 不被待决布局或展示偏好掩盖；高风险发现标 done 后仍需引用当前、无矛盾的通过复查。claim 为模型声明，parsed_result 为已解析回执，invalid 不可采信；三者不混为已验证。

## 从页面接收反馈
用户可在 HTML 填写意见，直接复制可读反馈并粘贴到当前 AI 会话，无需下载 JSON。文本包含任务、版本和阶段。先确认对应任务及页面版本；若版本已变，指出受影响条目并重新核对，不把旧反馈默认为最新批准。只将用户明确填写的选择或意见作为输入，未填写项保持未知。

页面选择由 kind 与当前 focus_stage 决定，使用内置 assets/views/ 的事项专用布局；先核对类型和阶段。具体见 scenario-layouts.md。不能把所有事项套成需求/设计/验收相同目录。

## 首屏的具体主题
标题用业务对象和动作，why 说明当前人的困难，summary 说明实际准备改变的行为，scope 说明本轮范围。当前决定必须给出背景 reason、可选范围 options、推荐依据和确认后的影响 impact（有证据才填写），不要用“理解方案、核对风险”等通用提示代替任务内容。技术方案与业务待决问题不能混在同一优先级，让人不知道应选择哪一个。示例应让读者能用一句话复述“在做什么、这次要我决定什么”。

## 一次只交付当前阶段
向用户提供当前任务 report.html，不提供演示总览或把全阶段材料汇总成工作页。phase_sections 按 focus_stage 限定补充材料；阶段专用内容只读取当前阶段，不提供切换历史阶段的控件。examples/index.html 仅用于比较插件模板。多人或跨项目依赖需要整体设计页时另行提供功能总览，不能替代当前阶段交付。

## 实测暴露的路径与交付约束

- CLAUDE_PLUGIN_ROOT 是指引、脚本与模板所在目录，不是待开发项目。首次执行先用 pwd、git rev-parse --show-toplevel 确认业务项目，将其真实路径作为 --project。源码修改前核对目标文件属于该项目；即使任务是修改插件本身，也不能自动修改已加载插件的安装目录。
- 本地报告必须返回实际存在的文件绝对链接。未启动并验证 HTTP 服务时，禁止编造 localhost 地址，尤其不能用 localhost:0 占位。
- 验收或发布阶段已有具体检查项时，检查项及反馈控件应直接出现在主内容区；不要让读者先读完整排障历史再去补充材料找操作。

## 只读定位与安全更新

`/zl-dev:status` 只使用 `reviewable.py locate [任务目录] --project <真实项目>` 和 `status`。locate 返回标题、当前阶段、task_revision、指纹和已有报告路径；报告不存在时 report 为 null，不补建。它不会调用 continue/render/index，也不创建任务目录。continue 是推进入口，会重新渲染报告，不能用于只读查询。

修改记录时先运行 locate，读取完整 task.json，将合并后的完整 JSON 保存到系统临时目录，然后执行：

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" update "<真实任务目录>" --project "<绑定项目绝对路径>" --from-file "<临时JSON路径>" --expect-revision "<locate返回的task_revision>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" render "<真实任务目录>"
```

update 使用既有 schema 校验，只允许更新已有、绑定到指定项目的任务，不能改变 id 或 project_path；版本冲突时拒绝覆盖，必须重新读取并合并。可增加 `--expect-fingerprint "<locate返回的fingerprint>"` 检查当前代码及行为契约；它不同于 task_revision，证据和说明变化也会改变 task_revision。fingerprint 为 null 时不能声称已核对代码版本。update 本身不 render；更新失败不执行 render。

在 macOS/Linux 上，同目录临时文件和原子替换保护旧数据，协作 CLI 写入使用文件锁；外部编辑器不遵守锁，不能并发直接编辑 task.json。旧任务缺少绑定时需先人工核对，不能猜测补绑。CLI 不绕过系统权限或 agent 权限：项目外的 ~/.claude/zl-dev 产出访问可能需要对具体任务目录授权；非交互 Claude CLI 的 acceptEdits 不保证自动允许项目外读写或 Bash。拒绝时保留原记录，如实返回失败及待保存内容位置，等待该范围的权限解决，不建议全局 bypass。禁止改用 Write、cp、其他命令或工作区副本规避明确的权限拒绝，也不能声称未保存内容已落盘。

已有非空 revision 的证据必须保留原 id，不能改绑到新指纹；重跑后新增独立证据 id 并保留旧记录，也可清空 revision 显式标为未绑定。此检查防止误改已有记录，无法证明测试实际执行或防止恶意伪造新证据；不得通过改 id、删除旧记录或先清空再重绑来伪装重跑。

locate/status 返回 HANDOFF.md 的 handoff.path 与 freshness（current/stale/unknown/missing），同时核对精确任务版本和代码/行为指纹；发现过期、旧格式未知或缺失时，用 go 重新核对并按需显式导出，先保留手工补充，status 不自动修复或覆盖交接材料。
