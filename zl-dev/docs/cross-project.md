# 跨项目功能：整体设计，分项目实施

## 核心顺序

识别候选项目 → 检查现有职责和调用关系 → 设计整个功能 → 确定项目边界与共同契约 → 拆开发任务及依赖 → 分项目实现 → 整体联调与人工核验。

一个功能一个 feature.json 和总览 feature.html，各项目各自一个 task.json/report.html。设计负责人和实施者可一人兼任，也可多人协作；项目数量不等于人员数量。换人或换 agent 要复述理解，同一个人不必人为交接给自己。

## 第一步：识别，不预分配

用户给出工作区或候选项目路径。仅在提供范围检查，不扫描个人目录或读取无关项目。脚本 inspect 识别清单文件及 Git 版本等事实，AI 另行读取项目约定、入口、接口、业务实现和现有测试，记录带源码位置的观察。不能因为名叫 admin 就认定所有管理业务都应在那里，也不能因为目录叫 api 就假设它掌握业务数据。

检查不可访问的项目时，标记未知并请求必要路径或访问方式；不可把猜测当已分析。远程只拿到方案、没拿到代码时，写清识别限制。

## 第二步：整体方案先于项目任务

feature.design 记录 goal（整个目标）、flow（完整用户和数据路径）、boundaries（按证据提出的职责边界）、decisions（取舍和待决问题）。必须从完整功能角度设计主路径、异常状态、权限、幂等、历史数据、兼容性和验收。

contracts 列出跨项目共同约定及版本。每条 {id, version, description, status: proposed/confirmed}。全局 contract_version 是整体方案基线，例如 v1；仅人明确确认关键规则后，才能记录对应确认。确认目标不是要求用户批准每项内部实现细节。

## 第三步：再分项目开发

allocations 中每条 {id, project_id, summary, depends_on: [], contract_version, status, owner}。owner 可同一个人也可不同人，未知留空。depends_on 引用其他 allocation.id，禁止环。先实现真实依赖；契约已明确时可以采用清楚标记的 mock 并行，但 mock 通过不代表联调通过。

projects 每条 {id, path, responsibility, task_path, contract_version, status, owner}。task_path 指向明确的子任务目录，path 为本机仓库路径。为其他机器交接时应重新绑定本机路径，不照搬别人的绝对路径。

子任务额外记录 feature: {id, path, contract_version}，保持子任务的需求与总方案关联。feature.py sync 只读取显式关联任务并汇总，不替任何项目修改代码，不自动创建团队或派发给他人。

## 第四步：变更与整体验收

影响共同规则的改动先更新整体方案版本，再列出受影响项目。每个项目按新基线实施、验证并更新 contract_version。报告展示版本不一致和快照过期，不能悄悄覆盖旧版本。不同 AI 工具读取同一总方案和子任务结构；不要只靠聊天上下文。

integration 条目 {id, scenario, environment, status, versions: {project_id: deployed_revision}, evidence}。记录整条用户路径、真实部署版本、环境、结果和原始证据。模拟/未执行要明确标记。脚本的汇总与新鲜度检查不等于发布批准，也不能自动证明线上或 E2E 通过。

## CLI 和持久化

```sh
python3 /插件路径/scripts/feature.py init /功能目录 --title "订单取消" --project admin=/工作区/admin --project api=/工作区/api
python3 /插件路径/scripts/feature.py inspect /功能目录
python3 /插件路径/scripts/feature.py sync /功能目录
python3 /插件路径/scripts/feature.py render /功能目录
python3 /插件路径/scripts/feature.py status /功能目录
```

总任务可放在共同工作区 `.zl-dev/features/order-cancel/` 或共享方案仓库。inspect 写观察，sync 写快照，render 生成 feature.html；这不是后台监听。未同步、不可访问和版本变化都应保留为缺口。不要仅传总目录给原来的 task CLI，它使用另一份 task.json 数据格式。

## 完整示例：一个人或多人都一样

在工作区启动 Claude，确保两个仓库可访问，然后发送：

```text
/zl-dev:feature 我想在管理台支持取消订单，具体流程还没想清楚。
候选项目：/workspace/admin-web、/workspace/order-api。
请先查两个项目的现状和调用关系，整体设计功能，再确定各项目改动。
先不要改业务代码。默认由我负责；后续需要时再分配实施者。
```

AI 应先查清：页面在哪里、API 由谁提供、订单/库存数据归谁、是否已有取消能力。可能发现后端已有取消 API，只需补权限和幂等，而不是重新设计一套；结论必须来自源码。

整体方案确认后：
```text
按总方案 v1 开始实施。先补后端幂等和状态校验，再接前端入口。
两个项目都由我负责。每完成一个切片就更新子任务和功能总览。
```

若多人实施，只替换分配：
```text
总方案不变，前端交给小王，后端交给我。
生成前端接手包，包含总方案版本、接口约定、边界和验收场景。
```

任何时候：
```text
/zl-dev:feature 继续 /功能目录，重新同步两个项目的进度，告诉我哪些接口可联调、哪些仍有阻塞。
```

演示总览包含模拟数据，不能拿示例状态充当真实项目的验证结果。
