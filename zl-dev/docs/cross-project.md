# 跨项目功能：整体设计，分项目实施

## 核心顺序

识别候选项目 → 检查现有职责和调用关系 → 设计整个功能 → 确定项目边界与共同契约 → 拆开发任务及依赖 → 分项目实现 → 整体联调与人工核验。

一个功能一个 feature.json，各项目各自一个 task.json；feature.html 与 report.html 均按 entry-workflow.md 的产出策略生成，不因子步骤结束而强制更新。页面根据 phase 默认打开当前阶段（discovery/design/contracts/implementation/integration，也识别 solution/testing/acceptance 等常用别名），页首读取 design.goal。导航用于查看同一功能的已有材料，不代表每次必须重走所有阶段。各阶段可填写判断和备注并复制给 AI；复制内容含功能编号、契约版本、报告生成时间和阶段，只是草稿，不自动批准方案或写回记录。设计负责人和实施者可一人兼任，也可多人协作；项目数量不等于人员数量。换人或换 agent 要复述理解，同一个人不必人为交接给自己。

## 第一步：识别，不预分配

用户给出工作区或候选项目路径。仅在提供范围检查，不扫描个人目录或读取无关项目。脚本 inspect 识别清单文件及 Git 版本等事实，AI 另行读取项目约定、入口、接口、业务实现和现有测试，记录带源码位置的观察。不能因为名叫 admin 就认定所有管理业务都应在那里，也不能因为目录叫 api 就假设它掌握业务数据。

检查不可访问的项目时，标记未知并请求必要路径或访问方式；不可把猜测当已分析。远程只拿到方案、没拿到代码时，写清识别限制。

## 第二步：整体方案先于项目任务

feature.design 记录 goal（整个目标）、flow（完整用户和数据路径）、boundaries（按证据提出的职责边界）、decisions（取舍和待决问题）。必须从完整功能角度设计主路径、异常状态、权限、幂等、历史数据、兼容性和验收。

contracts 列出跨项目共同约定及版本。每条 {id, version, description, status: proposed/confirmed}。全局 contract_version 是整体方案基线，例如 v1；仅人明确确认关键规则后，才能记录对应确认。确认目标不是要求用户批准每项内部实现细节。

## 第三步：再分项目开发

allocations 中每条 {id, project_id, summary, depends_on: [], contract_version, status, owner}。owner 可同一个人也可不同人，未知留空。depends_on 引用其他 allocation.id，禁止环。业务代码实施前运行 `feature.py preflight /功能目录`。它只读检查当前整体方案基线、所有共享契约确认、项目/子任务版本和切片依赖版本；有缺口返回退出码 2，先解决问题再开始实施。它不是 Edit hook，不能技术上阻止绕过指引的任意编辑，也不会因为通过就证明依赖已实现。先实现真实依赖；契约已明确时可以采用清楚标记的 mock 并行，但 mock 通过不代表联调通过。

projects 每条 {id, path, responsibility, task_path, contract_version, status, owner}。task_path 指向明确的子任务绝对目录（默认在用户 .claude 下），path 为本机仓库路径。外置子任务的 project_path 必须与此项目真实路径一致；不能借用其他项目的证据。为其他机器交接时应重新绑定本机路径，不照搬别人的绝对路径。

子任务额外记录 feature: {id, path, contract_version}，保持子任务的需求与总方案关联。feature.py sync 只读取显式关联任务并汇总，不替任何项目修改代码，不自动创建团队或派发给他人。`projects[].snapshot` 是派生快照，只能由 sync 更新；AI 不得手改其中计数、问题或新鲜度来使状态变绿。历史失败和过期证据仍计数、保留追溯；当前版本有全部行为覆盖且无当前未通过记录时，历史失败不再永久阻塞。当前失败/阻塞/未执行不能被另一条 passed 简单抵消，未知或未覆盖仍阻塞。

## 第四步：变更与整体验收

影响共同规则的改动先更新整体方案版本，再列出受影响项目。每个项目按新基线实施、验证并更新 contract_version。报告展示版本不一致和快照过期，不能悄悄覆盖旧版本。不同 AI 工具读取同一总方案和子任务结构；不要只靠聊天上下文。

integration 条目 {id, scenario, environment, status, versions: {project_id: deployed_revision}, evidence}。记录整条用户路径、真实部署版本、环境、结果和原始证据。模拟/未执行要明确标记。脚本的汇总与新鲜度检查不等于发布批准，也不能自动证明线上或 E2E 通过。

## CLI 和持久化

```sh
python3 /插件路径/scripts/feature.py init order-cancel --workspace /工作区 --title "订单取消" --project admin=/工作区/admin --project api=/工作区/api
python3 /插件路径/scripts/feature.py locate /功能目录
python3 /插件路径/scripts/feature.py update /功能目录 --workspace /工作区 --from-file /临时目录/feature-next.json --expect-revision <locate返回的feature_revision>
python3 /插件路径/scripts/feature.py inspect /功能目录
python3 /插件路径/scripts/feature.py preflight /功能目录
python3 /插件路径/scripts/feature.py sync /功能目录
python3 /插件路径/scripts/feature.py render /功能目录
python3 /插件路径/scripts/feature.py status /功能目录
```

更新方案时，先 `locate` 获取精确 feature.json 字节的 `feature_revision`，读取当前 feature.json，以完整对象在可写临时目录准备 `feature-next.json`，再用上述 `update` 导入。源文件权限失败会如实报错；不要通过直接 Write 用户目录绕过环境的写入限制。`update` 校验 JSON、固定功能 id/工作区/项目 id 与路径集合，并拒绝改写派生快照；本命令暂不支持增删或重新绑定项目。`--workspace` 必须匹配初始化记录的工作区。版本冲突时重新 locate、重读合并，不能强行覆盖。更新只保存数据，不生成页面、不确认业务规则；随后按需要 preflight、sync、render。

子任务快照绑定规范化的 task_path 和 task_id；即使代码与行为指纹相同，切换任务后也必须重新 sync。旧快照缺少绑定时按过期待核对处理。

`update`、`inspect` 和 `sync` 共用协作锁并原子替换文件，inspect/sync 还检查读取以来的版本变化。外部编辑器不遵守该锁，不要同时直接编辑 feature.json；这些保护也不提供超越系统权限的写入能力。当前写锁依赖 fcntl，Windows 等缺少它的平台仍可运行 locate/status/preflight 等只读命令，但写入命令会明确报不支持，不进行写入。

总任务默认保存在 `~/.claude/zl-dev/projects/<工作区名>-<路径哈希>/features/<slug>/`。用 `--workspace <共同工作区绝对路径>` 固定归属；各项目子任务仍按各自项目区分。inspect 写观察，sync 写快照，需要结构化交付时 render 生成 feature.html；这不是后台监听，也不应逐子动作 sync/render。未同步、不可访问和版本变化都应保留为缺口。不要仅传总目录给原来的 task CLI，它使用另一份 task.json 数据格式。

## 完整示例：一个人或多人都一样

在工作区启动 Claude，确保两个仓库可访问，然后发送：

```text
/zl-dev:go 跨项目 我想在管理台支持取消订单，具体流程还没想清楚。
候选项目：/workspace/admin-web、/workspace/order-api。
请先查两个项目的现状和调用关系，整体设计功能，再确定各项目改动。
先不要改业务代码。默认由我负责；后续需要时再分配实施者。
```

AI 应先查清：页面在哪里、API 由谁提供、订单/库存数据归谁、是否已有取消能力。可能发现后端已有取消 API，只需补权限和幂等，而不是重新设计一套；结论必须来自源码。

整体方案确认后：
```text
按总方案 v1 开始实施。先补后端幂等和状态校验，再接前端入口。
两个项目都由我负责。每完成一个切片及时保存子任务事实；有整体汇总或阅读需求时再同步并生成总览。
```

若多人实施，只替换分配：
```text
总方案不变，前端交给小王，后端交给我。
生成前端接手包，包含总方案版本、接口约定、边界和验收场景。
```

任何时候：
```text
/zl-dev:go 跨项目 继续 /功能目录，重新同步两个项目的进度，告诉我哪些接口可联调、哪些仍有阻塞。
```

演示总览包含模拟数据，不能拿示例状态充当真实项目的验证结果。

## 功能报告版本

feature 的 render、locate/status 输出 feature_revision（精确记录）及 assessment_revision（实时派生评估），report_state 只读区分 current/stale/unknown/missing；旧报告路径仍保留供追溯。复制反馈带两种版本及契约版本，只比较 contract_version 不足以确认材料最新。子任务记录、代码或日志变化可使整体报告过期；status 不自动 sync/render。新字段是派生信息，不手填到 feature.json，也不据本地哈希推断身份认证。

## 整体功能的会话焦点

按[会话关联](session-context.md)，整体功能用 target-kind=feature，作用范围是已核对的 feature.json.workspace_path；子任务用 target-kind=task，作用范围是自己的 project_path。主会话明确选择整体功能后保存关联，再由 target.kind/path 恢复。显式查看某个子任务不自动替换整体焦点；只有用户明确切换才由 go 绑定新目标。status 只读，不 bind/clear。换目录或缺失关联时不扫描其他项目猜测总功能，必要时使用明确功能路径。
