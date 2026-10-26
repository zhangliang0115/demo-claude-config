# 真实项目试用 #1：magpie-advisor 只读分析（M6）

## 性质

- **真实代码，非合成夹具**：仓库内 `magpie-advisor/advisor-tool`（作者自己的 magpie 插件，约 15 个源文件）。
- **不是第三方用户反馈**：试用由维护插件的 AI 发起，使用者与开发者是同一方。真实用户反馈仍需按 [trial-guide](../trial-guide.md) 收集。
- 隔离方式：在 `git worktree --detach` 的独立副本中运行，结束后删除；主工作区未受影响。

## 输入

```text
/zl-dev:go 只读分析这个项目：advisor 工具调用时，模型列表从哪里来、怎样被页面读到、resolve.js 如何选出实际调用的模型。不要修改任何文件。需要时可以生成分析报告。
```

Claude Code 2.1.310，`claude-sonnet-5-5`，zl-dev 0.26.0（`--plugin-dir`），max-turns 30。

## 结果

| 项 | 观察 |
| --- | --- |
| 结果 | success，7 轮，$0.64（CLI 报告值） |
| 读取的指引 | entry-workflow.md、internal-actions/analyze.md（与分支表一致，未加载其他） |
| 文件改动 | worktree `git status` 前后均为空 |
| 任务与报告 | 未建任务、未生成 HTML；按"需要时"判断文字已足够 |
| 越权 | 未调用 advisor 工具，理由是调用会改写插件目录的 `page/models.js`/`state.js`，与"不修改文件"冲突 |

回答覆盖三个问题，均带 `文件:行` 依据：模型列表来自端点 `/v1/models`（60 秒缓存、3 秒超时、失败回退旧缓存）；页面在沙箱内通过生成的 `page/models.js`/`state.js` 静态脚本读取；`modelChain` 按 mapped → matched/declared → fallback → session 去重排序，`consult` 外层端点、内层模型逐个尝试。

另外列出 5 个可疑点，并明确标注为"推断，未在运行中验证"，例如：`declared` 可能一直为空，因为现有 `state.js` 里记录的是 `why:"session"`；多端点时，页面标注的网关地址和列表来源可能不一致。

## 对插件的结论

- 只读分析分支在真实代码上按设计工作：读取的指引最少、不建任务、不渲染报告、事实与推断分开。
- 没有发现插件缺陷。上面 5 个可疑点属于 magpie-advisor 本身，留给作者判断。
- 局限：样本只有一次，任务只有一种（只读分析），使用者就是开发者本人。不能据此说开发、验收或交接流程在真实项目里也可靠。
