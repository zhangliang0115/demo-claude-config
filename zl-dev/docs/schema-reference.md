# task.json v1 数据约定

Python 3.9+，UTF-8 JSON 对象。以 scripts/reviewable.py 的 validate 为基础结构校验，以下语义仍需人工与 AI 核对。

必填：version=1；id/title 非空字符串；kind 为 feature/change/bugfix/refactor/performance/migration/upgrade/incident/operations。
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
init 不覆盖既有 task.json。render 固定生成 report.html；index 刷新子任务及 index.html；handoff 固定生成 HANDOFF.md。

## 证据新鲜度
fingerprint 绑定 Git 工作区内容与行为约定（含场景、验收、假设、方案、交接及操作计划）。没有 Git 时 UNKNOWN，不能声称当前有效。验证前后计算指纹，完全相同才绑定 evidence.revision；指纹变化必须重新验证，不能只刷新指纹。指纹匹配不证明命令实际运行。
报告是生成时快照，不会自动监控文件变化。任何修改后需重新 render/status。忽略文件与外部系统不在源码指纹保证范围，应额外记录环境及外部版本。task 目录中的日志不参与源码指纹，需人工核对真实性。

## 反馈
HTML 导出 decision-draft.json，不直接改 task.json，不代表审批或接收。人把草稿交回会话后核对任务与版本，再记录明确授权。跨工具接手包不包含凭据，不自动执行任何命令。
