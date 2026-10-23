# 内部动作：review

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：当前任务输入（由 go 路由提供）

按工作协议使用独立 reviewer（可用时）；否则明确同一代理自审。检查确认规则、代码差异、异常路径、权限、并发、兼容性和测试盲区。每项发现包含位置、成立条件、影响和复现方法；区分确认问题与怀疑。将发现写入风险或待决事项并更新 HTML，不仅输出口头总结。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。
