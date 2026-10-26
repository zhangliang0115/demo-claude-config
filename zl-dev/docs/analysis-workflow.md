# 业务逻辑与数据链路的只读分析

使用 `/zl-dev:go` 描述要理解的现状，用户无需记新命令。analysis 是独立事项类型和阶段，记录字段不要求实现、行为变更、项目测试、人工验收或发布。

## 适用与选择

- business_logic：从入口解释条件、规则、状态、副作用和异常分支。
- data_flow：从页面字段、接口、数据库字段、消息等追踪来源、传递、计算、过滤及写入/消费环节。
- 用户已要求开发或修改时，“先分析”仍可属于原开发流程；不能只按“分析”关键词强制换类型。
- 简短问题可以只读源码后文字答复，不创建长期任务或页面；复杂或持续追踪才保存 task。
- 跨项目只读资料以额外 project_paths 声明，不进入 feature 的实施分工、契约审批和 preflight。路径声明是记录范围，不是访问授权。

```text
明确问题和只读范围
→ 找真实入口及相关实现
→ 追踪调用/条件/数据转换
→ 以源码交叉核对并绑定来源
→ 在允许范围继续查断点，或只问确实缺失的材料
→ 保存可核对结论与范围
→ 按需文字交付或生成分析报告
```

## 任务创建与来源工具

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reviewable.py" init order-flow --project "/明确项目" --title "实付金额的数据链路" --kind analysis --no-render
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/analysis.py" source --id S1 --project "/明确项目" --path "src/quote.py" --line-start 10 --line-end 35
```

source 只读显式文件，不创建任务或 HTML，不执行被分析项目。返回可直接加入 sources 的 `{id,project_path,path,line_start,line_end,sha256}`。省略行范围时核对整个非空 UTF-8 文件，只返回元数据，不把全文再次回传给模型。默认单文件上限16MiB，二进制、编码不支持或过大应保留断点，不能绕过权限或冒充原文件。

path 为项目内相对路径，不能含 `..`；解析后符号链接也不能越出声明项目。跨项目来源应使用实际项目根和相对路径。记录并重新核对文件字节，Git 忽略文件及非 Git 项目也可用；整体报告在无法核对 Git 状态时仍可能是 unknown，不能说运行环境已验证。

## analysis 数据字段

数组无内容可省略或为空，不为填满格式编造材料。

| 字段 | 含义 |
| --- | --- |
| mode | business_logic / data_flow |
| question / conclusion | 原问题与静态结论，未形成时为空 |
| project_paths | 明确可读取的额外项目绝对路径；主项目由 task.project_path 提供 |
| sources | 上述来源工具输出对象，id 唯一；记录时 sha 不自动变更 |
| steps | `{id,title,description,source_ids}`，有序的已追到流程 |
| rules | `{id,condition,outcome,source_ids}`，业务条件与结果 |
| mappings | `{id,from,to,transformation,source_ids}`，字段传递和转换 |
| findings | `{id,classification,statement,source_ids}`，分类 fact/inference/unknown |
| gaps | `{id,description,next_action,disposition?}`，待查/缺材料/范围外边界 |

步骤、规则、映射和 fact 必须有存在的来源引用；推断和未知可没有引用，但要明确性质，不能写入已确认流程冒充事实。source 引用只能说明所读版本与位置，不证明模型推理或业务规则正确。

gap.disposition 可为 investigate / needs_input / out_of_scope，缺省保守视为 investigate。先继续本地可查部分；只有确实缺材料才请求具体输入；范围外项不隐藏。没有断点记录也不代表不存在尚未发现的分支。

analysis_assessment 由脚本派生，包含各来源 current/stale/unavailable/invalid、记录 SHA 与当前可观察 SHA、实际行数、材料缺失与推断/未知/断点数量。保存结果中的伪造派生值会被重新计算；外部来源变化会改变评估，使旧页面和旧缓存需要重新核对。

## 结束与继续

只读分析的完成是“在已说明范围内形成可追溯解释”，不是测试绿灯或批准。问题、结论、来源、有序流程尚缺时继续分析；来源变化先只读重查。可追查断点不允许直接结束；需要材料时只问缺失部分，明确范围外断点可形成局部可读材料。无需人为补开发记录、测试或签字。

source 元数据、结论、规则、映射等观察不应让保存记录本身使来源版本失效；实际问题/模式/范围变更则需重新核对。原有九种事项的指纹形状保留。新增模板目录可能使旧报告评估过期，但不代表旧业务代码证据已失效；不为刷新模板自动重跑项目测试。

## 输出与边界

业务逻辑报告优先展示入口/流程和条件规则；数据链路报告优先展示流转与字段映射。两者都直接呈现问题、结论、事实/推断/未知和断点，源码详细位置与哈希按需展开。页面不访问源码或业务接口，不提供执行、批准、发布控件；补充反馈仍可复制回会话。

生成仅通过既有 render 及发布保护，不另造网页。短答复、进度和调查中间步骤继续不强制 HTML。用户要求运行验证或业务修复时，应明确新的范围和任务关系；分析任务不能被 feature 当作已经实现或联调就绪。
