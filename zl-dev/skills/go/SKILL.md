---
name: go
description: 描述需求、问题或反馈，理解现状后推进开发和运维，并生成固定交互式说明页。
argument-hint: "[需求、反馈、任务名，或留空继续]"
disable-model-invocation: true
user-invocable: true
---

用户输入：$ARGUMENTS

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`。你负责定位、推进和记录，用户无需选择阶段或填表。

1. 定位当前真实项目。新需求先检查相关代码和现有任务，不能因只有一个历史任务就将新需求接入其中；只有明确延续同一目标才复用。空输入或“继续”调用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" continue --project "<项目绝对路径>"`；多个候选用标题简短询问，不自动选最近任务。
2. 探索 → 计划 → 实现 → 验证。先读取项目约定和必要源码，用具体输入/操作/输出说明你理解的目标；按风险决定是否需要计划，小改动直接推进。仅集中询问影响结果的关键未知；其余明确授权工作继续。不要每阶段等待“继续”。
3. 已识别多个仓库时按需读取 `docs/cross-project.md`，先读各项目实际能力并整体设计，再拆实施任务；单人和多人共用同一方案。共享规则变化先保存新版总方案与各项目绑定，再运行 feature.py preflight；失败时不得开始依赖这些约定的实施。preflight 是只读检查，不能代替人工决定，也不能技术上拦截任意代码编辑。
4. 只读取当前需要的 `docs/internal-actions/<动作>.md`，不预加载所有阶段。发现缺陷先复现；生产问题先只读诊断，写操作必须具备具体授权、范围、停止条件和恢复方法。只做本轮相关改动。
5. 先确定环境准备与结构化验收预期，再实际验证。优先按 docs/internal-actions/verify.md 用内部 verify 执行项目已有 unittest/JUnit 并绑定相关行为，不能为获得通过摘要而造空测试。其他检查保留真实来源，区分模型声明与解析回执。界面变更操作真实控件；独立审查可用时调用 reviewer，否则标明自审。当前失败与未解决 P0/P1 先修复重验，不因展示阶段或布局待决转给人兜底。人工观察和本次草稿分开，AI 测试角色标 ai，不代人勾选通过。接收反馈时核对 task_revision 与 assessment_revision，不只比较代码/行为指纹；人明确反馈后按其原意记录 result_status 和 reviewed_revision，旧页反馈先说明变化并重新核对。当前人工退回先处理，全部本版核验已记录则交负责人决定后续，不自动放行。
6. 先 locate 取得 task_revision，将完整新数据写入临时 JSON，再用 reviewable.py update --from-file 和 --expect-revision 校验、原子更新，之后 render 同一 HTML。写入被权限拒绝时如实报告，不能改用 Write/cp 或换路径绕过。同步更新标题、概述与实际实现说明，避免修复后仍描述为待修；不要据此改写目标或把旧证据改绑为当前。明确 focus_stage，只呈现当前阶段；其他阶段记录留在数据中。实际交付直接链接当前任务 report.html，不能用 examples/index.html 或所有阶段合集代替。最终返回前核对 update 实际成功且 render 实际成功；未保存或未生成就明确未完成及原因，不能只用将来时计划结束或把旧报告当新交付。用任务类型和阶段说明“是什么、为什么、目前发生了什么、下一步谁做什么”，不要求填满所有阶段。返回报告绝对链接、实际验证和一条下一步。人未核验不能宣称人工验收通过。

例：`/zl-dev:go 给订单列表增加客户筛选，翻页保持条件。先看现有实现，完成后验证筛选与翻页。`
例：`/zl-dev:go 生产订单查询超时，先只读排查，给出影响、证据和建议；不要修改生产。`
例：`/zl-dev:go 管理台支持取消订单，相关仓库 /workspace/admin 和 /workspace/orders。先整体理解和设计，再确定各项目改动。`
