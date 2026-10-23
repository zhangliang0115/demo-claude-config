# ZL Dev — 团队 AI 协作与理解验收

[插件完整描述](PLUGIN.md) · [标准插件清单](.claude-plugin/plugin.json) · [仓库安装清单](../.claude-plugin/marketplace.json)

把模糊需求、方案、交接、实现、测试、人工核验和生产运维放进同一套固定交互式 HTML。版本 0.5.0，Python 3.9+，标准库，无 CDN、无账号或 Artifact 发布依赖。

## 安装

本仓库根目录提供标准 `.claude-plugin/marketplace.json`，插件本体在 `zl-dev/.claude-plugin/plugin.json`。仓库内容提交并推送到 GitHub 后，具有访问权限的人可在 Claude Code 执行：

```text
/plugin marketplace add https://github.com/zhangliang0115/demo-claude-config
/plugin install zl-dev@zl-dev-marketplace
```

也可使用新版的一步入口：
```text
/plugin install zl-dev --marketplace zhangliang0115/demo-claude-config
```

**本地新增文件尚未推送时，GitHub 安装不会获得这些内容。** 本地开发无需安装市场，在目标项目目录启动：
```sh
claude --plugin-dir /本仓库绝对路径/zl-dev
```

安装后按客户端提示重载；输入 `/zl-dev:` 检查命令。其他 agent 工具不能直接加载 Claude 命令，但能读取 `HANDOFF.md` 并调用同一 Python CLI。

## 最常用路线

```text
/zl-dev:start 我们希望减少客服处理取消订单的工作，但具体规则尚未确定
/zl-dev:design <任务目录>
/zl-dev:handoff <任务目录>
```
下一位同事：
```text
/zl-dev:intake <任务目录>
/zl-dev:build <任务目录>
/zl-dev:review <任务目录>
/zl-dev:verify <任务目录>
/zl-dev:handoff <任务目录>
```
生产问题用 `/zl-dev:incident`；日常检查或运维变更用 `/zl-dev:ops`。`spec`、`plan` 可控制单独阶段，`status` 可随时继续。低风险明确任务可自动连续推进，不要求每人手动执行全部命令。

## 固定页面

九个区域：一分钟概览、场景演示、业务变化、实现解释、需要你决定、验证证据、方案与职责、跨人交接、生产与运维。角色选择器帮助不同负责人切换阅读入口。场景切换、规则筛选、代码说明折叠、决策草稿导出均离线可用。

任务类型：新功能、业务调整、缺陷、重构、性能、数据迁移、技术升级、生产事件、日常运维。阶段共享结构，内容遵循专项协议；缺失项明确留空，不编造数据。模拟演示不代表业务已运行。

## 示例与运行

- `examples/index.html`：团队示例总览。
- `examples/order-cancellation/report.html`：需求、方案、交接与验收示例。
- `examples/production-incident/report.html`：生产故障处理示例。

```sh
python3 zl-dev/scripts/reviewable.py index zl-dev/examples
python3 -m unittest discover -s zl-dev/tests -v
claude plugin validate --strict .
claude plugin validate --strict zl-dev
```

## 团队职责和数据约定

阅读 [团队协议](docs/team-workflow.md)、[基础工作流](docs/workflow.md)、[数据格式和 CLI](docs/schema-reference.md)。默认任务保存在用户目录 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/<slug>/`，交接时将 JSON、HTML、HANDOFF.md 及必要证据一并移交。不要提交密钥或未脱敏生产日志。

## 当前边界

这是流程与离线报告插件，不是工作流服务器。没有自动跨人同步、线上审批服务、生产执行器或发布系统。页面反馈导出后需人明确回传，不自动成为批准。AI 仍可能写错或编造记录，指纹只能发现内容变化，不能证明证据真实。渲染时检测源码与约定新鲜度，打开旧 HTML 不会自动检测后续代码变化。第三方环境、Git 忽略文件不在指纹覆盖范围。

所有示例都是演示资料，不代表真实线上事件或实际订单实现。尚未做完整 Claude 模型会话端到端验收；CLI、格式与浏览器验证另行报告。GitHub 分发必须先推送文件；公开发布的许可证尚未指定，不替用户选择开源许可。

官方格式依据（2026-10-22 核对）：[插件格式](https://code.claude.com/docs/en/plugins-reference)、[创建市场](https://code.claude.com/docs/en/plugin-marketplaces)。

## 名称变更

0.2.1 起 marketplace 名称为 `zl-dev-marketplace`，插件及目录名为 `zl-dev`，命令前缀为 `/zl-dev:`。旧安装不会自动转换为新插件，请按上面的新名称安装，再按需要卸载旧插件。新任务默认保存在用户 `~/.claude/zl-dev/projects/` 下按项目区分；已有任务目录不会自动移动，可把原任务目录显式传给命令继续使用。

## 阶段工作台（0.3.0）
新增九个阶段专用展示，共用固定字段、布局及交互：需求对照、方案比较、交接对照、实施偏差、审查筛选、测试步骤回放、人工验收草稿、发布检查、运维时间线。进入示例后点击“阶段工作台”。AI 只填数据，未知字段和无效证据引用会被拒绝。详见 [模板协议](docs/stage-templates.md)。这不是在线审批或业务执行器；回放来自记录，验收交互仅生成草稿。

## 跨项目功能
`/zl-dev:feature` 先读取候选项目的实际实现并整体设计，再按职责拆项目子任务。支持一个人跨多个项目或多人分工，共用一个功能方案和固定总览。总览显示项目识别、整体设计、共同契约、项目任务依赖和整体联调；详见 [完整命令与示例](docs/cross-project.md)。

## 产出目录（0.5.0）

```text
~/.claude/zl-dev/projects/
├── orders-<路径哈希>/tasks/cancel-order/
│   ├── task.json
│   ├── report.html
│   └── HANDOFF.md
└── workspace-<路径哈希>/features/cancel-order/
    ├── feature.json
    └── feature.html
```

目录键由项目名与真实绝对路径的 SHA-256 前 12 位组成；同名不同路径不会混在一起。跨项目功能以明确工作区归档，各子项目任务仍独立归档。记录绑定的原项目路径，验证继续读取原仓库。显式旧路径兼容，不自动迁移历史任务。仓库自带 examples 是演示资源，不是用户任务产出。
