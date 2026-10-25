# 内部动作：build

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：当前任务输入（由 go 路由提供）

读取确认的规则和当前切片，实施范围内代码变更，遵守项目风格。不把关键业务未知当默认值。同步更新真实实现步骤、改动位置和实现偏差，旧证据过期后重新验证。实际执行相关测试并保存结果，需要结构化交付时才渲染 HTML；遇到缺少环境就记录未验证，不伪造通过。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。重要事实按入口安全更新流程及时保存；只有符合 entry-workflow.md 按需产出策略时才执行 `render <任务目录>` 并返回真实链接。阶段结束或内部动作结束不强制生成 HTML，不批量 index 其他任务。
