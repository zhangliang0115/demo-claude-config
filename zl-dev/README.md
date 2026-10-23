# ZL Dev

描述需求，让 AI 完成理解、设计、开发和验证；页面帮助你快速知道做的是什么、现在需要处理什么。

## 安装
```text
/plugin marketplace add https://github.com/zhangliang0115/demo-claude-config
/plugin install zl-dev@zl-dev-marketplace
```

## 只保留两个命令
```text
/zl-dev:go 在订单列表增加客户筛选，翻页时保留筛选条件。
/zl-dev:status
```

继续反馈也使用 go：
```text
/zl-dev:go 继续，空结果需要给出清空筛选的入口。
```

无需记设计、审查、测试的命令。AI 按当前任务读取必要指引。需求不同于现有任务时建立新任务；不因存在唯一旧任务就把新需求混进去。多个任务需要定位时列标题供选择。

## 你打开页面应该看到什么

1. 任务名称、用户问题和目标行为。
2. 当前阶段，以及谁现在要做哪件具体的事。
3. 一个完整的操作例子和最多三项前后变化。

需要时使用“查阅已有材料”选择有内容的章节。没有内容的章节不会出现在菜单里。阶段专用模板默认只展示当前阶段，其余已记录阶段作为档案选择；不再铺开全部阶段按钮。

## 同一个功能跨多个项目
```text
/zl-dev:go 管理台需要支持订单取消。
候选项目：/workspace/admin-web、/workspace/order-api。
先查现状和调用关系，整体设计后再分配项目改动。实施可以由一个人或多人承担。
```

AI 按需进入 [跨项目流程](docs/cross-project.md)，共用整体方案和契约，再分别实施、汇总、联调。功能总览仍使用独立的固定模板。

## 存储与边界

版本 0.7.0，Python 3.9+ 标准库。任务默认存放于 `~/.claude/zl-dev/projects/<项目名>-<路径哈希>/tasks/`，跨项目功能放于归属工作区的 `features/`。原仓库保存业务代码，产出绑定原项目路径。旧任务不自动搬迁。

页面是离线快照；反馈草稿需明确回传，不能直接当作批准。模拟案例不代表代码运行成功。完整模型会话尚需真实项目试用，CLI 测试不能替代这种评测。旧版阶段命令已撤下，统一改用 go 描述操作；更新后按客户端提示重载。

## 示例与验证

[任务示例](examples/order-cancellation/report.html) · [生产事件](examples/production-incident/report.html) · [跨项目功能](examples/cross-project-cancel/feature.html)

```sh
python3 -m unittest discover -s zl-dev/tests -v
claude plugin validate --strict .
claude plugin validate --strict zl-dev
```

[插件说明](PLUGIN.md) · [技术数据格式](docs/schema-reference.md) · [入口与官方参考](docs/entry-workflow.md)
