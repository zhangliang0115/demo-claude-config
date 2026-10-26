# 执行工作区与协作活动

## 五个概念分开

| 对象 | 表达什么 | 不表达什么 |
| --- | --- | --- |
| 长期任务 | 问题、目标、决定与证据；保留现有 task.json 目录 | 会话私有代码副本 |
| 会话焦点 | 当前宿主会话明确引用哪个任务 | 代码独占权、操作授权 |
| checkout | 此次实际读取/编辑的代码根目录和 Git 工作区 | 独立端口、数据库和外部服务 |
| 本机仓库关系 | Git common dir 相同，说明本机 worktree 来自同一仓库家族 | 跨机器统一逻辑项目 ID |
| 执行活动 | 某会话准备在明确 checkout 读、修改或验证的协作登记 | 业务已执行成功、权限授予、安全沙箱 |

现有 task.project_path 继续决定任务归属、源码指纹和 verify 的 cwd。不会自动改成另一个 worktree，也不移动、合并旧任务。远程 URL 可能相同、改名或经代理，不用它自动合并项目。

## go 中何时使用

普通问答、进度查询和仅关联会话，不为登记新增工具调用。开始持续实施、审查或实际测试前，按需加载本文件：

1. 确认明确任务和本机实际目录。inspect/status 是纯读；已有活动、损坏或不可读取状态如实说明。
2. 准备编辑或验证时，使用主会话真实 host/session 注册 write 或 verify 活动。read 可并行，但存在写活动时源码观察可能改变。已持有本任务 write 的同一执行流程可直接进行范围内验证，不再重复申请 verify；只有独立开始验证时登记 verify，登记不会自动调用测试。只读分析不允许申请 write/verify。
3. 同 checkout 两项写入/验证冲突时，不开始第二项。不因为文件不同就认为安全；先核对正在进行的活动，再选择已有授权范围内串行、同任务协作或明确独立 worktree。登记冲突不自动中断另一个会话、不清理它的记录，也不为所有情况默认建 worktree。
4. 明确不同 worktree 可以并行登记，但只说明源码目录不同。同端口、数据库、缓存、队列或测试账号仍可能共享；已明确共享的资源使用同一 resource 标识登记，未知依赖如实记录。resource 是声明，不是自动探测或资源锁。
5. 活动结束后重新读登记版本，以自己的 token、host/session 和当前版本结束对应活动。先确认实际操作已经停止；失败或会话中断时保留遗留登记，不因时间久就当作已释放。不按 PID、目录名伪造会话身份。
6. 只有执行过实际验证并满足旧证据契约，才记录测试结果。begin/end 的成功、read 模式或当前无活动都不能代替业务验证，也不能证明不存在插件外编辑器或进程写入。

子代理不能修改父会话焦点。父会话统一协调明确切片的写入活动，子代理收到指定任务、目录与边界；如果宿主提供独立可靠 ID，可登记自己负责的活动，但不能据此绕过已有写冲突。

## 身份与异常

活动进行期间不移动、替换或重建执行目录；发现目录或身份变化先停止本次操作并核对，旧活动观察不自动重绑，不能宣称移动后的环境已被同一登记保护。历史路径按记录时的值保留，不按后来符号链接目标重写。

Git 子目录统一识别实际 top-level，符号链接使用规范路径；同时保留请求目录，避免不同入口漏掉同一 checkout。分支、HEAD、Git dir/common dir 只是当时观察。Git 定位环境覆盖不会成为另一个仓库的隐式身份。非 Git 目录仅按实际路径区分，父子目录保守视为范围重叠。

本机统一活动登记保证协作 begin 的比较与写入在同一锁中完成。CAS 冲突重新读取并理解变更，不能盲目重试覆盖。索引损坏/不可读时拒绝登记，不当成空表、不静默修复。活动无自动到期；遗留记录应由原会话明确核对后结束。暂不提供强制接管/清空别人活动的便利动作。

此机制不拦截任意编辑，不自动运行命令，不创建 worktree、不杀进程、不自动发布、不改变现有任务/证据。所有写操作仍须有原任务的授权；读操作也必须在已明确项目范围内。

## 多 worktree 与跨机器接手

同一仓库不同 worktree 的 task.project_path 不同，现有按路径区分的任务目录保持兼容。先确认目标目录、代码版本和环境，再显式创建/接手本机任务并保留原任务引用；不得把旧项目任务直接换绑后沿用旧证据。common dir 只建立本机关系，跨机器逻辑项目映射、任务迁移与证据导入尚未实现。

报告的“代码位置与版本”提供生成时实际任务路径与代码/行为指纹，不实时查询活动。活动变化不冒充业务版本变化；需要最新协作状态时由 Agent 只读查询，不让 HTML 连接本地服务或业务接口。

## 内部工具用法

以下是 Agent 使用的内部工具，用户仍只需 go/status。host/session 使用真实宿主标识；inspect/status 不写事实或报告。

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workspace.py" inspect --project "<明确目录>" --task "<任务目录>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workspace.py" status --project "<明确目录>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workspace.py" begin --project "<明确目录>" --task "<任务目录>" --host claude-code --session "<展开的真实ID>" --mode write --expect-revision "<status.registry_revision>"
# 明确的共享资源可逐项加 --resource "tcp:127.0.0.1:8080"；不同主机/环境应明确区分，不能靠标签证明隔离。
# 确认操作已经停止后，重新status取得最新revision，再结束自己的token：
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workspace.py" end --host claude-code --session "<同一ID>" --token "<begin.activity.token>" --expect-revision "<当前registry_revision>"
```

registry_revision 只表示活动索引字节版本；即使前后相同，也不能推断源码、数据库或其他外部状态未变。observation_unstable=false 仅表示未观察到已登记写入，不是代码稳定证明。

begin 返回 active 才登记成功；conflict 表示未登记，不能当成功继续编辑。CLI 进程正常返回不等于 state=active。end 返回 ended 才确实结束对应登记；not_found 表示此 token 当前没有活动，不是停止了业务进程。state=unknown 或 registry_revision=null 时不尝试 begin/end，也不把 null 换成 missing；如实说明登记不可用并调查原因。CAS 失败先核对，不更改其他会话记录来消除冲突。

无可靠会话 ID 时仍可 inspect/status，不伪造 owner、不调用 begin；说明本次未登记，无法提供会话级活动恢复或完整冲突识别。在明确任务与已有授权下可按单执行者安排继续，不因此新增人工审批；已知写入/资源冲突仍先解决，不能以缺 ID 绕过。索引损坏或不可读与缺 ID 不同，不能称无活动或登记保护已生效，应结合原任务范围和风险处理。原会话无法恢复的遗留登记仍需受控核对后恢复；本版不提供自动接管，不能直接删除索引来假装安全。

## 换工作区或换机器接手（0.26.0）

接手者在另一个 worktree、另一份克隆或另一台机器上继续时，先只读比较：

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/workspace.py" relate --task "<任务绝对目录>" --other "<接手者的 checkout>"
```

| state | 含义 | 接手方式 |
| --- | --- | --- |
| same_checkout | 就是任务绑定的目录 | 照常继续 |
| same_local_family | 同一本机仓库的另一个 worktree | 可协作；旧证据不适用于该 worktree |
| shared_remote | 共享 remote URL 的另一份克隆，可能在另一台机器 | 核对 HEAD、配置与依赖后在该工作区重新验证 |
| unrelated_or_unknown / not_comparable | 无可观察关系 | 不当作同一项目；需人工确认 |

`relate` 不迁移任务、不改 project_path、不改绑证据。任务记录（`~/.claude/zl-dev/`）不随代码同步到其他机器；跨机器接手用 handoff 导出的 HANDOFF.md 与 task.json 副本，在新机器上 init 新任务并在描述中引用原任务 id，旧证据只作参考，不作为新工作区的通过依据。
