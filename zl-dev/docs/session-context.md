# 会话焦点与长期任务

任务事实保存在原 task.json 或 feature.json，可跨会话延续。会话关联单独记录某个工具会话在某个项目/工作区当前引用的目标；它不复制任务，不表示权限、独占锁或代码工作区隔离。用户仍只使用 go/status，无需维护会话 ID。

关联索引保存在 `~/.claude/zl-dev/contexts/<host>/<session-SHA256>/<项目路径标识>.json`，长期任务仍在原 `projects/.../tasks/` 或 `features/`。索引保存当前目标和最多十次先前目标的简短历史，不保存聊天全文，也不把任务目录改成会话私有。

## 标识与作用范围

- Claude Code 技能正文使用 `${CLAUDE_SESSION_ID}` 获得宿主展开的当前会话标识，host 为 `claude-code`。这不是假设同名环境变量已导出到 Bash。[官方替换说明](https://code.claude.com/docs/en/skills#available-string-substitutions)
- ID 为空、unknown 或仍是占位符时，不构造伪 ID，不从 PID、目录或最近任务猜测。只使用已明确的任务引用；真正不明确时简短询问。
- 关联按 host、session 和规范化项目/工作区路径隔离。两个会话可分别引用不同任务，也可共同引用同一任务；同一会话可明确切换焦点。
- task 关联的作用范围必须等于 task.json.project_path；feature 关联必须等于 feature.json.workspace_path。显式目标先核对，不因名称相同就接受另一个项目。
- 跨项目总功能以其 workspace 为作用范围；查询某个子任务可直接使用明确路径，不自动把整体焦点切为子任务。换到另一个项目目录不会暗中复用别处的关联。
- 子代理可能共享父会话标识。子代理只处理显式分配目标，不 bind/clear 父会话焦点；主会话依据用户意图控制切换。

## go 的选择顺序

```text
普通问答，无需长期工作 → 文字回应，不写关联
明确新事项 → 不先沿旧焦点续作 → 创建真实任务 → 核对后关联
明确目标/接手/切换 → 核对目标元数据 → 读取当前关联版本 → CAS bind
空输入或继续 → 只读 resolve
  bound → 使用 target.kind/path 调用任务或功能工具
  unbound → 说明缺少已确认目标，列候选供指定
  invalid_index / invalid_target → 说明失效，不猜测替代目标
```

明确目标优先于旧关联，但绑定成功不意味着已经完成新事项的调查或授权判断。相同焦点有效时无需每轮重复 bind。创建/切换失败时说明未完成，不能把仍存在的旧关联称为新目标。

不从唯一或最近历史任务推出新会话意图；候选标题只用于帮助选择。不要为了恢复焦点另建一份需求，也不要移动或合并旧任务。

## 仅关联/切换的最短结束路径

当本轮只要求关联或切换、没有请求推进业务时：

```text
核对明确的目标类型/路径/作用范围
→ resolve 一次
→ 若当前已是该有效目标：直接确认
→ 否则 CAS bind 一次
→ 返回 state=bound、目标符合本次选择且给出新 context_revision：文字结束
```

bind 会校验目标事实记录；输入信息完整时，不需要另读整个任务或调用 locate 来重复核对。若缺少必要元数据，只补查目标记录，不扫描插件目录找协议。成功返回已提供状态和目标，无异常时不再 resolve、不读取 session_context.py 重算，也不调用 continue/render/index 或业务验证。

只有实际请求继续开发、分析或验证时才进入对应工作流程。相同有效焦点不重复写入；真实冲突/权限/身份错误不得隐藏，必要时按返回原因调查。这一短路径不要求普通问答或每轮交流都调用关联工具。

## 内部 CLI

关联工具只管理恢复索引。它不渲染 HTML，不执行开发、测试或生产操作。所有参数为独立 argv，不能将用户文本拼成 shell 程序。

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" resolve \
  --host claude-code --session "<技能中已展开的ID>" --project "<作用范围绝对路径>"

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" bind \
  --host claude-code --session "<已展开ID>" --project "<同一作用范围>" \
  --target-kind task --target "<已核对任务目录>" --expect-revision "<resolve.context_revision>"

# 整体功能目标用 --target-kind feature；project 传该功能的 workspace。
# 仅用户明确要求忘记本作用范围的焦点时清除关联：
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_context.py" clear \
  --host claude-code --session "<已展开ID>" --project "<同一作用范围>" \
  --expect-revision "<resolve.context_revision>"
```

resolve 是纯读；即使索引不存在或损坏，也不创建、修复目录/记录。它返回：

| 字段 | 用途 |
| --- | --- |
| context_revision | `missing` 或当前索引原始字节哈希；仅用于关联 CAS，不是任务/代码版本 |
| state | `unbound`、`bound`、`invalid_index` 或 `invalid_target` |
| action | `choose_or_start`、`continue` 或 `repair_binding`；不是授权 |
| target | null 或 `{kind,path,id,title,project_path}`；只有 bound 才用于默认续作 |

bind 校验实际目标身份、类型和项目作用范围，再使用锁、版本比较及原子写入保存关联。索引冲突先重读并核对本轮意图，不能盲目用新版本覆盖另一个选择。目标移动、删除、身份改变或项目不一致时不能静默修复；已有明确目标时，可经核对使用当前 context_revision 显式重新 bind。clear 只忘记关联，绝不删除 task/feature 或证据。

任何关联写入失败都如实说明。项目外用户目录的访问仍受客户端权限约束，不改用 Write/cp、其他路径或全局权限绕过。

## status 保持只读

- 本轮明确查询 B：直接查询 B，不把本会话原焦点 A 改为 B。
- 本轮没有明确目标：只读 resolve；仅 bound 时查询该 target。
- 缺少有效关联：说明缺口，不改索引；需要切换或修复由 go 处理。
- 查询不 bind/clear、不生成报告、不导出交接包。缺失或过期页面照实说明。

恢复 task 后显式调用 `reviewable.py continue <target.path> --project <target.project_path> --no-render`；status 使用 locate/status。恢复 feature 使用 feature.py locate/status，按实际授权继续工作。关键事实保存仍使用原 task/feature 的版本与校验，不能把 context_revision 当 task_revision 或 feature_revision。

## 交接与兼容

新会话接手时依据用户给出的任务/功能路径或接手包核对本机目标与代码，再为新会话建立关联；不会将旧会话的权限、生产授权或工作目录自动转移过来。没有可靠 ID 的工具继续使用明确目标路径，不伪造跨会话自动恢复保证。

旧任务及旧 CLI 仍可读取。reviewable.py 的无目标单候选行为仅为兼容保留；go/status 的新会话定位不靠它猜测。只增加内部恢复索引，不自动迁移现有目录，不建立全局 currentTask，也不自动创建 worktree。

本功能不隔离多个任务共同修改的源码、端口、数据库或测试进程。0.17.1 已为遵循新协议的 task/feature render 增加旧报告晚写保护，见 [report-publishing.md](report-publishing.md)。会话关联正确只能说明找对目标，不能据此宣布业务执行没有相互影响。

## 与执行工作区分开

0.19 的本机 checkout 观察和协作活动见 [执行上下文](execution-context.md)。焦点关联不随 begin/end 改写，活动登记也不会改变任务项目和旧证据。普通状态仍纯读，不为查询注册活动。
