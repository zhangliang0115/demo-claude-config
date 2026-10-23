---
description: 先整体设计跨项目功能，再分配各项目开发与整体联调
argument-hint: "[功能需求、候选项目路径或已有功能目录]"
---

读取 `${CLAUDE_PLUGIN_ROOT}/docs/cross-project.md` 和 `docs/workflow.md`。用户输入：$ARGUMENTS。

先确认可访问的候选项目范围，只读检查各项目约定、入口、调用关系和现有能力，再做整个功能的设计。不要预先按“前端/后端”目录名猜职责，也不要先分发模糊需求让各项目独立设计。

总方案包括目标/非目标、完整用户路径、跨系统状态和数据流、接口契约、异常一致性、兼容性、整体验收。基于真实源码观察提出边界与分工，未知写假设，关键业务问题由人决定。同一负责人可实现所有项目，也可分配多人；人员与项目是独立维度。

工具：`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/feature.py" init <功能slug> --workspace <共同工作区绝对路径> --title <名称> --project <id>=<绝对路径>`，可重复 --project。然后 inspect，阅读被识别项目的真实源码（脚本仅识别项目线索，不负责理解架构）。更新 feature.json 的整体 design、contracts、allocations；对照 schema 协议。模板固定，不能自行设计 HTML。

在整体方案明确后，才为各项目建立独立 task.json，把整体方案位置与 contract_version 写入各子任务。每个子任务沿用现有阶段模板，但引用同一总方案。实现顺序按依赖，独立切片可并行；仅在用户和环境授权允许时启动代理。换人/换 agent 时复述上下文；同人同会话不强制交接。

开发中若发现跨项目约定变更，回到总方案修改版本，列出受影响项目并重新验证，不允许单项目静默修改共同契约。只实现已明确授权的切片，关键未知不猜测。

`sync <功能目录>` 汇总显式 task_path；`render <功能目录>` 生成固定 feature.html；`status <功能目录>` 显示快照新鲜度和缺口。总功能完成必须有指定环境、所有项目实际版本、真实跨项目 E2E 和人工核验；各子项目测试通过不能直接宣布整体通过。结束返回 feature.html 及各项目下一步。

默认产出必须使用用户 `~/.claude/zl-dev/projects/<工作区名>-<路径哈希>/features/<slug>/`。后续使用返回的绝对功能目录，或同一个 slug + --workspace。子任务由 reviewable.py init <slug> --project <项目绝对路径> 创建；projects[].task_path 记录其返回的绝对目录，task.json.project_path 必须与关联项目路径一致。
