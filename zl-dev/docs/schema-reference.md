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
continue [任务目录或 slug] --project /项目路径：省略任务时仅在恰好一个任务的情况下恢复；0 或多个返回候选清单。不会执行开发命令。返回 next_action 与 step（understand/decide/implement/verify/accept），供 AI 继续；accept 表示待人工核验，不是已验收。

workflow_summary 是渲染时计算结果，不让 AI 填写完成度。指纹仅使用 semantic_contract 明确选择的行为字段；阶段 testing/review 的结果、handoffs、人员和展示摘要不参与。阶段 requirements/solution 的核心内容及 acceptance 预期仍参与。旧证据需重新验证。

时间展示统一为 `yyyy-MM-dd HH:mm:ss`，时区 Asia/Shanghai（UTC+8）。原始数据保留带时区的 ISO 时间，页面与复制反馈格式化显示，不改变证据记录本身。
