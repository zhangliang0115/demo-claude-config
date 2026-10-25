# 内部动作：design

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

读取 `${CLAUDE_PLUGIN_ROOT}/docs/entry-workflow.md`、`docs/team-workflow.md` 和 `docs/schema-reference.md`（后两者也相对插件根目录）。

用户参数：当前任务输入（由 go 路由提供）

读取原始需求与源码，生成事实/假设清单、方案选项、取舍和具体使用场景。补充 roles、assumptions、design。允许推荐合理方案，但关键业务假设必须由人确认。先保存方案与依据；有复杂比较或实际审阅需要时按固定模板生成 HTML，简单取舍可文字说明，绝不把模拟当已实现。

使用 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"` 管理任务，新建/恢复按入口使用 `--no-render`；渲染是按需独立动作。默认 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，按入口的 locate → CAS update 安全保存事实。仅确需结构化交付时 render 并返回真实链接，不逐动作 render 或批量 index；否则直接文字说明结果。
