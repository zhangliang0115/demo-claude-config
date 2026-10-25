# 内部动作：spec

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：当前任务输入（由 go 路由提供）

读取相关实现和测试，将当前行为与目标行为分开。为规则和场景建立稳定 ID，提供正常、异常、边界例子，记录依据。识别历史数据、权限、重复请求和并发影响。只将用户已确认的业务决定标为确认；其余保留待决。保存规则与场景；确需结构化阅读时按入口策略生成 HTML，否则文字解释即可。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。重要事实按入口安全更新流程及时保存；只有符合 entry-workflow.md 按需产出策略时才执行 `render <任务目录>` 并返回真实链接。阶段结束或内部动作结束不强制生成 HTML，不批量 index 其他任务。
