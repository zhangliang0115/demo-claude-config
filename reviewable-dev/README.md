# Reviewable Dev — 团队 AI 协作与理解验收

[插件完整描述](PLUGIN.md) · [标准插件清单](.claude-plugin/plugin.json) · [仓库安装清单](../.claude-plugin/marketplace.json)

把模糊需求、方案、交接、实现、测试、人工核验和生产运维放进同一套固定交互式 HTML。版本 0.2.0，Python 3.9+，标准库，无 CDN、无账号或 Artifact 发布依赖。

## 安装

本仓库根目录提供标准 `.claude-plugin/marketplace.json`，插件本体在 `reviewable-dev/.claude-plugin/plugin.json`。仓库内容提交并推送到 GitHub 后，具有访问权限的人可在 Claude Code 执行：

```text
/plugin marketplace add https://github.com/zhangliang0115/demo-claude-config
/plugin install reviewable-dev@reviewable-dev-marketplace
```

也可使用新版的一步入口：
```text
/plugin install reviewable-dev --marketplace zhangliang0115/demo-claude-config
```

**本地新增文件尚未推送时，GitHub 安装不会获得这些内容。** 本地开发无需安装市场，在目标项目目录启动：
```sh
claude --plugin-dir /本仓库绝对路径/reviewable-dev
```

安装后按客户端提示重载；输入 `/reviewable-dev:` 检查命令。其他 agent 工具不能直接加载 Claude 命令，但能读取 `HANDOFF.md` 并调用同一 Python CLI。

## 最常用路线

```text
/reviewable-dev:start 我们希望减少客服处理取消订单的工作，但具体规则尚未确定
/reviewable-dev:design <任务目录>
/reviewable-dev:handoff <任务目录>
```
下一位同事：
```text
/reviewable-dev:intake <任务目录>
/reviewable-dev:build <任务目录>
/reviewable-dev:review <任务目录>
/reviewable-dev:verify <任务目录>
/reviewable-dev:handoff <任务目录>
```
生产问题用 `/reviewable-dev:incident`；日常检查或运维变更用 `/reviewable-dev:ops`。`spec`、`plan` 可控制单独阶段，`status` 可随时继续。低风险明确任务可自动连续推进，不要求每人手动执行全部命令。

## 固定页面

九个区域：一分钟概览、场景演示、业务变化、实现解释、需要你决定、验证证据、方案与职责、跨人交接、生产与运维。角色选择器帮助不同负责人切换阅读入口。场景切换、规则筛选、代码说明折叠、决策草稿导出均离线可用。

任务类型：新功能、业务调整、缺陷、重构、性能、数据迁移、技术升级、生产事件、日常运维。阶段共享结构，内容遵循专项协议；缺失项明确留空，不编造数据。模拟演示不代表业务已运行。

## 示例与运行

- `examples/index.html`：团队示例总览。
- `examples/order-cancellation/report.html`：需求、方案、交接与验收示例。
- `examples/production-incident/report.html`：生产故障处理示例。

```sh
python3 reviewable-dev/scripts/reviewable.py index reviewable-dev/examples
python3 -m unittest discover -s reviewable-dev/tests -v
claude plugin validate --strict .
claude plugin validate --strict reviewable-dev
```

## 团队职责和数据约定

阅读 [团队协议](docs/team-workflow.md)、[基础工作流](docs/workflow.md)、[数据格式和 CLI](docs/schema-reference.md)。默认任务保存在业务仓库 `.reviewable-dev/tasks/<slug>/`，交接时将 JSON、HTML、HANDOFF.md 及必要证据一并移交。不要提交密钥或未脱敏生产日志。

## 当前边界

这是流程与离线报告插件，不是工作流服务器。没有自动跨人同步、线上审批服务、生产执行器或发布系统。页面反馈导出后需人明确回传，不自动成为批准。AI 仍可能写错或编造记录，指纹只能发现内容变化，不能证明证据真实。渲染时检测源码与约定新鲜度，打开旧 HTML 不会自动检测后续代码变化。第三方环境、Git 忽略文件不在指纹覆盖范围。

所有示例都是演示资料，不代表真实线上事件或实际订单实现。尚未做完整 Claude 模型会话端到端验收；CLI、格式与浏览器验证另行报告。GitHub 分发必须先推送文件；公开发布的许可证尚未指定，不替用户选择开源许可。

官方格式依据（2026-10-22 核对）：[插件格式](https://code.claude.com/docs/en/plugins-reference)、[创建市场](https://code.claude.com/docs/en/plugin-marketplaces)。
