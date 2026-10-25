# 内部动作：verify

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：当前任务输入（由 go 路由提供）

先确定环境准备、起始数据及结构化验收预期，再从行为约定选择实际检查，不仅复述已有测试。有 stage_details.acceptance.items 时以其为准，避免与旧 acceptance 字符串分叉。acceptance_setup 和验收预期参与行为版本；actual/reviewer/result/reviewed_revision 等观察元数据不改变行为指纹。AI 测试角色标 reviewer_kind=ai，不代替人工签字或预选通过。仅跑测试不等于委托接受结果；明确委托按标准代验时，按 entry-workflow.md 保存 acceptance_delegation，由 AI 实际执行并记录本版结果。有效委托但结果未完成由 AI 继续；版本变化先核对范围，不能机械转为人工重验，也不能改绑旧通过记录。当前 AI 的明确失败即使没有接受授权也先调查复核。

优先使用内部执行器运行项目已有测试。以下任务目录、项目、行为 ID 与测试路径需替换为实际值；`--` 后是原样 argv，在绑定项目中执行，不经 shell 拼接：

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" verify "<任务目录>" --project "<源码项目绝对路径>" --format unittest --behavior B1 -- python3 -m unittest discover -s tests -v
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" verify "<任务目录>" --project "<源码项目绝对路径>" --format junit --behavior B1 --behavior B2 --result-file "/tmp/zl-dev-<本次唯一ID>.xml" -- pytest --junitxml="/tmp/zl-dev-<本次唯一ID>.xml"
```

JUnit 示例仅适用于项目已使用 pytest；其他工具使用其真实 JUnit 参数。两处结果路径须相同、每次新建且运行前不存在；优先写项目外，或确认是 Git 忽略路径，否则测试产物本身会改变源码指纹而不能绑定本次结果。不要删旧结果冒充新运行。执行器保存日志、结果摘要与前后指纹，稳定时追加关联行为的证据；检查未启动、超时、摘要无法解析、任务或指纹变化都不能当作有效通过。`render` 是独立动作。

只绑定测试实际覆盖的行为。含部分 skip 的套件保守视为 not_run，不能用其余成功数推断所绑定行为全部通过；必要时拆开运行相关检查，保留原跳过记录。解析数量不是业务覆盖率，回执和哈希不是身份认证或防伪签字。旧 evidence 继续作为 claim 模型声明；有效回执为 parsed_result，无效回执为 invalid 并降级，不能手填 parsed_result 冒充解析。

没有支持的结果格式时仍执行真实检查并记录原始来源、前后 fingerprint，明确只是模型记录。二者一致且检查结果真实时才能绑定 evidence.revision；变化则重验。数量从机器结果核算，不凭印象总结，不将后来修改的业务约定追溯绑定旧测试。当前失败与未解决 P0/P1 优先；done 的高风险发现仍须引用当前、无矛盾的通过复查，focus_stage 不抹除阻塞。

按行为风险补充验证：涉及并发、重试、幂等、超时或恢复时，选择可能相互作用的故障组合，核对先后顺序与中间状态；不要求每次穷举所有类型。单项测试通过不能替代关键组合路径。

同时核对持久化状态、页面文案和用户实际可执行的动作。通过真实控件操作确认可编辑、可提交或应被阻止；脚本直接赋值不能证明控件可操作。响应或重放记录可能只说明历史操作结果，不能直接当作当前事实；刷新失败或结果未确认时，验证页面是否明确表达未知状态，并阻止依赖已确认当前状态的后续修改。保留每一步的版本、请求结果与存储核对依据。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。

已绑定版本的证据不能改绑 revision 或改 id 替换旧记录；重跑须保留旧证据并新增本次独立 id，也可清空 revision 显式失效。CLI 仅阻止有限误操作，不能证明执行真实性或防止伪造新记录。

界面验证按需求指定的终端范围执行；未要求移动端时不默认增加手机尺寸测试。本项目默认验证桌面网页。可运行夹具可用于贴近真实业务的场景评测，但需求/角色输入、实际执行者、原始结果与真实人工接受要分别标注。
