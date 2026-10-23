---
description: 运行真实检查并建立规则到证据的关联
argument-hint: "[任务描述或任务目录]"
---

先读取 `${CLAUDE_PLUGIN_ROOT}/docs/workflow.md`，遵循其中的事实、证据、风险和反馈规则。

用户参数：$ARGUMENTS

从行为约定制定验证，不仅复述已有测试。读取真实项目工具链，运行相关检查，保留命令、结果及证据位置。先获取 fingerprint，执行检查后再获取 fingerprint；二者一致且检查结果真实时才能将该值写入对应 evidence.revision。若变更则重新验证。失败或未执行保留准确状态。避免将之后更改的业务约定追溯绑定旧测试。渲染报告检查证据状态。

工具入口：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py"`。以生成的 task.json、插件 schema 和示例为字段依据。默认目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，使用任务 slug 和 `--project <项目绝对路径>` 解析，不能在仓库中另建产出目录。完成阶段后执行 `render <任务目录>`，在回复中给出生成 report.html 的绝对路径。
