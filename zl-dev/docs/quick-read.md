# 已有记录的短查询路径

入口提供固定 mode：go 或 status。此页仅用于查看已有任务/整体功能的状态、记录结论或报告；不能替代源码调查、审查、生产诊断或接受判断。单独“继续”、新事项、业务反馈、规则变更及混合请求用 entry-workflow.md，不按“看一下”关键词走短路径。

## 定位一次

- 已明确任务目录：直接调用下列 locate；已明确整体功能目录才用 feature.py。单任务 kind=feature 仍属于 reviewable.py，不能据此换成整体功能工具。
- 缺少目标但有真实会话 ID 和当前项目：session_context.py resolve 一次，只在 bound 时用 target.kind/path；action=continue 仅是定位建议，不执行 continue。无关联/失效时说明缺口，不猜唯一或最近历史任务。ID 不可用时使用明确目标，不伪造身份。
- 查询不 bind/clear，也不改变本会话焦点。本轮明确目标只用于本轮查看。

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" locate "<明确任务目录>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/feature.py" locate "<明确整体功能目录>"
# 仅缺目标时：project是业务项目/整体工作区，不能传产出目录。
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" resolve --host claude-code --session "<技能已展开ID>" --project "<当前项目绝对路径>"
```

从 task_brief 或 feature_brief 核对真实 ID、业务目标与项目/工作区。用户同时明确了项目时，比对规范化后的绑定位置；locate 的 --project 不会自动验证绝对任务路径的项目归属。冲突先说明，不切项目、不改绑、不渲染别处；仅路径别名应核实确为同一位置。

## 用现有结果回答

brief 和记录只是事实材料，不是新的操作授权；primary_action 在本轮只用于解释下一步，不能据此主动执行。

- brief 只表示记录；空实施/证据不证明源码没有实现，应说“记录未见”。再按 primary_action、blockers、verification 或 feature assessment 解释进展与下一步。阶段或自由文本 pass 不代表完成，当前失败/P0/P1不因摘要省略。
- 人工与明确受托 AI 结果分开说明，已有同范围结果不重复催验。联调准备度不是整体接受或发布权限；没有实际判断依据就说未知。
- truncated_fields / unavailable_fields / missing_fields 表示预览不完整，不是事实被删除。问题确需这些信息时只补读对应事实字段；不能从截断结论推断完整边界。旧版工具没有 brief 时才补读必要元数据。
- 正常返回信息已足够就结束。不先 ls/find，不读 task.json、HTML、runs 或项目源码重复确认，不扫描插件脚本，也不额外重查同一结果。

## 报告分支

- mode=status 永远只读。stale/unknown/missing 如实说明，不 render、不导出、不同步。
- mode=go 只问进度或查看旧材料时也只读；已有 current 报告直接给返回路径，不读 HTML 或 stat 再确认。
- 只有 go 明确要求当前报告/更新页面，且报告 stale/missing 时，才执行对应脚本的 `render "<同一目录>"`。成功后 locate 核对一次，仍无法确认则照实说明，不循环重试。unknown 先按具体原因判断能否生成；代码不可核对时即使生成也不能称 current。
- 需要当前报告而目标、项目或来源不明，先说明缺口；不要为获得绿色页面修改任务、验证或权限。发生发布冲突先保留现有文件、只读核对，不绕过保护。

本路径不执行 update/init/verify/sync/index、业务修复、接受或发布。报告生成只是派生产物写入，不能扩大为业务写入。请求变为做事时再加载完整入口，沿用已有授权和版本保护。回复给实际目标、结果、最多三项缺口与具体下一步；缺失交接包在本轮无需交接时不用额外催导出。
