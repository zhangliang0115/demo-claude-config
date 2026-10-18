# Claude Code 配置与功能说明

按官方文档整理的配置面和功能面清单，不是教程全文。键名以 [settings reference](https://code.claude.com/docs/en/settings-reference) 为准。文档全集约 228 页，入口是 [文档地图](https://code.claude.com/docs/llms.txt)。

类型和默认值只在文档写明的键上标注。文档随版本变化，以页面原文为准。

## 配置文件和作用域

同一键多处都写了，高的覆盖低的。数组类（`permissions.allow` / `deny` / `ask`、`hooks`、`env`）是合并，不是整段替换。

`fallbackModel`、`modelPicker`、`availableModels`、`modelSettings` 有各自的合并规则，不按普通数组合并。

| 优先级 | 位置 | 作用范围 |
|---|---|---|
| 1 | 组织托管：`managed-settings.json`、MDM、claude.ai console 下发的 server-managed settings | 全组织，个人改不掉 |
| 2 | `claude --settings <file-or-json>` | 仅这一次会话 |
| 3 | `.claude/settings.local.json` | 你自己、这一个项目（创建时会排除出 git） |
| 4 | `.claude/settings.json` | 团队共享，提交进仓库 |
| 5 | `~/.claude/settings.json` | 你自己、这台机器上所有项目 |

另有全局配置 `~/.claude.json`（登录态、MCP 本地/用户范围、项目信任、IDE 自动连接等），不在 settings.json 里。

补充规则：

- 标了仅用户、仅托管、或仅 `~/.claude.json` 的键，写进仓库文件会被忽略。
- 仓库里的 `permissions.allow`、`env` 等，要等目录被信任后才生效。
- `permissions.defaultMode` 的 `auto` 和 `bypassPermissions` 不能从项目或本地文件生效。
- 环境变量不是一个层级。部分行为同时有 shell 变量和设置键，谁赢按那一项自己的说明。

文档：<https://code.claude.com/docs/en/settings>

## 记忆：CLAUDE.md、rules、自动记忆

每个会话的上下文是新的。跨会话靠两类东西：你写的 CLAUDE.md，和 Claude 自己写的自动记忆。两者都是上下文，不是强制配置。要无条件拦住某个动作，用 PreToolUse hook。

| 文件 | 谁写、给谁 |
|---|---|
| 托管 `CLAUDE.md`（见下方路径），或托管设置里的 `claudeMd` 键 | 组织，不可被 `claudeMdExcludes` 排除 |
| `~/.claude/CLAUDE.md`、`~/.claude/rules/*.md` | 你，所有项目 |
| `./CLAUDE.md` 或 `./.claude/CLAUDE.md` | 团队，这个仓库 |
| `./CLAUDE.local.md` | 你，这个项目，应进 `.gitignore` |
| `.claude/rules/**/*.md` | 模块化规则；frontmatter `paths` 用 glob 限定文件，匹配时才加载 |
| `AGENTS.md` / `.claude/AGENTS.md` | 给其他 agent 的说明 |

组织托管 CLAUDE.md 的路径：

- macOS：`/Library/Application Support/ClaudeCode/CLAUDE.md`
- Linux / WSL：`/etc/claude-code/CLAUDE.md`
- Windows：`C:\Program Files\ClaudeCode\CLAUDE.md`

加载方式：

- 启动时加载当前目录及所有父目录的 `CLAUDE.md` 和 `CLAUDE.local.md`。同一目录里 local 排在后面。
- 子目录里的 CLAUDE.md 不在启动时加载，等 Claude 去读、写那个目录的文件才加载。
- `--add-dir` 的目录要设 `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` 才加载其中的 CLAUDE.md。
- 块级 HTML 注释在注入上下文前会被剥掉。

`@import`：

- 语法 `@path/to/file`，相对路径相对于写了这条 import 的文件。
- 最多递归 4 层。路径含空格用反斜杠转义，如 `@Design\ Docs/api.md`。
- 代码块和行内反引号里的 `@` 不解析。
- 指向工作目录外会弹一次批准。

AGENTS.md（v2.1.277+）：

- 默认只在工作目录及其父目录都没有 `CLAUDE.md`、`.claude/CLAUDE.md`、`CLAUDE.local.md` 时才读。`~/.claude/CLAUDE.md` 和 `.claude/rules/` 不算在这个判断里。
- 开关在 `pluginConfigs["cc-plugin-agents-md@builtin"].options.instructionFiles`，取值：
  - `claude-md-or-agents-md`（默认）
  - `claude-md-and-agents-md`
  - `claude-md`
  - `managed-only`
- `/config` 里这项叫 Project instructions。

自动记忆：

- 位置 `~/.claude/projects/<repo>/memory/`，入口文件是 `MEMORY.md`。同一 git 仓库的 worktree 共用一份。
- 每次只加载 `MEMORY.md` 的前 200 行或 25KB。
- 开关 `autoMemoryEnabled`，也可在 `/memory` 里切换，或设 `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`。
- `autoMemoryDirectory` 改存放位置，必须是绝对路径或以 `~/` 开头。

`/memory` 列出并编辑这些文件，包括还不存在的条目。`/init` 生成项目 CLAUDE.md；设 `CLAUDE_CODE_NEW_INIT=1` 后走交互式流程。`/doctor prompt-audit` 审计指令文件（v2.1.283+）。

文档：<https://code.claude.com/docs/en/memory>

## 权限模式

`permissions.defaultMode`，也可会话里 `Shift+Tab` 切换。

| 模式 | 行为 |
|---|---|
| `default`（别名 `manual`；桌面里显示 Manual） | 读工作区不询问；改文件、跑命令要确认 |
| `acceptEdits` | 编辑和常见文件系统命令（`mkdir`、`touch`、`mv`、`cp`）也不询问 |
| `plan` | 只读和出方案，批准前不能改 |
| `auto` | 后台分类器先判断再执行 |
| `dontAsk` | 工作区内的读取和预先批准的工具照跑，其余直接拒绝。只在 CLI，不在 Shift+Tab 循环里 |
| `bypassPermissions` | 全部放行。只适合隔离环境 |

规则：

- 求值顺序 `deny` → `ask` → `allow`，先匹配的生效。
- `deny` 在所有模式里都生效，包括 `bypassPermissions`。
- 显式 `ask` 规则在任何模式都不会自动放行。
- 规则语法：`Bash(npm run build)` 精确、`Bash(npm run *)` 通配、`Bash(* --version)`、`Read(./.env)`、`WebFetch(domain:example.com)`、`Agent(Explore)`、`mcp__<server>__<tool>`。
- `Shift+Tab` 循环是 `default` → `acceptEdits` → `plan`。`auto` 可用时排在 plan 后面；`bypassPermissions` 要先被放进循环才出现。
- 桌面 Code 标签把选过的模式按文件夹记住，Plan 只对当前会话。
- `auto` 和 `bypassPermissions` 写在项目或本地 settings 里会被忽略。
- `--permission-mode <mode>` 只对本次会话。`--dangerously-skip-permissions` 等于 `bypassPermissions`。`permissions.disableBypassPermissionsMode` 设为 `"disable"` 后进不去。

`permissions` 其余键：`allow`、`ask`、`deny`、`additionalDirectories`、`blockReadsOutsideWorkingDirectories`（任一处为 true 就生效，v2.1.257+）、`disableAutoMode`。

文档：<https://code.claude.com/docs/en/permission-modes>、<https://code.claude.com/docs/en/permissions>

## settings.json 键

带 † 的主要给组织托管。标了范围的不能随便放进项目文件。未标注范围的，用户、项目、本地、托管四类文件都可以写。

### 模型和回答

- `model`：会话默认模型（别名或完整 ID）。`--model` 和 `ANTHROPIC_MODEL` 可覆盖。托管里的 `model` 只是起始默认，真正的限制是 `availableModels` 和 `deniedModels`
- `modelPicker`：自定义模型菜单。仅用户或托管。`options[]` 含 `model`（必填）、`label`、`description`、`behavesAs`（v2.1.257+），以及 `replaceBuiltInOptions`（默认 false）。需要 v2.1.242+
- `modelOverrides`：模型 ID → 供应商侧 ID（如 Bedrock ARN）
- `modelSettings.<模型>`：按模型存 `effortLevel`、`maxEffortLevel`、`autoCompactWindow`（整数 100000–1000000，或 `"auto"`）。按规范模型名做键，别名和带日期的 ID 会归到同一条。v2.1.251+
- `effortLevel`：`low` / `medium` / `high` / `xhigh`。顶层默认；按模型保存的以 `modelSettings` 为准
- `maxEffortLevel`：`low` / `medium` / `high` / `xhigh` / `max`（`max` 等于不封顶）。多处取最低。v2.1.267+
- `availableModels`：可选模型白名单。`enforceAvailableModels`（默认 false，v2.1.175+）让 Default 也落在这个名单里
- † `availableModelsMatch`：`prefix`（默认）或 `exact`，仅托管，v2.1.283+
- † `deniedModels`：黑名单，仅托管，v2.1.283+。`best`、`opusplan`、`default` 会被忽略
- `fallbackModel`：有序备选，最多保留 3 个。不跨文件合并，取优先级最高的那份
- `advisorModel`：`fable` / `opus` / `sonnet` 或完整 ID。不设等于关掉 advisor。`CLAUDE_CODE_DISABLE_ADVISOR_TOOL` 关掉后，这个键开不回来。三层生效条件见下方「advisor 工具」
- `alwaysThinkingEnabled`：布尔。`false` 关扩展思考；`true` 是空操作。默认开着
- `fastMode`：布尔，`/fast` 切换。`fastModePerSessionOptIn`（默认 false）为 true 时每次会话都要再开一次
- `language`：界面语言，字符串，不校验
- `outputStyle`：见下方「输出风格」。区分大小写
- `showThinkingSummaries`：布尔，默认 false。true 时用 Ctrl+O 看完整思考摘要
- `switchModelsOnFlag`：布尔。安全分类器命中时是否自动换模型。false 则交互会话暂停，`-p` 直接报错
- `ultracode`：布尔，默认关。需要动态工作流和 `xhigh`。Claude Code 只读不写这个键。v2.1.284+
- `promptCacheTtl`、`subagentPromptCacheTtl`：`5m` 或 `1h`。覆盖顺序：`FORCE_PROMPT_CACHING_5M` > 对应环境变量 > 这个键 > `ENABLE_PROMPT_CACHING_1H`。v2.1.242+
- † `modelPricing`：托管计费倍率，仅托管，v2.1.242+

### 会话、子代理、worktree

- `agent`：每个会话以某个命名子代理启动
- `crossSessionInbound`：其他会话发来的消息。`accept` < `hold` < `refuse`，项目或本地可以设得更严
- `disableAgentView`：关掉后台代理和 agent 视图
- `isolatePeerMachines`：给其他机器上的会话发消息前先问。任一处为 true 即生效
- `teammateMode`：agent team 队友的显示方式
- `processWrapper`：后台进程的企业启动器，macOS / Linux。仅用户或托管
- `worktree.baseRef`：`fresh`（默认，从远端默认分支）或 `head`（从本地 HEAD）
- `worktree.bgIsolation`：后台会话是否可以不建 worktree 就改文件
- `worktree.sparsePaths`：只检出列出的目录
- `worktree.symlinkDirectories`：大目录用符号链接而不是复制
- `worktree.location`：桌面 SSH 会话建 worktree 的位置。仅用户

### 远程、桌面、通知

- `remoteControlAtStartup`：会话开始就连上 Remote Control。项目或本地设 `false` 可以压过托管的 `true`
- `disableRemoteControl`：彻底关掉 Remote Control
- `remote.defaultEnvironmentId`：`claude --cloud` 的默认云环境。自托管的 `ccpool_` ID 只从用户、托管和 `--settings` 读
- `agentPushNotifEnabled`：允许 Claude 发手机推送
- `inputNeededNotifEnabled`：Claude 在等你时推送
- `preferredNotifChannel`：完成通知走终端铃声还是桌面通知
- `awaySummaryEnabled`：回到终端时给一段会话回顾
- `enableArtifact`：`false` 关掉 Artifact 工具，任何文件都开不回来。`disableArtifact` 已弃用
- `disableDeepLinkRegistration`：不再注册 `claude-cli://`
- † `disableDesktopLocalSessions`：关掉桌面的本机 Code 会话
- `sshConfigs`：桌面下拉里的 SSH 连接。仅用户或托管
- † `sshHostAllowlist`：限制可连的 SSH 主机

### MCP

- `enableAllProjectMcpServers`：批准项目 `.mcp.json` 里的全部服务器
- `enabledMcpjsonServers`：按名字批准
- `disabledMcpjsonServers`：按名字拒绝，所有权限模式都生效
- `allowedMcpServers`、`deniedMcpServers`：按 `serverName` 或 `serverUrl` 允许或拒绝
- `disableClaudeAiConnectors`：不再拉取 claude.ai 连接器。任一处为 true 即生效
- † `managedMcpServers`：组织下发的远程服务器，优先级高于所有作用域。v2.1.259+
- † `allowManagedMcpServersOnly`：只用托管白名单
- † `allowAllClaudeAiMcps`：托管 MCP 之外也加载 claude.ai 连接器
- † `allowClaudeInChromeWithManagedMcp`：有托管 MCP 时仍允许 Claude in Chrome

前两项如果提交在仓库 settings 里，目录未被信任时会被忽略。来自 `~/.claude/settings.json`、托管和 `--settings` 的批准仍然有效。

### 插件和 skills

- `enabledPlugins`：按作用域开关插件，键是 `插件名@市场名`
- `extraKnownMarketplaces`：登记市场来源
- `pluginConfigs`：插件自己的配置答案。仅用户或托管
- `skillOverrides`：隐藏或折叠某些 skill
- `disableBundledSkills`：关掉内置 skills 和工作流
- `disableSkillShellExecution`：skill 和自定义命令里不再内联执行 shell
- `syncClaudeAiPlugins`、`syncClaudeAiSkills`：设 `false` 停止加载从 claude.ai 同步来的插件或 skill。用户、本地或托管
- `appendPlugins`、`prependPlugins`：组织的 mod 排在用户 mod 之后或之前。仅用户或托管
- † `strictKnownMarketplaces`：市场来源白名单
- † `blockedMarketplaces`：屏蔽某些市场
- † `strictPluginOnlyCustomization`：禁止用户和项目级的 skills、agents、hooks、MCP。可分子键 `.agents`、`.hooks`、`.mcp`、`.skills`
- † `allowedChannelPlugins`、`channelsEnabled`、`disableCommandPluginSources`
- † `pluginSuggestionMarketplaces`、`pluginTrustMessage`

### Hooks 和工作流

- `hooks`：见下方「Hooks」
- `enableWorkflows`：给自己开或关动态工作流
- `disableWorkflows`：给所有人关掉
- `workflowSizeGuideline`：工作流的目标代理数量
- `workflowKeywordTriggerEnabled`：消息里的 `ultracode` 是否触发工作流
- `disableAllHooks`：关掉 hooks，同时关掉 status line 和 `@` 文件建议命令
- `allowedHttpHookUrls`：限制 HTTP hook 的目标
- `httpHookAllowedEnvVars`：HTTP hook 允许放进请求头的环境变量
- † `allowManagedHooksOnly`：只跑组织的 hooks

### 鉴权和供应商

- `apiKeyHelper`：生成 API 凭证的命令
- `awsAuthRefresh`、`awsCredentialExport`：Bedrock 凭证
- `gcpAuthRefresh`：Google Cloud 凭证
- `otelHeadersHelper`：生成轮换的 OpenTelemetry 请求头
- `forceLoginMethod`：限制登录方式（claude.ai、Console，或云网关）
- `forceLoginOrgUUID`：把 claude.ai 登录钉在某个组织。托管来源会强制执行
- `forceLoginGatewayUrl`：登录用的网关地址。仅用户或托管
- † `allowedProviders`：限制可用的 API 供应商
- † `gatewayInternalNetworks`：允许 `/login` 访问内网公网 IPv4 段上的网关

### 上下文和输出限制

- `autoCompactEnabled`：自动压缩开关
- `autoCompactWindow`：上下文填到多少开始压缩
- `idleCompaction`：终端空闲时是否停止压缩
- `autoMemoryEnabled`、`autoMemoryDirectory`：见「记忆」
- `claudeMd`：组织注入的 CLAUDE.md 内容。仅托管
- `claudeMdExcludes`：跳过匹配的 CLAUDE.md，glob 数组，跨层合并。托管的 CLAUDE.md 排除不掉
- `env`：会话和子进程的环境变量。这里的值覆盖 shell 里的同名变量；设成 `""` 用来抵消 shell 已 export 的值。桌面或自托管 runner 的启动环境优先于 `env`
- `fileCheckpointingEnabled`：为 `/rewind` 保留文件快照
- `plansDirectory`：plan 模式写方案文件的目录
- `bashOutputMaxChars`：成功命令的内联输出大小
- `skillListingBudgetFraction`：留给 skill 列表的上下文比例
- `skillListingMaxDescChars`：单条 skill 描述的长度上限
- `taskOutputMaxChars`：已在 v2.1.277 删除

### 界面

- `theme`：配色
- `editorMode`：提示符里用 vim 键位
- `verbose`：完整工具输出。和 `viewMode` 同时设时，`viewMode` 赢
- `viewMode`：`default` / `verbose` / `focus`
- `tui`：全屏或经典渲染
- `statusLine`：见「状态栏」
- `subagentStatusLine`：子代理任务行的显示
- `spinnerTipsEnabled`、`spinnerTipsOverride`、`spinnerVerbs`、`showTurnDuration`
- `syntaxHighlightingDisabled`：关掉 diff 和代码高亮
- `terminalProgressBarEnabled`、`terminalTitleFromRename`
- `prefersReducedMotion`、`axScreenReader`
- `timeFormat`：12 小时、24 小时、UTC，或 strftime
- `timeZone`、`maxProseWidth`
- `promptSuggestionEnabled`、`emojiCompletionEnabled`
- `defaultShell`：`!` 命令用 Bash 还是 PowerShell
- `fileSuggestion`：自定义 `@` 文件补全命令
- `respectGitignore`：`@` 选择器是否排除 gitignore 的文件
- `respondToBashCommands`：`!` 命令之后 Claude 是否接着回应
- `autoScrollEnabled`、`showClearContextOnPlanAccept`
- `voice`、`voiceEnabled`（旧的单键写法）
- `vimInsertModeRemaps`：INSERT 模式下的双键序列映射到 Escape。仅用户或托管
- `keybindingFlavor`：已弃用，无效果
- `askUserQuestionTimeout`、`dialogExpiry`：仅用户或托管
- `autoContinueAtUsageLimit`：用量重置后自动继续。仅用户或托管
- `companyAnnouncements`：启动时的公告
- `footerLinksRegexes`：把匹配的 issue 或 review ID 变成可点链接。仅用户或托管
- `spellcheck`、`bashEditDiffEnabled`：仅用户或托管
- `wheelScrollAccelerationEnabled`

### Git 署名

- `attribution.commit`：commit trailer
- `attribution.pr`：PR 描述里的署名
- `attribution.sessionUrl`：云端和 Remote Control 的 commit 是否带会话链接
- `includeCoAuthoredBy`：已弃用，改用 `attribution`
- `includeGitInstructions`：是否移除内置的 commit 和 PR 说明
- `prUrlTemplate`：把 PR 链接指向内部工具

### 隐私和更新

- `cleanupPeriodDays`：transcript 保留天数
- `desktopSessionCleanupPeriodDays`：桌面和 Cowork transcript 的保留期限。仅用户或托管
- `feedbackDrafts`：把反馈草稿排队待审。仅用户或托管
- `feedbackSurveyRate`：会话质量调查的频率
- `skipWebFetchPreflight`：Anthropic 不可达时跳过 WebFetch 的主机名检查
- `autoUpdatesChannel`：`stable` 或 `latest`
- `minimumVersion`：自动更新不低于这个版本
- † `requiredMinimumVersion`、`requiredMaximumVersion`：超出范围就拒绝启动

### 沙箱

`sandbox.*`，作用于 Bash、PowerShell、Monitor 及其子进程。文件工具、MCP、hooks 不在沙箱里。平台是 macOS、Linux、WSL2；原生 Windows 不走沙箱。

默认可写：当前工作目录、用户临时目录、`--add-dir` 或 `permissions.additionalDirectories` 里的目录。沙箱路径里 `/tmp/build` 是绝对路径，`~/.kube` 相对家目录。这和 Read/Edit 的权限规则不同，后者用 `//path` 表示绝对路径。

- `enabled`：开关，默认 false。也可在会话里 `/sandbox`
- `failIfUnavailable`：沙箱跑不起来就拒绝启动。默认 false
- `autoAllowBashIfSandboxed`：沙箱内命令免审批。默认 true
- `allowUnsandboxedCommands`：沙箱失败后是否允许到沙箱外重试。默认 true；false 即严格模式
- `excludedCommands`：这些命令在沙箱外运行，语法同 `Bash(...)` 通配
- `enableWeakerNestedSandbox`：Linux / WSL2，在非特权容器里用较弱的沙箱
- `enableWeakerNetworkIsolation`：macOS，MITM 代理后面的 TLS 校验
- `allowAppleEvents`：macOS 允许 Apple Events。仅用户或托管
- `ignoreViolations`：按命令子串忽略预期的探测违规
- `ripgrep`：自定义 ripgrep 二进制，`command` 和 `args`。仅用户或托管
- † `bwrapPath`、`socatPath`：bubblewrap 和 socat 的路径
- `filesystem.allowWrite` / `denyWrite` / `denyRead` / `allowRead`
- `filesystem.disabled`：关掉文件系统隔离。仅用户或托管
- † `filesystem.allowManagedReadPathsOnly`
- `network.allowedDomains` / `deniedDomains`
- `network.allowUnixSockets` / `allowAllUnixSockets`（macOS）
- `network.allowLocalBinding`：监听端口和 localhost。macOS
- `network.allowMachLookup`：macOS XPC
- `network.httpProxyPort` / `socksProxyPort`
- `network.strictAllowlist`：不在名单里的直接拒绝而不是询问。仅用户或托管
- `network.tlsTerminate`：代理终结 TLS。仅用户或托管
- † `network.allowManagedDomainsOnly`
- `credentials.files`、`credentials.envVars`：`deny` 或 `mask`
- `credentials.allowPlaintextInject`、`credentials.awsPairs`：仅用户或托管
- `credentials.sigv4`：`streaming` / `presigned` / `sigv4a`，各为 `deny` 或 `passthrough`

文档：<https://code.claude.com/docs/en/sandboxing>

### 工具和企业托管

- † `browserExternalPageTools`：Browser 窗格里，Claude 的工具是否作用于外部页面
- † `disableBrowserExternalNavigation`：Browser 窗格只允许 localhost
- † `disableMobileSimulatorTools`：禁用 iOS 模拟器窗格里的工具
- † `disableSideloadFlags`：拒绝用来旁路加载插件、子代理或 MCP 的 CLI 参数
- † `forceRemoteSettingsRefresh`：刷新到 server-managed settings 之前不许启动
- † `managedSourcesBehavior`：多个托管来源是合并还是只取最高的
- † `parentSettingsBehavior`：嵌入宿主带来的限制是应用还是丢弃
- † `policyHelper` 及 `.path`、`.refreshIntervalMs`、`.timeoutMs`
- † `wslInheritsWindowsSettings`：WSL 读取 Windows 的策略链

### `~/.claude.json` 里的键

这些不在 settings.json：

- `autoConnectIde`：自动连接正在运行的 VS Code 或 JetBrains
- `autoInstallIdeExtension`：关掉 IDE 扩展自动安装
- `claudeInChromeDefaultEnabled`：会话开始时启用 Chrome 集成
- `copyFullResponse`：`/copy` 直接复制完整回复，不弹选择
- `copyOnSelect`：关掉选中即复制
- `defaultToAgentsView`：不带参数运行 `claude` 时打开 agent 视图
- `diffTool`：用 VS Code 或 JetBrains 的 diff，而不是终端
- `externalEditorContext`：Ctrl+G 时把上一条回复作为注释带进外部编辑器
- `leftArrowOpensAgents`：关掉左箭头打开 agent 视图
- `prStatusFooterEnabled`：关掉 PR 评审状态徽章

已删除：`permissionExplainerEnabled`（v2.1.257）、`teammateDefaultModel`（v2.1.234）。

## 斜杠命令

完整表在 [commands](https://code.claude.com/docs/en/commands)。命令只在消息开头识别，后面的文字是参数。一次最多串 6 个 skill。标了 skill 的本质是一段提示词。

### 会话

- `/clear`（别名 `/reset`、`/new`）：新会话，保留项目记忆
- `/resume`（别名 `/continue`）：回到早前的会话
- `/branch`：从当前点分支出一条对话
- `/fork`（别名 `/bg`）：复制到一个后台会话
- `/background`：把整个会话转成后台代理
- `/compact [说明]`：压缩上下文
- `/context [all]`：上下文占用
- `/btw [问题]`：旁路提问，不进历史
- `/rewind`（别名 `/checkpoint`、`/undo`）：回退代码或对话到某个检查点
- `/export [文件名]`：导出纯文本
- `/copy`：复制回复
- `/exit`（别名 `/quit`）：退出。挂在后台会话上时是断开，会话继续跑
- `/rename`：改会话标题
- `/recap`：生成一行会话摘要
- `/color`：当前会话的提示条颜色
- `/focus`：只看最后一条提示和工具调用摘要
- `/cd <路径>`：把会话的工作目录挪走
- `/add-dir <路径>`：增加一个工作目录
- `/stop`：停掉挂着的后台会话
- `/tasks`（别名 `/bashes`）：当前会话的后台任务，包括已结束的子代理
- `/teleport`（别名 `/tp`）：把云端会话拉到这个终端。需要 claude.ai 订阅
- `/goal`：设定一个目标，持续多轮直到满足
- `/subtask <任务>`：派一个子代理，结果回到这个对话

### 模型和权限

- `/model [模型]`：切换并保存为新会话的默认。`s` 只对本次会话
- `/effort [级别|auto|status|ultracode]`：`low`、`medium`、`high`、`xhigh`、`max`、`auto`
- `/fast`：快速模式
- `/advisor`：advisor 工具用的模型
- `/autocompact`：自动压缩窗口
- `/plan [描述]`：进入 plan 模式
- `/permissions`（别名 `/allowed-tools`）：管理 allow / ask / deny
- `/sandbox`：切换沙箱。仅支持的平台
- `/config`（别名 `/settings`）：设置界面，或 `/config key=value`
- `/status`：版本、模型、账号、连通性、设置来源
- `/usage`（别名 `/cost`、`/stats`）：费用和用量
- `/privacy-settings`：Pro 和 Max
- `/rate-limit-options`：碰到用量限制时的选项
- `/usage-credits`：配置或申请用量额度

### 界面

- `/theme`、`/tui`、`/terminal-setup`、`/scroll-speed`
- `/output-style [风格]`：v2.1.269+
- `/statusline`：配置状态栏
- `/keybindings`：打开快捷键文件
- `/voice`：语音听写
- `/vim`：已在 v2.1.92 删除，改到 `/config` 的 Editor mode

### 记忆、扩展、诊断

- `/init`：生成 CLAUDE.md
- `/memory`：编辑记忆文件，开关自动记忆
- `/mcp [reconnect|enable|disable]`：管理 MCP 服务器和 OAuth
- `/hooks`：查看 hook 配置
- `/agents`：创建或管理子代理
- `/list-agents`（别名 `/peers`）：列出子代理、队友和其他会话。v2.1.224+
- `/skills`：列出 skills
- `/reload-skills`、`/reload-plugins`
- `/plugin`：插件菜单，或 `list`、`install`、`enable`、`disable`、`uninstall`、`marketplace add`
- `/doctor`（别名 `/checkup`）：安装和配置体检。`prompt-audit` 需要 v2.1.283+
- `/debug`：诊断运行时问题
- `/feedback`（别名 `/bug`、`/share`）：带会话上下文提交反馈
- `/ide`：IDE 集成
- `/import [codex|gemini|cursor]`：导入其他工具的配置
- `/insights`：分析这台机器上近期会话的 HTML 报告
- `/release-notes`、`/help`

### 审查和并行

- `/diff`：工作区改动
- `/code-review`（别名 `/review`）：按 `low` 到 `max` 审查，可加 `--fix`、`--comment`、`--max-findings`，目标可以是 PR 号、分支或路径
- `/ultrareview`：`/code-review ultra` 的别名，云端多代理审查
- `/security-review`：查安全问题
- `/simplify`：skill。复用、简化和效率清理，不找 bug
- `/batch <指令>`：skill。大改动拆成独立单元，每个一个 worktree
- `/workflows`：工作流进度视图

### 账号和集成

- `/login`、`/logout`、`/upgrade`
- `/remote-control`（别名 `/rc`）：从其他设备继续这个本地会话
- `/remote-env`：选择默认云环境
- `/desktop`（别名 `/app`）：macOS 或 x64 Windows，且登录了 Claude 订阅
- `/mobile`（别名 `/ios`、`/android`）
- `/chrome`：Claude in Chrome
- `/install-github-app`、`/install-slack-app`
- `/web-setup`：用本机 `gh` 给云端会话连 GitHub
- `/setup-bedrock`、`/setup-vertex`：没配对应环境时菜单里不显示

### 内置 skills

`/verify`、`/run`、`/run-skill-generator`、`/deep-research`、`/loop`（别名 `/proactive`）、`/fewer-permission-prompts`、`/skill-doctor`、`/design`、`/design-sync`、`/design-login`、`/dataviz`、`/slides`、`/artifact-capabilities`、`/artifact-diagramming`、`/artifacts`、`/workflow-authoring`、`/plugin-authoring`、`/auto-mode-setup`、`/claude-api`、`/update-config`、`/powerup`、`/team-onboarding`、`/insights`。

`/schedule`（别名 `/routines`）管理云端 routine。部分登录方式下这个命令不存在。

已删除：`/ultraplan`（改用 plan 模式）、`/pr-comments`（v2.1.91）。

## Hooks

写在 settings 的 `hooks` 里。也可以来自插件 `hooks/hooks.json`、skill 或子代理 frontmatter（只在该组件生效）。没有单独的 `.claude/hooks` 配置文件，那个目录只是放脚本的地方。

文档：<https://code.claude.com/docs/en/hooks>

### 事件

共 33 个：

| 事件 | 何时 |
|---|---|
| `SessionStart` | 会话开始或恢复 |
| `Setup` | `--init-only`，或 `-p` 下的 `--init` / `--maintenance` |
| `UserPromptSubmit` | 提交提示词之后、Claude 处理之前 |
| `UserPromptExpansion` | 用户输入的命令展开成提示词之前 |
| `PreToolUse` | 工具调用执行前 |
| `PermissionRequest` | 工具调用需要一次权限决定 |
| `PermissionDenied` | auto 模式拒绝了一次调用 |
| `PostToolUse` | 工具调用成功后 |
| `PostToolUseFailure` | 工具调用失败后 |
| `PostToolBatch` | 一批并行工具调用全部结束后、下一次模型调用前 |
| `Notification` | Claude Code 发出通知 |
| `MessageDisplay` | 显示助手消息文本时 |
| `SubagentStart` | 子代理启动 |
| `SubagentStop` | 子代理结束 |
| `TaskCreated` | 创建任务 |
| `TaskCompleted` | 任务标记完成 |
| `Stop` | Claude 回应结束 |
| `StopFailure` | 这一轮因 API 错误结束 |
| `TeammateIdle` | agent team 的队友即将空闲 |
| `InstructionsLoaded` | 加载了 CLAUDE.md 或 `.claude/rules/*.md` |
| `ConfigChange` | 会话中配置文件变了 |
| `CwdChanged` | 工作目录变了 |
| `DirectoryAdded` | 会话中增加了工作目录 |
| `FileChanged` | 被监视的文件变了 |
| `WorktreeCreate` | 创建 worktree |
| `WorktreeRemove` | 移除由 `WorktreeCreate` 创建的 worktree |
| `PreCompact` | 压缩上下文之前 |
| `PostCompact` | 压缩完成之后 |
| `PreModelSwitch` | 应用一次模型切换之前 |
| `PostModelSwitch` | 会话模型变了之后 |
| `Elicitation` | MCP 服务器在工具调用中向用户要输入 |
| `ElicitationResult` | 用户回应了这次询问 |
| `SessionEnd` | 会话终止 |

### 结构

三层：事件 → matcher 组 → handler 数组。

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(rm *)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh",
            "args": []
          }
        ]
      }
    ]
  }
}
```

matcher：

- `"*"`、`""` 或省略：匹配全部。
- 只含字母、数字、`_`、`-`、空格、`,`、`|`：精确匹配，或用 `|`、`,` 分隔的列表。
- 含其他字符：未锚定的 JavaScript 正则，整段匹配要自己加 `^` 和 `$`。
- 工具事件匹配 `tool_name`。`SessionStart` 匹配 `source`：`startup`、`resume`、`clear`、`compact`、`fork`。
- 事件本身不支持 matcher 时，写了也会被静默忽略。

handler 类型：

| type | 专有字段 |
|---|---|
| `command` | `command`、`args`、`async`、`asyncRewake`、`shell`、`onFailure` |
| `http` | `url`、`headers`、`allowedEnvVars`、`onFailure` |
| `mcp_tool` | `server`、`tool`、`input` |
| `prompt` | `prompt`（用 `$ARGUMENTS`）、`model` |
| `agent` | `prompt`、`model` |

公共字段：`type`、`if`（权限规则语法，仅工具事件）、`timeout`、`statusMessage`、`once`。超时默认：command / http / mcp_tool 600 秒，prompt 30 秒，agent 60 秒。

### 输入和退出码

stdin（或 HTTP POST body）的公共字段：`session_id`、`prompt_id`、`transcript_path`、`cwd`、`scratchpad_dir`、`permission_mode`、`effort`、`hook_event_name`、`agent_id`、`agent_type`。工具事件另有 `tool_name`、`tool_input`、`tool_use_id`。

退出码：

- 0：成功。stdout 是单个 JSON 对象就按 JSON 解析，否则当纯文本。纯文本只有 `UserPromptSubmit`、`UserPromptExpansion`、`SessionStart`、`PostModelSwitch` 会加进上下文。
- 2：阻断。stderr 是原因。能阻断的事件包括 `PreToolUse`、`UserPromptSubmit`、`UserPromptExpansion`、`Stop`、`SubagentStop`、`TeammateIdle`、`TaskCreated`、`TaskCompleted`、`ConfigChange`、`PreCompact`、`PreModelSwitch`、`Elicitation`、`ElicitationResult`、`WorktreeCreate`、`WorktreeRemove`、`PostToolBatch`。`PostToolUse` 和 `PostToolUseFailure` 上工具已经跑完，exit 2 撤不回。`PermissionRequest` 不看 exit 2，要在 JSON 里拒绝。
- 其他：不阻断，只在记录里留一条提示。

`PreToolUse` 的决定写在 stdout JSON 里：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "原因"
  }
}
```

`permissionDecision` 取值 `allow`、`deny`、`ask`、`defer`。`PermissionRequest` 用 `decision.behavior` 的 `allow` 或 `deny`。`continue: false` 在所有事件上都会让 Claude 停下来。`onFailure: "block"`（v2.1.295+）让失败或超时的 command / http hook 也阻断。

## MCP

文档：<https://code.claude.com/docs/en/mcp>

| 范围 | 存在哪 | 谁能用 |
|---|---|---|
| local（默认） | `~/.claude.json` 的 `projects["<路径>"].mcpServers` | 仅当前项目 |
| project | 仓库根 `.mcp.json` | 团队，交互会话里要批准后才跑 |
| user | `~/.claude.json` 顶层 `mcpServers` | 所有项目 |

同名时优先级：托管 `managedMcpServers` > local > project > user > 插件 > claude.ai 连接器。不跨作用域合并字段。`claude -p`、Agent SDK 和云端会话加载项目服务器时不弹批准。

```json
{
  "mcpServers": {
    "local-tool": {
      "command": "npx",
      "args": ["-y", "@example/server"],
      "env": { "API_KEY": "${API_KEY}" }
    },
    "remote-api": {
      "type": "http",
      "url": "${API_BASE_URL:-https://api.example.com}/mcp",
      "headers": { "Authorization": "Bearer ${API_TOKEN}" }
    }
  }
}
```

- stdio：`command`、`args`、`env`。不写 `type` 就是 stdio。
- 远程：`type` 为 `http`（别名 `streamable-http`）、`sse`（已弃用）或 `ws`，加 `url`、`headers`。有 `url` 却没有 `type` 会被跳过。
- 还可写 `headersHelper`（一条打印 JSON 请求头的命令，限 10 秒）、`timeout`（单次工具调用，毫秒）、`alwaysLoad`、`oauth`（`clientId`、`callbackPort`、`authServerMetadataUrl`、`scopes`）。
- `"type": "sdk"` 只能由 SDK 宿主注册，写在文件里会被跳过。
- 服务器名只允许字母、数字、连字符、下划线。

`${VAR}` 和 `${VAR:-default}` 在 `command`、`args`、`env`、`url`、`headers` 里展开。没设又没有默认值时保留字面量并警告。远程 `url` 和 `headers` 里，`ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN`、`AWS_BEARER_TOKEN_BEDROCK`、`HTTPS_PROXY`、`NPM_TOKEN` 这类凭证变量会展开成空。stdio 服务器的环境里有 `CLAUDE_PROJECT_DIR`。

工具名是 `mcp__<server>__<tool>`。插件自带的服务器是 `mcp__plugin_<plugin>_<server>__<tool>`。

```bash
claude mcp add --transport http <名字> <url>
claude mcp add --transport stdio <名字> -- <命令> [参数...]
claude mcp add-json <名字> '<json>' --scope user
claude mcp list
claude mcp get <名字>
claude mcp remove <名字>
claude mcp login <名字>
claude mcp reset-project-choices
claude mcp serve
claude mcp add-from-claude-desktop
```

`/mcp` 里禁用服务器，写的是 `~/.claude.json` 的 `disabledMcpServers` 或 `enabledMcpServers`，和 settings 里的 `enabledMcpjsonServers` 不是同一份名单。`MCP_TIMEOUT` 是启动超时，`MAX_MCP_OUTPUT_TOKENS` 默认 25000。

## Skills

文档：<https://code.claude.com/docs/en/skills>

位置：托管设置目录、`~/.claude/skills/<name>/SKILL.md`、`.claude/skills/<name>/SKILL.md`、子目录里的 `.claude/skills/`、`--add-dir` 带进来的、插件的 `skills/`。插件 skill 的调用名是 `/插件名:skill名`。

同名时托管 > 个人 > 项目。skill 优先于旧的 `.claude/commands/` 同名文件。`SKILL.md` 建议不超过 500 行，旁边可以放 `reference.md`、`scripts/` 等，Claude 按需读。

frontmatter：

- `name`、`description`、`when_to_use`（和 description 合并，截断在 1536 字符）
- `argument-hint`、`arguments`
- `disable-model-invocation`：默认 false。true 则 Claude 不会自己调用
- `user-invocable`：默认 true。false 则只能由 Claude 调用
- `allowed-tools`：调用期间这些工具免审批，不限制别的工具
- `disallowed-tools`
- `model`（可用 `inherit`）、`effort`
- `context: fork`：在分支出的子代理里跑。配合 `agent`、`background`
- `hooks`、`paths`、`shell`（`bash` 或 `powershell`）
- `metadata`、`license`、`compatibility`：Claude Code 不处理，只是信息

正文替换：`$ARGUMENTS`、`$ARGUMENTS[N]`、`$N`、`${CLAUDE_SESSION_ID}`、`${CLAUDE_EFFORT}`、`${CLAUDE_SKILL_DIR}`、`${CLAUDE_PROJECT_DIR}`、`${CLAUDE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_DATA}`。`` !`command` `` 在发送前执行，输出替换掉占位符。

`/skills` 列出，`/reload-skills` 重新扫描。

## 子代理

文档：<https://code.claude.com/docs/en/sub-agents>

每个是一个带 YAML frontmatter 的 Markdown。位置和同名优先级：托管 > `--agents` 的 JSON（仅本次会话）> `.claude/agents/` > `~/.claude/agents/` > 插件的 `agents/`。

必填只有 `name` 和 `description`。`name` 不能含 `:`，最长 256 字符。未知字段会被静默忽略。

其余字段：`tools`（白名单）、`disallowedTools`、`model`（`sonnet` / `opus` / `haiku` / `fable` / 完整 ID / `inherit`）、`permissionMode`、`maxTurns`、`skills`、`mcpServers`、`hooks`、`memory`（`user` / `project` / `local`）、`background`、`isolation`（`worktree`）、`effort`、`omitClaudeMd`、`autoCompactWindow`、`color`、`initialPrompt`。插件里的子代理忽略 `hooks`、`mcpServers`、`permissionMode`。

模型解析顺序：调用时传入的参数 > frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` > 当前会话的模型。

内置类型：

| 名字 | 用途 |
|---|---|
| `Explore` | 只读搜索，拒绝 Write 和 Edit，不加载 CLAUDE.md |
| `Plan` | plan 模式里的只读研究 |
| `general-purpose` | 多步骤任务，子代理可用的工具都有 |
| `claude` | 兜底 |
| `statusline-setup` | `/statusline` 使用 |
| `claude-code-guide` | 回答 Claude Code 本身的问题 |

在 `permissions.deny` 里写 `Agent(Explore)` 禁用某一个。拒绝 `Agent` 工具本身则全部不能委派。

## 插件

文档：<https://code.claude.com/docs/en/plugins/overview>

一个插件是一个目录：清单 `.claude-plugin/plugin.json`，组件放 `skills/`、`agents/`、`hooks/hooks.json`、`.mcp.json`、`output-styles/`，还可以带一个改界面的 JavaScript mod。

市场是一份 `.claude-plugin/marketplace.json`，不是托管商店。官方市场 `claude-plugins-official` 在第一次启动交互式终端时自动添加，除非被托管策略挡住。

安装范围：`user`（默认）、`project`（写进 `.claude/settings.json`）、`local`（写进 `.claude/settings.local.json`）。

```bash
claude plugin install code-review@claude-plugins-official
claude plugin marketplace add <来源>
```

`claude plugin`（别名 `claude plugins`）还有 `init`、`uninstall`、`enable`、`disable`、`update`、`list`、`details`、`configure`、`prune`、`eval`、`validate`。会话里用 `/plugin` 和 `/reload-plugins`。

## 快捷键

文档：<https://code.claude.com/docs/en/keybindings>

文件是 `~/.claude/keybindings.json`，`/keybindings` 创建或打开，改完自动加载。

```json
{
  "$schema": "https://www.schemastore.org/claude-code-keybindings.json",
  "bindings": [
    {
      "context": "Chat",
      "bindings": {
        "ctrl+e": "chat:externalEditor",
        "ctrl+s": null
      }
    }
  ]
}
```

`null` 是解绑。支持和弦，如 `ctrl+k ctrl+s`，间隔不超过 3 秒。上下文有 `Global`、`Chat`、`Autocomplete`、`Confirmation`、`HistorySearch`、`Task`、`Select`、`Scroll`、`Agents` 等约 30 个。

不能改的键：Ctrl+C、Ctrl+D、Ctrl+M、Ctrl+[、Ctrl+I、Ctrl+H、Caps Lock。

默认动作举例：`chat:cycleMode`（Shift+Tab）、`app:toggleTranscript`（Ctrl+O）、`history:search`（Ctrl+R）、`chat:stash`（Ctrl+S）、`chat:modelPicker`（Meta+P）、`chat:thinkingToggle`（Meta+T）、`chat:externalEditor`（Ctrl+G）。

## 输出风格

文档：<https://code.claude.com/docs/en/output-styles>

`outputStyle` 区分大小写。内置是 `Default`、`Proactive`、`Concise`、`Explanatory`、`Learning`。写成 `explanatory` 会退回 Default。`/output-style` 切换，需要 v2.1.269+。

自定义文件：`~/.claude/output-styles/`、项目 `.claude/output-styles/`（从工作目录向上到仓库根逐级加载）、托管目录下的 `.claude/output-styles/`。frontmatter 有 `name`、`description`、`keep-coding-instructions`（默认 false）、`force-for-plugin`（仅插件）。

风格只是指令，不保证行为。要保证就用 hook。`/config` 里选的风格写进 `.claude/settings.local.json`。

## 状态栏

文档：<https://code.claude.com/docs/en/statusline>

```json
{
  "statusLine": {
    "type": "command",
    "command": "你的脚本",
    "padding": 2,
    "refreshInterval": 5
  }
}
```

脚本从 stdin 读 JSON。常用字段：`model.id`、`model.display_name`、`cwd`、`workspace.current_dir`、`workspace.project_dir`、`workspace.git_worktree`、`workspace.repo`、`cost.total_cost_usd`、`cost.total_duration_ms`、`cost.total_lines_added`、`context_window.used_percentage`、`context_window.remaining_percentage`、`rate_limits.five_hour.used_percentage`、`rate_limits.seven_day.used_percentage`。

`subagentStatusLine` 改写子代理任务行。`disableAllHooks: true` 会把状态栏一起关掉。`/statusline` 可以按描述生成这个配置。

## Worktree

文档：<https://code.claude.com/docs/en/worktrees>

- `claude --worktree <名字>`（`-w`）：默认目录 `<repo>/.claude/worktrees/<名字>/`，分支 `worktree-<名字>`。
- `claude --worktree "#1234"`：从该 PR 拉取并建 worktree。
- 子代理 frontmatter 写 `isolation: worktree`，让它在独立 worktree 里改。
- 仓库根的 `.worktreeinclude` 用 gitignore 语法列出要复制进新 worktree 的被忽略文件，例如 `.env`。用 `WorktreeCreate` hook 替换了 git 逻辑之后，这个文件不生效。
- 桌面里在分支名旁选 worktree，位置和分支前缀在 Settings > Claude Code。

## 定时任务

文档：<https://code.claude.com/docs/en/scheduled-tasks>、<https://code.claude.com/docs/en/routines>

- `/loop [间隔] [提示词]`：会话内重复执行。不给间隔时由 Claude 定，1 分钟到 1 小时。不给提示词时用内置维护提示，或 `loop.md`。
- `loop.md` 放 `.claude/loop.md`（优先）或 `~/.claude/loop.md`，超过 25000 字节会截断。
- 一次性提醒直接说，如「下午 3 点提醒我推送」。
- 工具是 `CronCreate`、`CronList`、`CronDelete`。每会话最多 50 个。周期性任务 7 天后过期。
- 只在 Claude Code 开着且空闲时触发。`CLAUDE_CODE_DISABLE_CRON=1` 关掉调度器。
- 云端 routines（`/schedule`）最小间隔 1 小时，在云端跑，不依赖这台机器。
- 桌面的 scheduled tasks 需要本机开着，最小间隔 1 分钟。文档：<https://code.claude.com/docs/en/desktop-scheduled-tasks>

## 桌面应用的 Code 标签

文档：<https://code.claude.com/docs/en/desktop>

- Desktop 有 Chat、Cowork、Code 三个标签。Code 的每个会话有自己的历史和项目目录。
- 环境可选 Local、Cloud、SSH，Windows 上还可选 WSL 发行版。
- 和 CLI 共用同一套设置文件。`/config` 在桌面里打开的是 Settings > Claude Code，不是终端菜单。
- 模式选择器：Manual、Accept edits、Plan、Auto、Bypass permissions。`dontAsk` 只在 CLI。
- Remote Control 是会话上的开关，或 `/remote-control`。设置项 **Connect new sessions to Remote Control** 控制新会话是否自动连。`disableRemoteControl: true` 可彻底关掉。
- CLI 入口是 `claude --remote-control "名称"`（`--rc`）和 `claude remote-control`。
- 云端会话里没有 Bypass permissions、`@` 提及文件、插件浏览器。插件在 WSL 和云端会话里不可用。

文档：<https://code.claude.com/docs/en/remote-control>

## advisor 工具

文档：<https://code.claude.com/docs/en/advisor>

让 Claude 在动手前把思路交给另一个更强的模型过一遍。它注册成一个服务端工具（`type: advisor_20260301`，`name: advisor`），由 API 在服务端执行，本地不跑任何东西。用法是 `/advisor [模型]`、`--advisor <模型>`，或 settings 里的 `advisorModel`。

### 生效条件

三层条件同时满足才会真的发出 advisor 调用，缺一层就静默退化成普通对话。

1. **CLI 开关**：`/advisor` 本身受实验开关控制。不设 `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1` 时，命令直接返回 `/advisor isn't available in this environment.`；设了才返回 `Advisor set to Opus 5.5`。另外 `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` 一旦设过就关死了，`advisorModel` 开不回来；`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` 也会连坐。
2. **端点**：必须是 Anthropic Messages 协议的原生直通，且上游真的实现了 `advisor_20260301`。第三方供应商、Bedrock/Vertex/Foundry 都不行。
3. **主模型**：必须是 Claude 模型。advisor 是 Claude 协议里的服务端工具，非 Claude 的主模型即使请求里带了也会被忽略。

会话里真的调用了 advisor 时，转录显示 `Advising <模型>`，结果分三种：`Reviewed`（Ctrl+O 看建议）、`Declined`、`Unavailable (<error_code>)`。

### 为什么第三方网关用不了

以 magpie 为例（源码 `internal/gateway/advisor.go`），它的策略是「能转就转，转不了就删」：

- 只有 Anthropic 原生直通路径会处理 advisor。上游模型名要匹配 `claude-`，且 advisor 模型要能解析到同一个 provider 的同一个上游名字，否则**删掉 advisor 工具**，并把会话里那段 advisor 说明改写成 "The advisor tool is no longer available; disregard the earlier advisor instructions."
- 走翻译路径时（`/v1/messages → /v1/chat/completions` 或 `/v1/responses`），`anthropic.go` 的解析循环直接丢弃所有 `advisor_*` 类型的工具，同时改写提示词。
- 结果是：客户端以为 advisor 开着，实际请求里已经没有这个工具，模型只能自己编一句「advisor 说是 4」。

实测本机三条路由，全部不可用：

| 路由 | 实际端点 | 结果 |
|---|---|---|
| `group/claude-sonnet-4.5-latest`（kiro） | `/v1/messages` 直通，但 kiro 背后是 Kiro 自己的运行时 | 工具能过网关，上游不认，响应里没有 `server_tool_use` |
| `opendesign/claude-*` | `/v1/messages → /v1/responses` | 翻译层直接丢弃 advisor 工具 |
| `cloudpp/*` | `/v1/messages → /v1/chat/completions` | 同上，且该供应商已关闭 |

### 自己做 API 或扩展网关，可行吗

可行，而且我实测过客户端这一半是通的。

我起了一个假的 Anthropic 端点，按官方格式返回 `server_tool_use` + `advisor_tool_result`，用 `ANTHROPIC_BASE_URL` 指过去，Claude Code 原样识别并显示，返回块类型是 `{'server_tool_use': 1, 'advisor_tool_result': 1, 'text': 1}`。也就是说 **Claude Code 不校验 advisor 是谁执行的**，只要响应里按格式出现这两个块，它就当 advisor 用过了。

所以三条路都成立，成本从低到高：

- **假执行（最容易）**：网关在 `/v1/messages` 直通路径上截获 advisor 工具，自己调另一个模型（Opus、GPT、本地模型都行），把结果包成 `advisor_tool_result` 塞回响应。协议不用改，客户端也不用改。代价是它不是一个真正的「同一次推理内的服务端工具」，而是网关发起的第二次调用。
- **网关转发（中等）**：像 magpie 的 `searchReply` 那样做多轮——主模型请求里保留 advisor 工具，网关自己执行 advisor 那一轮，再把结果拼回给主模型。这需要网关同时管两段流式响应。
- **真做 API（最难）**：自己的端点要实现完整的 Messages 协议、流式事件、`server_tool_use` / `advisor_tool_result` 的块结构，以及 `advisor_redacted_result`（Opus 5.5 的加密结果）。工作量等于做一个兼容 Anthropic Messages 的服务。

要注意的坑：

- CLI 侧仍要 `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1`，这是本地开关，跟端点无关。
- 主模型最好仍是 Claude 名字。实测把主模型设成 `deepseek/deepseek-flash` 时，CLI 照样把 `advisor_20260301` 塞进请求，说明本地不拦；但真上游可能不认。
- advisor 模型名要能被上游解析。走网关时客户端发的是 magpie 的 id（如 `claude-opus-5-5` 或 `group/...`），网关得自己映射。
- 一旦上游返回 `Unavailable`，客户端会在会话里留下痕迹，下次不会再自动重试同一个错误。

## 环境变量

来源：[Environment variables](https://code.claude.com/docs/en/env-vars)。写在 settings 的 `env` 里会覆盖 shell 里的同名变量；标了「项目文件无效」的，从项目和本地 settings 读不到，要放 shell、用户或托管设置。

取值约定：多数开关用 `1` 开、`0` 关。少数变量任何非空值都生效，包括 `0` 和 `false`，表格里单独注明，那种要恢复就 unset。

### 认证和端点

| 变量 | 默认 | 作用 |
|---|---|---|
| `ANTHROPIC_API_KEY` | | 作为 `X-Api-Key`。交互模式批准一次后覆盖订阅登录，`-p` 总是用它 |
| `ANTHROPIC_AUTH_TOKEN` | | `Authorization: Bearer` 的值 |
| `ANTHROPIC_BASE_URL` | Anthropic 官方端点 | API 或代理地址。非官方主机默认关掉 MCP 工具搜索；v2.1.196 起，除 `api.anthropic.com` 外 Remote Control 也被关掉 |
| `ANTHROPIC_CUSTOM_HEADERS` | | 额外请求头，`Name: Value`，换行分隔。v2.1.227+ |
| `ANTHROPIC_BETAS` | | 额外的 `anthropic-beta` 值。订阅登录也能用 |
| `ANTHROPIC_PROFILE` | | 选用 `ant auth login` 存下的哪个 profile |
| `ANTHROPIC_ORGANIZATION_ID` | | Workload Identity Federation 的组织 ID |
| `ANTHROPIC_FEDERATION_RULE_ID` | | Federation 规则 ID，配 `ANTHROPIC_ORGANIZATION_ID` |
| `ANTHROPIC_WORKSPACE_ID` | | 规则跨多个 workspace 时要带 |
| `CLAUDE_CODE_OAUTH_TOKEN` | | claude.ai OAuth access token，优先于钥匙串。给 SDK 和自动化用 |
| `CLAUDE_CODE_OAUTH_REFRESH_TOKEN` | | `claude auth login` 的 refresh token，需要 `CLAUDE_CODE_OAUTH_SCOPES` |
| `CLAUDE_CODE_OAUTH_SCOPES` | | refresh token 的 scope，空格分隔 |
| `CLAUDE_CODE_CLIENT_CERT` | | mTLS 证书文件路径 |
| `CLAUDE_CODE_CLIENT_KEY` | | mTLS 私钥文件路径 |
| `CLAUDE_CODE_CLIENT_KEY_PASSPHRASE` | | 加密私钥的口令，可选 |
| `CLAUDE_CODE_CERT_STORE` | `bundled,system` | 用哪套 CA：`bundled`、`system` 或两者 |
| `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` | | `apiKeyHelper` 生成的凭证多久刷新一次 |
| `CLAUDE_CONFIG_DIR` | `~/.claude` | 配置目录。settings 里要写绝对路径。项目和本地文件无效 |
| `HTTP_PROXY` | | HTTP 代理 |
| `HTTPS_PROXY` | | HTTPS 代理 |
| `NO_PROXY` | | 绕过代理的域名和 IP |
| `CLAUDE_CODE_PROXY_RESOLVES_HOSTS` | 关 | `1`：让代理做 DNS 解析 |
| `CLAUDE_CODE_GZIP_REQUEST_BODIES` | 直连时开 | `0`：请求体不 gzip |
| `CLAUDE_CODE_PROPAGATE_TRACEPARENT` | 仅直连 Anthropic 时开 | `1`：向自定义代理也传播 W3C trace context。v2.1.152+ |

### 供应商

| 变量 | 默认 | 作用 |
|---|---|---|
| `CLAUDE_CODE_USE_ANTHROPIC_AWS` | 关 | 走 Claude Platform on AWS |
| `CLAUDE_CODE_USE_BEDROCK` | 关 | 走 Amazon Bedrock |
| `CLAUDE_CODE_USE_MANTLE` | 关 | 走 Bedrock 的 Mantle 端点 |
| `CLAUDE_CODE_USE_VERTEX` | 关 | 走 Google Cloud 的 Agent Platform |
| `CLAUDE_CODE_USE_FOUNDRY` | 关 | 走 Microsoft Foundry |
| `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST` | | 由嵌入 Claude Code 的宿主平台设置。设置后忽略用户 settings 里的供应商、端点和认证变量，也忽略托管设置里的 `model`、`fallbackModel`、`modelOverrides`。托管的 `availableModels` 仍然有效，除非宿主自己给了一份 |
| `CLAUDE_CODE_SKIP_ANTHROPIC_AWS_AUTH` | 关 | 跳过 AWS 平台的客户端签名，给自己签名的网关用 |
| `CLAUDE_CODE_SKIP_BEDROCK_AUTH` | 关 | 跳过 Bedrock 的 AWS 认证，给 LLM 网关用 |
| `CLAUDE_CODE_SKIP_MANTLE_AUTH` | 关 | 跳过 Mantle 的 AWS 认证 |
| `CLAUDE_CODE_SKIP_VERTEX_AUTH` | 关 | 跳过 Google Cloud 认证 |
| `CLAUDE_CODE_SKIP_FOUNDRY_AUTH` | 关 | 跳过 Azure 认证，保留你自己提供的 `Authorization`。设了 Foundry 的 key 或 token 时无效 |
| `CLAUDE_CODE_SKIP_AWS_CRED_CACHE` | 缓存开 | `1`：每次请求都重新解析 AWS 凭证链。v2.1.207+ |
| `CLAUDE_CODE_AWS_CHAIN_RESOLVE_TIMEOUT_MS` | 60000 | AWS 凭证链的等待时间。v2.1.207+ |
| `CLAUDE_CODE_SKIP_MODEL_ACCESS_MEMORY` | 记忆开 | `1`：Bedrock 和 Google Cloud 启动时不再记住「这个账号调不了哪些模型」，记忆最长一天。v2.1.285+ |
| `ANTHROPIC_AWS_API_KEY` | | Claude Platform on AWS 的 workspace key，优先于 SigV4 |
| `ANTHROPIC_AWS_BASE_URL` | `https://aws-external-anthropic.{region}.api.aws` | AWS 平台端点 |
| `ANTHROPIC_AWS_WORKSPACE_ID` | | AWS 平台必填，作为 `anthropic-workspace-id` |
| `ANTHROPIC_BEDROCK_BASE_URL` | | Bedrock 端点 |
| `ANTHROPIC_BEDROCK_MANTLE_BASE_URL` | | Bedrock Mantle 端点 |
| `ANTHROPIC_BEDROCK_REGION_PREFIX` | | `us`、`eu`、`apac`、`jp`、`au`、`global`。v2.1.224+ |
| `ANTHROPIC_BEDROCK_SERVICE_TIER` | | `default`、`flex`、`priority` |
| `AWS_BEARER_TOKEN_BEDROCK` | | Bedrock API key |
| `ANTHROPIC_VERTEX_BASE_URL` | | Google Cloud 端点 |
| `ANTHROPIC_VERTEX_PROJECT_ID` | | GCP 项目 ID |
| `VERTEX_REGION_CLAUDE_*` | | 按模型覆盖 Google Cloud 区域。每个模型一个变量，如 `VERTEX_REGION_CLAUDE_5_5_OPUS`、`VERTEX_REGION_CLAUDE_FABLE_5_1`、`VERTEX_REGION_CLAUDE_HAIKU_5_5`，老模型也各有一个 |
| `ANTHROPIC_FOUNDRY_API_KEY` | | Microsoft Foundry 的 key |
| `ANTHROPIC_FOUNDRY_AUTH_TOKEN` | | Foundry 的 bearer token，优先于 key 和 Azure 默认链。v2.1.203+ |
| `ANTHROPIC_FOUNDRY_BASE_URL` | | Foundry 的完整 base URL |
| `ANTHROPIC_FOUNDRY_RESOURCE` | | Foundry 资源名，不是 URL |
| `CLAUDE_CODE_DISABLE_BEDROCK_CONTENT_TYPE_DEFAULT` | 开 | `1`：不再给缺 Content-Type 的响应套默认解码。v2.1.239+ |
| `CLAUDE_CODE_DISABLE_BEDROCK_CONTENT_TYPE_GUARD` | 开 | `1`：跳过 event-stream 的 content-type 检查。v2.1.208+ |
| `CLAUDE_CODE_DISABLE_MTLS_RELOAD_ON_STALE_CONNECTION` | 开 | `1`：连接报错时不重新加载 mTLS 文件。v2.1.232+ |
| `CLAUDE_CODE_GATEWAY_HINT_HEADERS` | 直连开，代理和第三方关 | `1` 强制发网关提示头，`0` 任何地方都不发。v2.1.273+ |
| `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` | 关 | `1`：用网关的 `/v1/models` 填充模型菜单 |
| `CLAUDE_CODE_GATEWAY_MODEL_DISCOVERY_TIMEOUT_MS` | 3000 | 上面那次发现的超时，只接受纯数字。v2.1.269+ |

### 模型、思考、缓存

| 变量 | 默认 | 作用 |
|---|---|---|
| `ANTHROPIC_MODEL` | | 当前模型。`--model` 和 `/model` 盖过它 |
| `ANTHROPIC_DEFAULT_MODEL` | | 新会话的起始模型。v2.1.236+ |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | | `opus` 别名指向的模型。`opusplan` 在 plan 模式用它 |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | | `sonnet` 别名。`opusplan` 在 plan 模式之外用它 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | | `haiku` 别名，后台任务也用它 |
| `ANTHROPIC_DEFAULT_FABLE_MODEL` | | `fable` 别名 |
| `ANTHROPIC_DEFAULT_*_NAME` | 识别出的模型名，否则用模型 ID | 上面四个别名在模型菜单里的显示名 |
| `ANTHROPIC_DEFAULT_*_DESCRIPTION` | `Custom <家族> model` 开头 | 菜单里的描述 |
| `ANTHROPIC_DEFAULT_*_SUPPORTED_CAPABILITIES` | | 声明能力，如 `effort,thinking` |
| `ANTHROPIC_CUSTOM_MODEL_OPTION` | | 模型菜单里多加一行 |
| `ANTHROPIC_CUSTOM_MODEL_OPTION_NAME` | 识别出的模型名，否则用模型 ID | 这一行的显示名 |
| `ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION` | `Custom model (<model-id>)` | 这一行的描述 |
| `ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES` | | 这一行声明的能力 |
| `ANTHROPIC_SMALL_FAST_MODEL` | | 已弃用，改用 `ANTHROPIC_DEFAULT_HAIKU_MODEL` |
| `CLAUDE_CODE_EFFORT_LEVEL` | | `low`、`medium`、`high`、`xhigh`、`max`、`auto`。盖过 `--effort` 和 `/effort` |
| `CLAUDE_CODE_ALWAYS_ENABLE_EFFORT` | 关 | `1`：每个请求都带 `effort` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 不设，等于跟随主会话 | 子代理、队友、工作流代理的默认模型。调用时传入的模型和定义里的 `model` 优先于它。设 `inherit` 等于不设。v2.1.251 之前它会盖过那两项 |
| `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` | 关 | `1`：强制所有子代理用同一个模型。v2.1.257+ |
| `CLAUDE_EFFORT` | | Claude Code 自己设在 Bash 和 hook 子进程里，值是当时的 effort。不要自己写 |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | 按模型 | 覆盖假定的上下文窗口大小 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | 按模型；未识别的 ID 为 32000 | 输出 token 上限。未识别的 ID 封顶 128000 |
| `CLAUDE_CODE_DISABLE_1M_CONTEXT` | 开 | `1`：关掉 1M 上下文窗口 |
| `MAX_THINKING_TOKENS` | 不设：自适应模型自己决定深度 | 扩展思考的固定预算。被夹在 1024 和「最大输出 token 减 1」之间。`0` 在 Anthropic API 上关思考，但 Opus 5.5、Sonnet 5.5、Haiku 5.5 和 Fable 关不掉。自适应推理模型会忽略这个数字，除非同时设了 `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING` |
| `CLAUDE_CODE_DISABLE_THINKING` | 关 | `1`：不发送 `thinking` 参数 |
| `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING` | 关 | `1`：Opus 4.6 和 Sonnet 4.6 退回 `MAX_THINKING_TOKENS` 预算 |
| `DISABLE_INTERLEAVED_THINKING` | 关 | `1`：不发 interleaved-thinking 的 beta 头。网关不支持时用 |
| `CLAUDE_CODE_DISABLE_FAST_MODE` | 开 | `1`：禁用快速模式 |
| `CLAUDE_CODE_SKIP_FAST_MODE_NETWORK_ERRORS` | 关 | `1`：快速模式的可用性检查失败时当作可用。组织明确禁用的响应仍然生效 |
| `CLAUDE_CODE_SKIP_FAST_MODE_ORG_CHECK` | 关 | `1`：跳过客户端的快速模式检查。API 侧的组织限制仍然生效 |
| `CLAUDE_CODE_DISABLE_LEGACY_MODEL_REMAP` | 开 | `1`：不再把 Opus 4 / 4.1 重映射到新 ID |
| `CLAUDE_CODE_DISABLE_MODEL_ACCESS_FALLBACK` | 开 | `1`：请求被拒时直接失败，不在会话中途换模型。v2.1.285+ |
| `CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK` | 开 | `1`：关掉安全命中后的自动换模型 |
| `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT` | 开 | `1`：不认识的模型 ID 不做自动压缩。v2.1.223+ |
| `FALLBACK_FOR_ALL_PRIMARY_MODELS` | 关 | 任何非空值（含 `0`）都生效：没有配置 fallback 时，所有模型在反复过载后停止重试。要恢复默认就 unset。配了 fallback 链时，换模型不受它影响 |
| `CLAUDE_CODE_PROMPT_CACHE_TTL` | 5 分钟 | 主对话的缓存时长，只接受 `5m` 或 `1h`。v2.1.242+ |
| `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` | 5 分钟 | 子代理、工作流、后台任务的缓存时长。v2.1.242+ |
| `ENABLE_PROMPT_CACHING_1H` | 关 | `1`：请求 1 小时缓存。订阅用户的主对话本来就是 1 小时。上面两个变量优先于它 |
| `FORCE_PROMPT_CACHING_5M` | 关 | `1`：强制 5 分钟，压过上面全部 |
| `ENABLE_PROMPT_CACHING_1H_BEDROCK` | | 已弃用，改用 `ENABLE_PROMPT_CACHING_1H` |
| `DISABLE_PROMPT_CACHING` | 关 | `1`：所有模型都关缓存，压过按模型的设置 |
| `DISABLE_PROMPT_CACHING_FABLE` | 关 | `1`：只关 Fable |
| `DISABLE_PROMPT_CACHING_OPUS` | 关 | `1`：只关默认 Opus |
| `DISABLE_PROMPT_CACHING_SONNET` | 关 | `1`：只关默认 Sonnet |
| `DISABLE_PROMPT_CACHING_HAIKU` | 关 | `1`：只关默认 Haiku |
| `CLAUDE_CODE_EXTRA_BODY` | | JSON 对象，合并进每个请求体顶层。shell 里设的对后台会话也生效。v2.1.206+ |
| `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` | 按模型 | 不设时 Haiku 4.5、Sonnet 5、Opus 4.7 及更早用完整提示，更新的模型用精简提示。`1` 强制精简，`0`、`false`、`no`、`off` 强制完整。工具集不变 |
| `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING` | Anthropic API 开，Foundry 和网关关 | 细粒度工具流。`0` 关，`1` 强制开 |
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` | 关 | `1`：去掉 beta 头和字段，给严格的网关用 |
| `CLAUDE_CODE_DISABLE_STRUCTURED_OUTPUTS` | 关 | `1`：不发送 `output_config.format`。v2.1.288+ |
| `CLAUDE_CODE_ATTRIBUTION_HEADER` | 开 | `0`：请求里不带署名块 |

### 超时、重试、流式

| 变量 | 默认 | 作用 |
|---|---|---|
| `API_TIMEOUT_MS` | 600000（10 分钟） | API 请求超时，最大 2147483647 |
| `API_FORCE_IDLE_TIMEOUT` | 非 Anthropic 供应商开着 5 分钟空闲超时 | `0` 关掉；`1` 对所有供应商都开着 |
| `CLAUDE_CODE_MAX_RETRIES` | 10 | 重试次数。v2.1.186 起封顶 15，开了 watchdog 后这个上限取消 |
| `CLAUDE_CODE_RETRY_WATCHDOG` | 关 | `1`：无人值守会话对 429 和 529 无限重试，退避最长 5 分钟。额度耗尽的 429 立即失败。v2.1.186+ |
| `CLAUDE_CODE_RETRY_WATCHDOG_MAX_WAIT_MS` | 不限 | 单次请求花在等 429 / 529 上的最长时间，如 `1800000`。v2.1.295+ |
| `CLAUDE_CODE_OVERLOADED_RETRY_BASE_DELAY_MS` | 500 | 529 退避的起点，范围 500–32000。v2.1.292+ |
| `CLAUDE_CODE_OVERLOADED_RETRY_MAX_DELAY_MS` | 32000 | 529 退避的上限，范围 32000–64000。v2.1.296+ |
| `CLAUDE_CODE_NONSTREAMING_TIMEOUT_RETRIES` | | `0`：非流式请求第一次超时就失败。v2.1.285+ |
| `CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK` | 开 | `1`：流中断时不退回非流式 |
| `CLAUDE_CODE_CONNECT_TIMEOUT_MS` | | 已在 v2.1.186 删除，无效果。改用 `API_TIMEOUT_MS` |
| `CLAUDE_STREAM_IDLE_TIMEOUT_MS` | 按看门狗各自的默认 | 流空闲看门狗的超时。显式设置时最低 300000，字节级看门狗再封顶 30 分钟 |
| `CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS` | | 字节级看门狗的超时，夹在 10 秒到 30 分钟，优先于上一个。v2.1.210+ |
| `CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS` | | 流式请求第一个字节的期限。大请求体会额外放宽。v2.1.242+ |
| `CLAUDE_ENABLE_STREAM_WATCHDOG` | 所有供应商开 | `0` 强制关事件级看门狗，`1` 强制开 |
| `CLAUDE_ENABLE_BYTE_WATCHDOG` | 直连 Anthropic、AWS 平台和网关的流式响应开 | `1` 强制开字节级看门狗，`0` 强制关，同时关掉首字节期限 |
| `CLAUDE_ENABLE_BYTE_WATCHDOG_BEDROCK` | 关 | `1`：Bedrock 的 eventstream 响应也走字节级看门狗 |

### Bash、PowerShell、文件工具

| 变量 | 默认 | 作用 |
|---|---|---|
| `BASH_DEFAULT_TIMEOUT_MS` | 120000（2 分钟） | 前台 Bash / PowerShell 超时 |
| `BASH_MAX_TIMEOUT_MS` | 600000（10 分钟） | 模型能设定的超时上限 |
| `BASH_MAX_OUTPUT_LENGTH` | 30000 | 命令输出回读上限，最大 150000 |
| `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` | 25000 | 读文件的 token 上限 |
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` | 关 | 每条命令后回到原来的目录 |
| `CLAUDE_CODE_SHELL` | 自动检测 | Bash 工具用的 shell，只接受 bash 或 zsh 的路径。先看 `$SHELL`，否则 PATH 上先找 zsh 再找 bash |
| `CLAUDE_CODE_SHELL_PREFIX` | | 包住 Bash、hook、状态栏、stdio MCP 启动命令的前缀。PowerShell hook 不走它 |
| `CLAUDE_ENV_FILE` | | 每条 Bash 命令前先执行的脚本，用来保持虚拟环境激活。SessionStart 等 hook 也会写它 |
| `CLAUDE_CODE_GIT_BASH_PATH` | | Windows 上 `bash.exe` 的路径 |
| `CLAUDE_CODE_USE_POWERSHELL_TOOL` | Windows 无 Git Bash 时开；有 Git Bash 时 claude.ai 和 Console 账号开 | `0` 关掉。Linux、macOS、WSL 以及 Bedrock、Google Cloud、Foundry 要 `1`，且 PATH 里有 `pwsh` |
| `CLAUDE_CODE_POWERSHELL_RESPECT_EXECUTION_POLICY` | 关，进程级绕过执行策略 | `1`：遵守机器的执行策略 |
| `CLAUDE_CODE_DISABLE_WINDOWS_SHELL_LAUNCHER` | 关 | `1`：直接启动 PowerShell。v2.1.269+ |
| `CLAUDE_CODE_DISABLE_POWERSHELL_CMD_RM_DENY` | 关 | `1`：关掉 `cmd` 删除内置命令的检查。v2.1.283+ |
| `CLAUDE_CODE_BASH_EDIT_DIFF` | | `0` 不记录、`1` 总是记录 Bash 改过的文件。v2.1.269+ |
| `CLAUDE_CODE_PERFORCE_MODE` | 关 | `1`：按 Perforce 做写保护 |
| `CLAUDE_CODE_BS_AS_CTRL_BACKSPACE` | Windows 上当 Ctrl+Backspace，macOS 和 Linux 上当普通 Backspace | `0` 普通 Backspace，`1` 当 Ctrl+Backspace |
| `CLAUDE_CODE_DISABLE_INLINE_SHELL_RM_PROMPT` | 开 | `1`：不扫描 `bash -c` 脚本里的删除。v2.1.288+ |
| `CLAUDE_CODE_DISABLE_DANGEROUS_RM_TIMEOUT` | 开 | `1`：去掉关键路径确认的时限。v2.1.281+ |
| `CLAUDE_CODE_DISABLE_SUBSTITUTION_RM_PROMPT` | 开 | `1`：跳过 `rm "$(...)"` 的检查。v2.1.281+ |
| `CLAUDE_CODE_GLOB_TIMEOUT_SECONDS` | 20，WSL 上 60 | Glob 超时 |
| `CLAUDE_CODE_GLOB_HIDDEN` | 开，包含点文件 | `false`：Glob 排除点文件 |
| `CLAUDE_CODE_GLOB_NO_IGNORE` | 开，返回被 gitignore 的文件 | `false`：Glob 遵守 `.gitignore` |
| `USE_BUILTIN_RIPGREP` | 用自带的 | `0`：用系统的 `rg` |
| `CLAUDE_CODE_USE_NATIVE_FILE_SEARCH` | 关 | `1`：用 Node 文件 API 发现命令、子代理和输出风格，不用 ripgrep。不影响 Grep 工具 |
| `CLAUDE_CODE_TOOL_MEMORY_LIMIT` | | Linux / WSL：Bash 和 PowerShell 的内存上限，如 `4G`。`0` 或 `off` 关掉。改动要下次启动才生效。v2.1.233+ |
| `CLAUDE_CODE_TOOL_MEMORY_CGROUP_EXCLUDE` | | 逗号分隔，哪些进程不计入上面的上限，如 `mcp,lsp`。`none` 全算，`all-new` 只算新命令。Bash、PowerShell、Monitor 始终计入。v2.1.246+ |
| `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` | 关 | `1`：子进程环境里去掉凭证。`GITHUB_TOKEN` 和代理变量保留。GitHub Actions 配了 `allowed_non_write_users` 时自动设 |
| `CLAUDE_CODE_SCRIPT_CAPS` | | JSON，限制特定脚本每会话能跑几次，如 `{"deploy.sh": 2}`。要配合上面的 scrub |
| `CLAUDE_CODE_TMPDIR` | macOS `/tmp`，其他平台 `os.tmpdir()` | 内部临时文件目录。项目和本地文件无效。沙箱里路径太长会退回系统默认 |

### 子代理、后台任务、会话

| 变量 | 默认 | 作用 |
|---|---|---|
| `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | 20 | 同时跑的子代理数。v2.1.217+ |
| `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | 3 | 子代理嵌套深度。`1` 等于不许嵌套。v2.1.217+ |
| `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` | | 已在 v2.1.224 删除，无效果。删除前是 200 |
| `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY` | 10 | 并行的只读工具数 |
| `CLAUDE_CODE_MAX_TURNS` | | 没有 `--max-turns` 时的回合上限 |
| `CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS` | 600000（10 分钟） | 子代理卡住的判定时间 |
| `CLAUDE_AUTO_BACKGROUND_TASKS` | 关 | `1`：长任务大约两分钟后强制转后台 |
| `CLAUDE_CODE_WORKER_CHECKIN_SCHEDULE` | 不提醒 | 配合上面那个，提醒 Claude 去看还在跑的后台子代理。逗号分隔的秒数，1–86400，最后一项重复。v2.1.283+ |
| `CLAUDE_CODE_AUTO_BACKGROUND_WORKER_CHECKIN_SECONDS` | | 已在 v2.1.283 删除，改用上一个 |
| `CLAUDE_SUBAGENT_BG_SHELL_MAX_MS` | | 已在 v2.1.260 删除，无效果。删除前默认 60 分钟 |
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` | 关 | `1`：关掉全部后台任务 |
| `CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP` | 关 | `1`：内存压力下不回收后台 shell。v2.1.193+ |
| `CLAUDE_CODE_BG_TASKS_REPORT_RUNNING` | 开 | `0`：回合结束时报告空闲，而不是保持「运行中」。v2.1.269+ |
| `CLAUDE_CODE_DISABLE_BG_EXIT_HANDOFF` | 关 | `1`：监督进程重启时不交接后台工作。v2.1.196+ |
| `CLAUDE_DISABLE_ADOPT` | 关 | `1`：把会话转后台时停掉正在跑的后台工作，而不是带走。v2.1.195+ |
| `CLAUDE_CODE_DISABLE_AGENT_VIEW` | 关 | `1`：关掉后台代理和 agent 视图 |
| `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS` | 关 | `1`：去掉内置子代理，包括 `general-purpose`。只在 `-p` |
| `CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS` | 关 | `1`：只去掉内置 Explore 和 Plan。v2.1.198+ |
| `CLAUDE_CODE_FORK_SUBAGENT` | 交互会话开，`-p` 和 SDK 关 | `1` 到处开，`0` 到处关 |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | 关 | `1`：启用 agent teams |
| `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` | 16，CPU 少时更低 | 一次工作流同时跑的代理数，1–256。v2.1.269+ |
| `CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS` | 5000 | 同前缀的工作流代理错开首个请求，好命中缓存。`0` 关掉。设了 `DISABLE_PROMPT_CACHING` 时本来就不等。v2.1.229+ |
| `CLAUDE_CODE_GOAL_CHECKIN_MINUTES` | 30 | `/goal` 的检查间隔。`0` 关掉，最大 10080。v2.1.234+ |
| `CLAUDE_CODE_TEAM_TEARDOWN_PARK_TIMEOUT_MS` | 10000 | 非交互会话退出时等 agent team 拆除的时间，1000–60000，越界的值被忽略。v2.1.206+ |
| `CLAUDE_CODE_TASK_LIST_ID` | | 多个会话共用一份任务列表 |
| `TASK_MAX_OUTPUT_LENGTH` | | 已在 v2.1.277 删除，无效果 |
| `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` | 600000（10 分钟） | `-p` 结束前等后台工作的上限。`0` 一直等 |
| `CLAUDE_CODE_EXIT_AFTER_STOP_DELAY` | | 空闲后多少毫秒退出 |
| `CLAUDE_AFK_TIMEOUT_MS` | 关 | 离开多久后自动继续。v2.1.200 之前默认 60000 |
| `CLAUDE_AFK_COUNTDOWN_MS` | 20000 | 自动继续前的倒计时 |
| `CLAUDE_CODE_RESUME_INTERRUPTED_TURN` | 关 | `1`：上次会话停在半轮时自动续上。`0` 关掉 |
| `CLAUDE_CODE_RESUME_INTERRUPTED_TURN_MAX_AGE_MS` | 不限 | 上面那个的消息年龄上限，太旧就不开自动续。负数或非数字按一小时。v2.1.211+ |
| `CLAUDE_CODE_RESUME_PROMPT` | `Continue from where you left off.` | 续上时发给模型的那句话。空字符串也用默认 |
| `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` | 8 | Stop 或 SubagentStop hook 连续阻断多少次后强制结束。`0` 不封顶 |
| `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` | 1500 | SessionEnd hook 的时间预算，自动上调到 settings 里配置的最大 `timeout`，封顶 60 秒。插件 hook 的 timeout 不参与上调 |
| `CLAUDE_CODE_SKIP_PROMPT_HISTORY` | 关 | `1`：不写提示历史和 transcript。这种会话不会出现在 `--resume`、`--continue` 和上箭头历史里 |
| `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE` | 关 | `1`：嵌套时也写 transcript |
| `CLAUDE_CODE_TRANSCRIPT_LOCAL_GC` | 关 | `1`：长的 `-p` 会话在压缩后裁掉旧历史，文件超过 5 MB 才裁。settings 的 `env` 开不了它。v2.1.287+ |
| `CLAUDE_CODE_STARTUP_FAILURE_RESULTS` | 关 | `1`：`--output-format stream-json` 时，启动失败写一条结果消息而不是只有 stderr。v2.1.274+ |
| `MAX_STRUCTURED_OUTPUT_RETRIES` | 5 | `-p` 下 `--json-schema` 校验失败的重试次数，含第一次 |
| `SLASH_COMMAND_TOOL_CHAR_BUDGET` | 窗口的 1%，兜底 8000 | skill 元数据展示给模型的字符预算 |
| `CLAUDE_CODE_PROCESS_WRAPPER` | | 企业启动器的 argv 前缀。v2.1.208+ |
| `CLAUDE_CODE_PROJECT_DIR_NAME` | | `projects/` 下的目录名，配 `CLAUDE_CONFIG_DIR`。v2.1.234+ |
| `CLAUDE_CODE_DISABLE_AUTH_REFRESH_LOCK` | 关 | `1`：刷新认证时不等其他进程。v2.1.286+ |
| `CLAUDE_CODE_USER_DIALOG_TIMEOUT_MS` | 跟随 `dialogExpiry` | 转发给远程客户端的对话框期限。`0` 或负数等于没有期限。项目和本地文件无效 |
| `CLAUDE_JOB_DIR` | | Claude Code 设在后台会话里，指向 `~/.claude/jobs/<id>`。不要自己写 |
| `CLAUDE_PID` | | 子进程里 Claude Code 的进程号。v2.1.214+。不要自己写 |
| `CLAUDE_CODE_SESSION_ID` | | Bash、hook、stdio MCP 子进程里的当前会话 ID。不要自己写 |
| `CLAUDECODE` | | 子进程和 IDE 终端里由 Claude Code 设置。不要自己写 |
| `CLAUDE_CODE_CHILD_SESSION` | | 子进程里设为 `1`。v2.1.172+。不要自己写 |
| `CLAUDE_CODE_MESSAGING_SOCKET` | | 收件箱 socket 路径。v2.1.224+。不要自己写，`env` 块也写不进去 |
| `CLAUDE_CODE_MESSAGING_TOKEN` | | 会话认证 token。v2.1.228+。不要自己写 |
| `CLAUDE_CODE_BRIDGE_SESSION_ID` | | Remote Control 期间的会话 ID。v2.1.199+。不要自己写 |
| `CLAUDE_CODE_REMOTE` | | 云端会话里自动为 `true` |
| `CLAUDE_CODE_REMOTE_SESSION_ID` | | 云端会话的 ID，用来拼回会话记录的链接 |

### 压缩和记忆

| 变量 | 默认 | 作用 |
|---|---|---|
| `DISABLE_AUTO_COMPACT` | 关 | `1`：关自动压缩和空闲压缩。`/compact` 还能用。压过 `autoCompactEnabled` |
| `DISABLE_COMPACT` | 关 | `1`：自动和手动压缩都关 |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | | 按窗口的 1–100% 压缩，只能把阈值调低 |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | | 窗口大小，100000–1000000，只接受纯整数 |
| `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` | 200000 | 空闲压缩的门槛，最低 100000。v2.1.290+ |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY` | 开 | `1` 关掉自动记忆，`0` 强制打开 |
| `CLAUDE_CODE_DISABLE_CLAUDE_MDS` | 关 | `1`：不加载任何 CLAUDE.md |
| `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` | 关 | `1`：`--add-dir` 的目录也加载记忆 |
| `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` | 关 | `1`：去掉内置的 git 工作流说明和状态快照 |
| `CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING` | 关 | `1`：`/rewind` 不能恢复文件 |
| `CLAUDE_CODE_NEW_INIT` | 关 | `1`：`/init` 走交互式流程 |

### MCP、搜索、网页、产物

| 变量 | 默认 | 作用 |
|---|---|---|
| `ENABLE_TOOL_SEARCH` | 全部延迟加载；非官方 `ANTHROPIC_BASE_URL` 时改为一次性加载 | `true` 在非官方主机上也延迟。`auto` 按上下文 10% 决定，`auto:5` 改成 5%。`false` 全部一次性加载 |
| `MCP_TIMEOUT` | 30000 | 单个服务器的启动超时 |
| `MCP_TOOL_TIMEOUT` | 100000000 | 工具执行超时。HTTP 服务器另有 60 秒的单次请求限制，设到 60000 以上才抬高它 |
| `MAX_MCP_OUTPUT_TOKENS` | 25000 | 工具响应的 token 上限。超过 10000 会警告 |
| `MCP_CONNECTION_NONBLOCKING` | 不阻塞 | `0`：第一个查询前等服务器连上。`alwaysLoad: true` 的服务器不受这个影响 |
| `MCP_CONNECT_TIMEOUT_MS` | 5000 | 阻塞启动时等一批连接的时间 |
| `MCP_SERVER_CONNECTION_BATCH_SIZE` | 3 | 启动时并行连的本地 stdio 服务器数 |
| `MCP_REMOTE_SERVER_CONNECTION_BATCH_SIZE` | 20 | 并行连的远程服务器数 |
| `MCP_SDK_GENERATION` | v2 | `v1` 或 `v2`，钉住 MCP 客户端运行时。v2.1.218+ |
| `MCP_PROTOCOL_NEGOTIATION` | 不设时按文档描述的服务器探测 | `auto` 探测 HTTP、claude.ai 连接器和 stdio，`legacy` 全不探测。其他值被忽略。只在 v2 运行时。v2.1.221+ |
| `MCP_DISCOVERY_CACHE` | 关 | `1` 开发现缓存，`0` 即使灰度打开也关。v2.1.238 之前默认开 |
| `MCP_DISCOVERY_CACHE_TTL_S` | 900 | 缓存条目多久后后台刷新 |
| `MCP_DISCOVERY_CACHE_MAX_STALE_S` | 14400（4 小时） | 超过这个秒数就丢弃，启动时重连。封顶 7 天。v2.1.238 之前默认 86400 |
| `MCP_DISCOVERY_CACHE_STRIKES` | 1 | 连续几次刷新失败后丢弃。v2.1.238+ |
| `CLAUDE_CODE_MCP_ALLOWLIST_ENV` | 关 | `1`：stdio MCP 服务器只拿到最小环境 |
| `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` | 120000（2 分钟） | MCP 调用转后台的门槛。`0` 关掉。v2.1.212+ |
| `CLAUDE_CODE_MCP_STARTUP_WAIT_MS` | | `-p` 里第一回合等 MCP 服务器的时间。`0` 不等。v2.1.274+ |
| `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` | 网络服务器 300000（5 分钟），stdio 1800000（30 分钟） | 空闲超时。`0` 禁用。v2.1.187+ |
| `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` | 4096；由工具搜索加载的为 16384 | 描述长度上限。v2.1.280+ |
| `CLAUDE_AGENT_SDK_MCP_NO_PREFIX` | 关 | `1`：去掉 `mcp__<server>__` 前缀。仅 SDK |
| `ENABLE_CLAUDEAI_MCP_SERVERS` | 登录用户默认开 | `false`：不再拉取 claude.ai 的 MCP 服务器 |
| `MCP_CLIENT_SECRET` | | 预配置 OAuth 的 client secret |
| `MCP_OAUTH_CALLBACK_PORT` | | OAuth 回调的固定端口 |
| `CLAUDE_CODE_DISABLE_WEB_FETCH` | 关 | `1`：关掉 WebFetch。v2.1.285+ |
| `CLAUDE_CODE_WEBFETCH_CACHE_TTL_MS` | 900000（15 分钟） | 每个 URL 的缓存时长。只在启动时读一次，小数和其他写法保持默认。v2.1.233+ |
| `CLAUDE_CODE_WEBFETCH_DEADLINE_MS` | 300000（5 分钟） | 下载一个页面的上限，含重定向。`0` 不限。v2.1.268+ |
| `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` | 200 | 每会话 WebSearch 次数。v2.1.212+ |
| `CLAUDE_CODE_WEB_SEARCH_REFILLS_PER_HOUR` | 交互 100，`-p` 为 0 | 额度每小时回充多少次。v2.1.290+ |
| `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` | 关 | `1`：关掉 advisor 工具。`advisorModel` 开不回来 |
| `CLAUDE_CODE_ENABLE_CFC` | | `1` 或 `0`，启动时设定 Chrome 集成 |
| `CLAUDE_CODE_DISABLE_CFC_PROMPT` | 关 | `1`：去掉 Chrome 的提示段落。v2.1.257+ |
| `CLAUDE_CODE_ENABLE_TASKS` | 开，用 TaskCreate 等任务工具 | `0`：退回旧的 `TodoWrite` |
| `CLAUDE_CODE_ENABLE_TODO_TOOLS` | 关 | `1`：所有模型都启用任务工具。v2.1.233+ |
| `CLAUDE_CODE_DISABLE_CRON` | 关 | `1`：关掉定时任务调度器 |
| `CLAUDE_CODE_DISABLE_BUNDLED_SKILLS` | 关 | `1`：去掉内置 skills |
| `CLAUDE_CODE_DISABLE_POLICY_SKILLS` | 关 | `1`：不读托管的 skills 目录 |
| `CLAUDE_CODE_DISABLE_ARTIFACT` | 关 | `1`：关掉 Artifact 工具 |
| `CLAUDE_CODE_ARTIFACT_AUTO_OPEN` | 开 | `0`：发布后不自动打开 |
| `CLAUDE_CODE_ARTIFACT_COMMENTS` | 开 | `0`：不读 artifact 评论。v2.1.221+ |
| `CLAUDE_CODE_ARTIFACT_COMMENTS_AUTOREACT` | 开 | `0`：不自动回复评论。v2.1.228+ |
| `CLAUDE_CODE_ARTIFACT_PUBLISH_EDITS` | 开 | `0`：发布过程中不编辑。v2.1.300+ |
| `CLAUDE_CODE_DISABLE_FILE_MENTIONS` | 关 | `1`：`@` 提及只当路径发。v2.1.299+ |
| `CLAUDE_CODE_DISABLE_ATTACHMENTS` | 关 | `1`：`@` 提及当纯文本 |
| `CLAUDE_CODE_SYNC_SKILLS` | 关 | `1`：`-p` 里先等 claude.ai 账号的 skills 下载完再跑第一个查询。交互会话本来就会同步 |
| `CLAUDE_CODE_SYNC_SKILLS_WAIT_TIMEOUT_MS` | 5000 | 上面那个的等待上限 |
| `CLAUDE_CODE_SYNC_SKILLS_INSTALL_TIMEOUT_MS` | 30000 | 会话中途重载 skills 的超时 |
| `CLAUDE_CODE_SYNC_PLUGIN_INSTALL` | 关，插件在后台装 | `1`：`-p` 里等插件装完再跑第一个查询 |
| `CLAUDE_CODE_SYNC_PLUGIN_INSTALL_TIMEOUT_MS` | 不设则一直等 | 同步安装的超时，超时后不带插件继续并记一条错误 |

### 权限、提示建议、通知

| 变量 | 默认 | 作用 |
|---|---|---|
| `CLAUDE_CODE_ENABLE_AUTO_MODE` | 无效果 | 接受但无效果。只在 v2.1.158–v2.1.206 需要设 `1` |
| `CLAUDE_CODE_AUTO_MODE_SERVER` | | `0`：用 Claude Code 自己的分类器。不设时哪些会话问服务器，见官方说明。v2.1.271+ |
| `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION` | | `false` 关提示建议；`true` 一直开到用量上限。v2.1.238+ |
| `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY` | 关 | `1`：关会话质量调查 |
| `CLAUDE_CODE_ENABLE_FEEDBACK_SURVEY_FOR_OTEL` | 关 | `1`：Anthropic 流量被挡时把调查发到自己的 OTel |
| `CLAUDE_CODE_SEND_FEEDBACK` | | `0` 关、`1` 开 Claude 起草的反馈。`1` 不能给没有权限的账号授权 |
| `CLAUDE_CODE_DISABLE_NOTIFICATION_PRESENCE_CHECK` | 关 | `1`：人在电脑前也发桌面通知。v2.1.193+ |
| `CLAUDE_CLIENT_PRESENCE_FILE` | | 存在这个文件就抑制手机推送。v2.1.181+ |
| `CLAUDE_CODE_ENABLE_AWAY_SUMMARY` | | `0` 或 `1`，覆盖离开后的会话回顾 |
| `CLAUDE_CODE_RESTRICTED` | 关 | `1`：受限模式，等同 `--restricted`。settings 的 `env` 里无效。v2.1.248+ |
| `CLAUDE_CODE_SAFE_MODE` | 关 | `1`：安全模式，等同 `--safe-mode`。不加载 CLAUDE.md、skills、插件、hooks、MCP、自定义命令和代理、输出风格、工作流、主题、快捷键、状态栏、自动记忆。托管策略仍然生效 |
| `CLAUDE_CODE_SIMPLE` | 关 | `1`：最小系统提示，只有 Bash、读文件、改文件。等同 `--bare`。认证必须来自 `ANTHROPIC_API_KEY` 或 `--settings` 里的 `apiKeyHelper` |

### 终端和显示

| 变量 | 默认 | 作用 |
|---|---|---|
| `CLAUDE_CODE_NO_FLICKER` | 关 | `1`：全屏渲染 |
| `CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN` | 关 | `1`：用经典的主屏渲染 |
| `CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT` | 关 | `1`：全屏模式每帧重绘 |
| `CLAUDE_CODE_DISABLE_VIRTUAL_SCROLL` | 关 | `1`：渲染每一条消息 |
| `CLAUDE_CODE_DISABLE_MOUSE` | 关 | `1`：全屏模式关掉鼠标跟踪 |
| `CLAUDE_CODE_DISABLE_MOUSE_CLICKS` | 关 | `1`：保留滚轮，关掉点击。v2.1.195+ |
| `CLAUDE_CODE_SCROLL_SPEED` | | 滚轮倍率，正数，最大 20，可以是 `0.5` 这种小数。`3` 接近 vim 的一格一事件 |
| `CLAUDE_CODE_NONBLOCKING_STDOUT` | 关 | `1`：终端卡住时 Claude Code 不跟着冻住。v2.1.261+ |
| `CLAUDE_CODE_NATIVE_CURSOR` | 关 | `1`：用终端自己的光标 |
| `CLAUDE_CODE_ACCESSIBILITY` | 关 | `1`：保持原生光标可见 |
| `CLAUDE_AX_SCREEN_READER` | | `1` 开、`0` 关屏幕阅读器输出。v2.1.181+ |
| `CLAUDE_AX_PREPARK_MS` | 0 | 写入前的等待，封顶 5000。v2.1.233+ |
| `CLAUDE_AX_STARTUP_QUIET_MS` | 3000 | 启动时暂停渲染，封顶 600000。v2.1.217+ |
| `CLAUDE_CODE_HIDE_CWD` | 关 | `1`：启动 logo 里不显示目录 |
| `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` | 关 | `1`：不改终端标题，也不报状态 |
| `CLAUDE_CODE_FORCE_STRIKETHROUGH` | 关 | `1`：强制 `~~文字~~` 渲染删除线。v2.1.186+ |
| `CLAUDE_CODE_FORCE_SYNC_OUTPUT` | 关 | `1`：强制 DEC 模式 2026 同步输出 |
| `CLAUDE_CODE_FORCE_TERMINAL_IMAGES` | 关 | `1`：用 kitty 协议画图 |
| `CLAUDE_CODE_TMUX_TRUECOLOR` | `$TMUX` 存在时限 256 色 | 任何非空值（含 `0` 和 `false`）都允许 tmux 里的真彩色。要恢复 256 色就 unset |
| `FORCE_HYPERLINK` | 探测到终端支持才开 | `1` 开、`0` 关 OSC 8 超链接。按数字解析，`false` 这种字符串反而是开 |
| `CLAUDE_CODE_SYNTAX_HIGHLIGHT` | 开 | `false`：diff 里关语法高亮。代码块要用设置键 `syntaxHighlightingDisabled` |
| `IS_DEMO` | 关 | 任何非空值（含 `0`）都进入演示模式：隐藏邮箱和组织名，跳过引导。要关掉就 unset |
| `DEBUG` | 关 | `1`、`true`、`yes`、`on` 才开调试，等同 `--debug`。日志在 `~/.claude/debug/<会话>.txt`。`DEBUG=express:*` 这种不会触发 |

### 插件

| 变量 | 默认 | 作用 |
|---|---|---|
| `CLAUDE_CODE_PLUGIN_CACHE_DIR` | `~/.claude/plugins` | 插件根目录 |
| `CLAUDE_CODE_PLUGIN_DIRS` | | 额外的插件目录，`:` 或 `;` 分隔。v2.1.280+ |
| `CLAUDE_CODE_PLUGIN_DIR_WATCH` | 交互会话开，非交互关 | 文件变化时重载 mod。v2.1.287+ |
| `CLAUDE_CODE_PLUGIN_GIT_TIMEOUT_MS` | 120000 | 克隆市场的超时 |
| `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE` | 关 | `1`：刷新失败时保留已有的检出 |
| `CLAUDE_CODE_PLUGIN_PREFER_HTTPS` | 关 | `1`：`owner/repo` 走 HTTPS 克隆 |
| `CLAUDE_CODE_PLUGIN_SEED_DIR` | | 只读的种子目录，`:` 或 `;` 分隔 |
| `CLAUDE_CODE_ENABLE_BACKGROUND_PLUGIN_REFRESH` | 关 | `1`：`-p` 里在回合边界刷新插件 |
| `FORCE_AUTOUPDATE_PLUGINS` | 关 | `1`：主更新器关着也强制更新插件 |
| `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL` | 关 | `1`：不自动登记官方市场 |
| `CLAUDE_CODE_PACKAGE_MANAGER_AUTO_UPDATE` | 关 | `1`：允许 Homebrew 或 WinGet 在后台升级 |

### 遥测和 OpenTelemetry

`DISABLE_TELEMETRY` 和 `DO_NOT_TRACK` 任何时候都生效。打开导出、选择目的地、采集内容的变量，项目和本地 settings 里无效，要放 shell、用户或托管设置。`OTEL_RESOURCE_ATTRIBUTES` 和导出间隔、超时、压缩这些仍然从项目文件生效。

| 变量 | 默认 | 作用 |
|---|---|---|
| `DISABLE_TELEMETRY` | 开 | 任何非空值（含 `0` 和 `false`）都退出遥测，同时停掉 feature flag 拉取。要恢复就 unset |
| `DO_NOT_TRACK` | 开 | `1` 等同 `DISABLE_TELEMETRY`。这个按标准布尔读，`0` 不会退出 |
| `DISABLE_ERROR_REPORTING` | 开 | 任何非空值（含 `0`）都退出错误上报。要恢复就 unset |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | 关 | 任何非空值都关掉非必要流量和 feature flag 拉取。要恢复就 unset |
| `DISABLE_GROWTHBOOK` | 开 | `1` 或 `true`：不拉 feature flag，全部用代码默认值。`0` 不影响。Remote Control 等依赖 flag 的功能会不可用 |
| `CLAUDE_CODE_ENABLE_TELEMETRY` | 关 | `1`：打开 OpenTelemetry |
| `BETA_TRACING_ENDPOINT` | | beta tracing 的 OTLP/HTTP 端点 |
| `ENABLE_BETA_TRACING_DETAILED` | 关 | `1` 且设了上一个：打开带内容的详细 tracing。项目和本地文件无效 |
| `CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH` | 61440 | 属性长度上限，单位是 UTF-16。v2.1.214+ |
| `CLAUDE_CODE_OTEL_DIAG_STDERR` | 关 | `1`：导出错误打到 stderr。否则只在 `--debug` 时出现。v2.1.179+ |
| `CLAUDE_CODE_OTEL_FLUSH_TIMEOUT_MS` | 5000 | span 刷出超时 |
| `CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS` | 1740000（29 分钟） | 请求头刷新间隔 |
| `CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS` | 2000 | 导出器关闭超时 |
| `CLAUDE_CODE_DEBUG_LOGS_DIR` | `~/.claude/debug/<会话>.txt` | 调试日志路径。只设它不开启日志 |
| `CLAUDE_CODE_DEBUG_LOG_LEVEL` | `debug` | `verbose`、`debug`、`info`、`warn`、`error` |
| `OTEL_LOG_USER_PROMPTS` | 关，提示词打码 | `1`：trace 和日志里包含用户提示词 |
| `OTEL_LOG_ASSISTANT_RESPONSES` | 跟随上一个 | `1`：包含模型回复。不设时跟随 `OTEL_LOG_USER_PROMPTS`。`0` 即使那个开着也打码。v2.1.193+ |
| `OTEL_LOG_TOOL_DETAILS` | 关 | `1`：包含工具参数、MCP 服务器名、原始错误等 |
| `OTEL_LOG_TOOL_CONTENT` | 关 | `1`：span 事件里包含工具输出。需要 tracing |
| `OTEL_LOG_RAW_API_BODIES` | 关 | `1`：内联请求和响应 JSON，按内容上限截断。`file:<目录>`：完整写到磁盘。内容是整段对话 |
| `OTEL_LOG_MANAGED_SETTINGS` | 关 | `1`：日志里带打码后的托管设置和原文的 SHA-256。v2.1.274+ |
| `OTEL_METRICS_INCLUDE_ACCOUNT_UUID` | 包含 | `false`：指标里去掉账号 UUID |
| `OTEL_METRICS_INCLUDE_SESSION_ID` | 包含 | `false`：去掉会话 ID |
| `OTEL_METRICS_INCLUDE_VERSION` | 不带 | `true`：带上 Claude Code 版本 |
| `OTEL_METRICS_INCLUDE_ENTRYPOINT` | 不带 | `true`：带上会话入口。v2.1.152 加入 |
| `OTEL_METRICS_INCLUDE_REPOSITORY` | 不带 | `true`：带 `vcs.*` 仓库属性。v2.1.269+ |
| `OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES` | 附带 | `false`：指标标签不附带 `OTEL_RESOURCE_ATTRIBUTES`。v2.1.161 起附带 |
| `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` | | 标准 OTel 的属性长度限制。Claude Code 取它和 `CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH` 的较小值 |

标准 OTel 导出变量同样生效：`OTEL_METRICS_EXPORTER`、`OTEL_LOGS_EXPORTER`、`OTEL_EXPORTER_OTLP_ENDPOINT`、`OTEL_EXPORTER_OTLP_PROTOCOL`、`OTEL_EXPORTER_OTLP_HEADERS`、`OTEL_METRIC_EXPORT_INTERVAL`、`OTEL_RESOURCE_ATTRIBUTES`，以及按信号拆分的变体。配置见 [Monitoring](https://code.claude.com/docs/en/monitoring-usage)。

### 更新和隐藏命令

| 变量 | 默认 | 作用 |
|---|---|---|
| `DISABLE_AUTOUPDATER` | 关 | `1`：关后台自动更新。`claude update` 还能用 |
| `DISABLE_UPDATES` | 关 | `1`：连手动 `claude update` 和 `claude install` 都禁。比上一个更严 |
| `DISABLE_UPGRADE_COMMAND` | 关 | `1`：隐藏 `/upgrade` |
| `DISABLE_DOCTOR_COMMAND` | 关 | `1`：隐藏 `/doctor` 和 `/checkup`。不影响终端里的 `claude doctor` |
| `DISABLE_LOGIN_COMMAND` | 关 | `1`：隐藏 `/login`。认证在外部处理时用 |
| `DISABLE_LOGOUT_COMMAND` | 关 | `1`：隐藏 `/logout` |
| `DISABLE_FEEDBACK_COMMAND` | 关 | `1`：关掉 `/feedback`、`/bug`、`/share`。旧名 `DISABLE_BUG_COMMAND` 也认 |
| `DISABLE_EXTRA_USAGE_COMMAND` | 关 | `1`：隐藏 `/usage-credits` |
| `DISABLE_INSTALL_GITHUB_APP_COMMAND` | 关 | `1`：隐藏 `/install-github-app`。第三方供应商本来就隐藏 |
| `DISABLE_COST_WARNINGS` | 关 | `1`：不显示费用警告 |
| `DISABLE_INSTALLATION_CHECKS` | 关 | `1`：不显示安装位置警告 |

### IDE、云端、Remote Control

| 变量 | 默认 | 作用 |
|---|---|---|
| `CLAUDE_CODE_IDE_HOST_OVERRIDE` | 自动探测 | IDE 宿主地址 |
| `CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL` | 关 | `1`：不自动装 IDE 扩展 |
| `CLAUDE_CODE_IDE_SKIP_VALID_CHECK` | 关 | `1`：跳过 lockfile 校验 |
| `CLAUDE_CODE_AUTO_CONNECT_IDE` | 在支持的 IDE 终端里开 | 在 `autoConnectIde` 设置之前读取。`false` 关，`true` 强制开 |
| `CCR_FORCE_BUNDLE` | 关 | `1`：`claude --cloud` 强制上传本地仓库 |
| `CLAUDE_REMOTE_CONTROL_SESSION_NAME_PREFIX` | 主机名 | 自动生成的 Remote Control 会话名前缀，拼出 `myhost-graceful-unicorn` 这样的名字 |
| `CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS` | 关 | `1`：输出里加 `session_state_changed` 消息 |
| `CLAUDE_CODE_FORWARD_SUBAGENT_TEXT` | 关 | `1`：`stream-json` 里带上子代理的文本。v2.1.211+ |
| `CLAUDE_CODE_YOU_SHOULD_KNOW_DEBUG` | 关 | `1`：提示符上方显示 You should know 模块最近三次检查。v2.1.287+ |

关掉 feature flag 拉取（`DISABLE_TELEMETRY`、`DO_NOT_TRACK`、`DISABLE_GROWTHBOOK`、`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`，或走第三方供应商）之后，这些功能不可用：Remote Control、跨机器的会话消息、`/import`、`/skill-doctor`、从 claude.ai 同步 skills 和插件、advisor 工具、artifact 评论、空闲时的自动压缩。同一台机器上的会话互发消息不受影响。

已删除、现在无效果的：`CLAUDE_CODE_ENABLE_OPUS_4_7_FAST_MODE`（v2.1.142）、`CLAUDE_CODE_OPUS_4_6_FAST_MODE_OVERRIDE`（v2.1.160）。

## 本机当前配置

对照 `~/.claude/settings.json`。值里的凭证没有写入本文。

- `model`、`modelPicker`（自定义了一组模型）、`advisorModel: opus`、`language: Chinese`、`theme: dark`、`verbose: false`
- `autoCompactWindow: 272000`，另有按模型的 `modelSettings`
- `includeCoAuthoredBy: false`、`enableWorkflows: true`、`skipDangerousModePermissionPrompt: true`
- `hooks.PreToolUse` 匹配 `Bash`，跑 `rtk hook claude`
- `statusLine` 接到 claude-hud 插件，`refreshInterval: 5`
- `enabledPlugins`：`claude-hud@claude-hud`、`claude-md-management@claude-plugins-official`、`code-simplifier@claude-plugins-official`、`document-skills@anthropic-agent-skills`、`example-skills@anthropic-agent-skills`、`jdtls-lsp@claude-plugins-official`
- `extraKnownMarketplaces` 登记了 `claude-hud`
- `pluginConfigs` 里 `ecc@ecc` 的 `hooks_enabled: true`、`hook_profile: standard`
- `env` 里有代理、`ANTHROPIC_BASE_URL`、各档默认模型别名、`CLAUDE_CODE_MAX_CONTEXT_TOKENS`、`ENABLE_TOOL_SEARCH`、`DISABLE_ERROR_REPORTING`。其中 `ANTHROPIC_SMALL_FAST_MODEL` 官方已弃用
- 用户级文件：`~/.claude/CLAUDE.md`、`~/.claude/rules/ecc/`、skills（`correction-log`、`find-skills`、`frontend-design`、`manage-skills`、`obsidian-vault`）、用户 MCP `iphone_use`
- 没有 `~/.claude/keybindings.json`，没有 `~/.claude/agents`，没有定时任务目录

## 参考

- 设置文件和优先级：<https://code.claude.com/docs/en/settings>
- 全部设置键：<https://code.claude.com/docs/en/settings-reference>
- 命令：<https://code.claude.com/docs/en/commands>
- CLI：<https://code.claude.com/docs/en/cli-reference>
- Hooks：<https://code.claude.com/docs/en/hooks>
- MCP：<https://code.claude.com/docs/en/mcp>
- 记忆：<https://code.claude.com/docs/en/memory>
- Skills：<https://code.claude.com/docs/en/skills>
- 子代理：<https://code.claude.com/docs/en/sub-agents>
- 插件：<https://code.claude.com/docs/en/plugins/overview>
- 权限：<https://code.claude.com/docs/en/permissions>
- 沙箱：<https://code.claude.com/docs/en/sandboxing>
- 环境变量：<https://code.claude.com/docs/en/env-vars>
- 文档地图：<https://code.claude.com/docs/llms.txt>
