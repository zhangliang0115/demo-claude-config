# Claude 模型评测与成本归因（M2/M3/M4）

## 范围

- 模型：`claude-sonnet-5-5`，Claude Code 2.1.310，`--plugin-dir` 加载工作区插件，`bypassPermissions`，每次全新会话，max-turns 15，timeout 180 秒，不重试。
- 场景（`scripts/evaluate_models.py`，合成夹具，不运行业务代码）：progress 看进度、summary 追加记录并保存、report 要当前报告、handoff 导出交接包、analysis 只读分析源码。每场景 3 次。
- 宿主环境未隔离：用户已有 8 个插件、45 个工具、26 个技能、2 个 MCP 照常加载。费用为 CLI 报告的 `total_cost_usd`，不是账单。
- Opus 未测：Sonnet 已全部通过，按成本优先暂缓；结论不外推到 Opus 或其他模型。

## 结果

| 场景 | 0.24.0 轮数 | 0.24.0 平均输入 tokens | 0.25.0 轮数 | 0.25.0 平均输入 tokens | 检查通过 |
| --- | --- | --- | --- | --- | --- |
| progress | 3,3,3 | 116.8K | 3,3,3 | 116.9K | 3/3 → 3/3 |
| summary | 5,7,6 | 282.1K | 6,6,6 | 271.6K | 3/3 → 3/3 |
| report | 3,3,3 | 116.5K | 3,3,3 | 116.6K | 3/3 → 3/3 |
| handoff | 11,5,8 | 382.0K | 6,4,5 | 220.0K | 3/3 → 3/3 |
| analysis | 4,4,4 | 126.6K | 4,4,4 | 124.6K | 3/3 → 3/3 |
| 合计费用 | | $6.23 | | $5.17 | 15/15 → 15/15 |

检查项：源码与 Git 状态不变；summary 只改 summary 字段；progress/handoff 不改报告；handoff 实际导出 HANDOFF.md；analysis 不建任务。无超时、无 max_turns。

## 0.25.0 改了什么

- entry-workflow.md 21.9KB → 15.0KB：按两轮独立审查补回全部有约束力的规则，只删重复和冗长表述。
- CLI 对显式空目录参数报错。0.24.0 handoff-r1 里模型用 shell 变量拼路径，变量未展开时 `locate ""` 静默返回空候选列表，模型随后读源码排查，多花 5 轮。
- 历史设计快照（go-design）、实测记录（evaluations、live-evaluation、practical-review）移到仓库 `docs/zl-dev/`，不再随插件分发。

两批各 3 次，样本小；handoff 的下降同时来自空参数报错和指引缩短，没有分别归因。

## 成本归因（M4 / ZL-11）

- 3 轮场景的输入约 117K tokens，其中 zl-dev 指引与工具返回合计约 9KB 字节。主体是宿主每轮重发的系统上下文（工具、插件、技能清单），不归 zl-dev，也不能靠插件优化。
- 多出来的成本按轮数线性增长：每多一轮约多 38–48K 输入 tokens。因此减少多余轮次（错误后的排查、重复核对）收益最大。
- summary 场景的 JSON 往返：读取 task.json 和写临时 JSON 只占每轮几 KB 字节，与每轮的宿主上下文相比很小。

结论：ZL-12（内部增量更新）**没有数据支持，不实施**。后续优化方向是减少轮数，而不是缩小 JSON。

## 0.26.0 抽查

同一评测工具对 0.26.0 跑五场景各 1 次（Sonnet 5.5）：5/5 成功，检查全部通过，轮数 progress 3、summary 6、report 3、handoff 6、analysis 4，合计 $1.73，与 0.25.0 一致，未见回归。单次样本，只用于回归检查。

## M2 补齐：Opus 5.5 与多会话、执行上下文场景（2026-10-27，0.26.0）

新增两个场景：

- multisession：同项目两个任务，本会话关联任务 A，另一会话关联任务 B；只说“继续”，不给路径。检查是否接回 A、不提 B、不改记录与报告。
- execcontext：另一会话已在同一 checkout 登记写活动；请求开始实现。检查是否报告冲突、不改源码、不改任务。活动在每次运行前由控制器登记、运行后由控制器结束，最终活动表为空。

| 模型 | 场景 | 通过 | 轮数 | 费用 |
| --- | --- | --- | --- | --- |
| Sonnet 5.5 | multisession | 3/3 | 4,4,4 | $0.98 |
| Sonnet 5.5 | execcontext | 3/3 | 5,8,5 | $1.51 |
| Opus 5.5 | progress | 3/3 | 3,3,3 | $1.42 |
| Opus 5.5 | summary | 3/3 | 6,6,6 | $3.31 |
| Opus 5.5 | report | 3/3 | 3,3,3 | $1.41 |
| Opus 5.5 | handoff | 3/3 | 5,7,7 | $3.49 |
| Opus 5.5 | analysis | 3/3 | 3,3,3 | $1.44 |
| Opus 5.5 | multisession | 3/3 | 5,4,4 | $2.14 |
| Opus 5.5 | execcontext | 3/3 | 5,6,5 | $2.98 |

27/27 通过，无超时、无 max_turns。抽查 execcontext 轨迹：模型读取 execution-context 后识别出他人写活动，未登记、未清理他人记录、未改源码，并给出等待/独立 worktree/补授权三种选择。

Opus 轮数与 Sonnet 相近，单次费用约为 Sonnet 的 2 倍。multisession 与 execcontext 的检查依赖最终答复文本中的关键词（任务标题、“冲突/活动”），属于启发式判定；已人工抽查一份 execcontext 轨迹确认非假阳性。
