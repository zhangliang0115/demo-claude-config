# magpie 支持 Claude Code advisor：插件方案实测 + 上游补丁草案

结论先说：**不改 magpie 也能用，走插件已经跑通了**；改 magpie 才有的好处是「advisor 变成真正的服务端工具、不占上下文里的工具位」。两条路都写在这里。

本文所有结论都在本机（magpie 0.1.1279 / Claude Code 2.1.302 / macOS）实测过，没跑通的地方会明确标出。

---

## 一、先确认源码与上游状态

| 项目 | 值 |
|---|---|
| 本机 magpie | 0.1.1279（`/Applications/magpie.app`，构建于 2026-10-17 12:54） |
| 上游仓库 | <https://github.com/yetone/magpie>，`main` |
| advisor 相关源码 | `internal/gateway/advisor.go`（6.7K）、`internal/gateway/anthropic.go`、`internal/gateway/gateway.go` |
| 与 GitHub `main` 对比 | `advisor.go`、`anthropic.go`、`search.go` 逐字节一致；`gateway.go` 只差本地少一段 `cpuProfile` 路由（本地构建差异，不影响 advisor） |

上游对 advisor 的现状，源码和 `docs/subsystems/gateway-routing.md:170` 写得很清楚：

- 只在 **Anthropic 原生直通**（`passthrough`）路径处理 advisor。
- 上游模型名要匹配 `(?i)(?:^|[/.:-])claude-`，且 advisor 模型要能解析到**同一个 provider** 的上游名，否则删掉工具。
- 走翻译路径（`→ chat/completions`、`→ responses`）时，`parseAnthropic` 直接丢弃 `advisor_*`，并把提示词改写成 "The advisor tool is no longer available…"。
- 有一条注释点出了动机：不删的话，模型会把 `advisor()` 当自己的工具调用，Claude Code 回 "No such tool available: advisor"（JackChou on Discord）。

**上游不收 PR**（README 第 279 行：*This repository doesn't take pull requests. Only maintainers can open them.*），反馈渠道是 Discord 和 issue。所以「补丁」只能是草案，给维护者看或自己 fork。

> **实测提醒**：上游把 advisor 工具删掉后，会把提示词改写成 "The advisor tool is no longer available; disregard the earlier advisor instructions."。如果同时开着 `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1`，模型会同时看到「advisor 已不可用」和 MCP 里那个也叫 advisor 的工具，**多数时候会听前者的，拒绝调用**。用插件方案时把实验开关关掉，只走 MCP 工具（见 2.6 的实测）。

---

## 二、插件方案：已经跑通

### 2.1 关键判断：三条路都试过，只有插件工具这条路成立

| 方案 | 结果 | 原因 |
|---|---|---|
| 网关 middleware 里自己调模型，伪造 `advisor_tool_result` | **不可行** | moejs 沙箱里 `fetch`、`setTimeout` 都不存在（实测 `typeof fetch === "undefined"`），`internal/middleware/points_test.go:271` 有测试专门保证这一点；hook 限时 250ms，也放不下一次模型调用 |
| 网关 middleware 改写请求，让上游自己执行 advisor | **不可行** | middleware 只能改 body，不能改上游能力；本机上游（kiro / opendesign / cloudpp）没有一条认 `advisor_20260301` |
| **插件工具（MCP）** | **可行，已跑通** | 工具在 Bun 宿主里执行，有 `fetch`，超时 55s；Claude Code 通过 MCP 调用，magpie 转发到插件宿主 |

顺带一个实测发现：**Claude Code 客户端不校验 advisor 是谁执行的**。我起过一个假的 Anthropic 端点，按官方格式返回 `server_tool_use` + `advisor_tool_result`，CLI 原样识别（块统计 `{server_tool_use:1, advisor_tool_result:1, text:1}`）。这条对做「真 API」的人有用，但对插件方案不是必需。

### 2.2 插件是什么

`magpie-advisor/advisor-tool/` 是一个 magpie 插件，**一个条目**里有三部分：

| 部分 | 文件 | 作用 |
|---|---|---|
| 工具 | `index.js` | 以 `advisor-tool_advisor` 出现在 magpie 的 MCP 服务器上，所有 agent 都能调用 |
| 请求钩子 | `hooks.js` | 把每次请求的完整对话和本插件的 options 落到本地，供工具读取（见 2.4） |
| 设置页 | `page/` | 侧边栏 Plugins 分组里的 **Advisor** 页：选模型、改端点、看最近一次调用 |

```
advisor-tool/
├── package.json     # 一个条目声明三件事：main / magpie.hooks / magpie.page
├── index.js         # 导出 AdvisorTool，提供 tool.advisor
├── hooks.js         # 网关请求钩子：落盘对话与 options
├── context.js       # 把请求体压成 advisor 看的转录
├── config.js        # 四层配置合成；网关地址自动发现
├── resolve.js       # 端点列表与模型候选链（都不写死）
├── log.js           # ~/.config/magpie/advisor.log
├── pagedata.js      # 写 page/models.js、page/state.js 给设置页读
└── page/            # 设置页（沙箱内，只读插件目录下的静态文件）
```

插件目录里**没有** `advisor.json`。配置全部走 magpie 的插件选项（设置页或 `magpie plugin options`），端点取网关地址，模型跟随 Claude Code 的 advisor 声明——代码里没有任何写死的模型或端口。想用文件配置的话可以自己建一个 `advisor.json`（优先级低于插件选项），但不是必需。

**工具语义对齐官方 advisor**：官方 advisor 工具不带参数，模型直接调用 `advisor()`，平台把完整对话喂给 advisor，执行方塞进 `input` 的内容根本到不了它（见官方文档 "Nothing the executor puts in `input` reaches the advisor"）。这里同样把 `args` 设成空对象，不再让模型手填 question/context。

`index.js` 的核心：

```js
export const AdvisorTool = async () => ({
  tool: {
    advisor: {
      description: "Consult a stronger model … It sees the whole conversation so far …",
      args: {},                                   // 和官方一样：不带参数
      async execute() {
        const capture = await pendingCapture(Date.now());   // 钩子标记的那份请求体
        const built = prompt(capture, budget);              // 转录 + 系统提示摘录
        // 端点按 endpoints 顺序试；模型按候选链试，规则见 2.5
        for (const ep of eps) {
          for (const cand of modelChain(cfg, declared, sessionModel, await servedModels(ep))) {
            const res = await fetch(ep.url + "/v1/chat/completions", {
              method: "POST",
              headers: { "content-type": "application/json", ...(ep.key ? { authorization: "Bearer " + ep.key } : {}) },
              body: JSON.stringify({
                model: cand.model,
                messages: [
                  { role: "system", content: SYSTEM },  // 让它给建议，不要替 agent 写答案
                  { role: "user",   content: built.text },
                ],
              }),
            });
            if (res.ok) return (await res.json()).choices[0].message.content.trim();
            if (res.status !== 404) break;          // 非「不认这个模型」→ 换端点
          }
        }
        throw new Error("advisor could not reach a working endpoint/model");
      },
    },
  },
});
```

### 2.3 插件 options 怎么传到工具里

这是踩出来的坑：`magpie plugin options` 设的值，**插件的 `tool.execute` 直接拿不到**。

- `internal/plugin/host.js:1509` 构造的 `ctx` 只有 `sessionID`、`messageID`、`callID`、`agent`、`directory`、`worktree`、`abort`、`metadata`，没有 `options`。
- 文档里 `ctx.options` 是 **middleware** 的，不是插件工具的。
- 网关钩子的 ctx 里**有** `options`（`host.js` 的 `gatewayBegin`：`options: structuredClone(h.options)`）。

所以插件用钩子做一次转发：`onRequest` 每次把 `ctx.options` 和 `ctx.directory` 写到 `<tmpdir>/magpie-advisor-ctx/options.json`，工具读这个文件。这也是工具和钩子必须在**同一个插件条目**里的原因——options 是按条目存的。

工具的 `ctx` 里没有 `options` 仍然值得给上游提 issue：靠钩子转发能用，但多一次落盘，而且钩子没跑过（比如只调工具、没有请求经过）时读不到最新配置。

### 2.4 上下文怎么来的（这一步是插件方案的关键）

官方的 advisor 由 Anthropic 在同一次推理里执行，天然拿到完整对话。插件是**第二次独立请求**，默认只拿得到模型主动递给它的东西——这就是最初的上下文丢失。补的办法不是让模型手填上下文，而是从网关侧把对话捞出来：

1. **网关钩子 `hooks.js`**（magpie 的异步网关钩子，Bun 运行）在路由前拿到客户端**原始请求体**，把 `messages`、`system`、`tools` 一起落盘；同一个钩子顺手把插件 options 和 magpie 配置目录落盘，供工具读取。
2. 回复写完后钩子的 `onResponse` 检查这次回复里有没有 advisor 工具调用；有，就把**对应的那次请求**标成「待咨询」写到 `pending-advisor.json`。
3. 工具执行时只读这个标记（读完即删，且只认本次调用开始之后写入的），再用 `context.js` 压成转录。

钩子就在插件目录里（`hooks.js`），不需要单独安装。

`context.js` 做的事：

- 按字符预算（插件选项的 `budget`，默认 16000）**从最近往前**取，最近的对话优先。
- 工具调用截到 600 字、工具结果截到 1500 字，单条消息不超过预算的 1/3。
- 跳过 `thinking` / `redacted_thinking`；图片和文档只留 `[image]` / `[document]` 标记。
- 把用户消息里注入的 `<system-reminder>`（项目规则、环境说明）摘出来归到系统提示，**不当作对话**——否则一条 23k 字规则会把真正的对话挤掉（实测踩到过）。
- 去掉末尾那条「正在调用 advisor 自己」的 assistant 消息，避免重复提问。

**为什么不用「取最近一份捕获」**：这台机器上同时跑着多个会话（桌面会话、CLI 会话、子代理），它们都往同一个目录写。插件工具的 `ctx` 里 `sessionID` 是空的，MCP 请求也不带会话头（用本地探针服务实测过），所以「最近一份」会读到别人的对话——实测发生过，advisor 复述了另一个会话的内容。宁可明说没有上下文，也不能给一段张冠李戴的转录。

落盘位置是 `<tmpdir>/magpie-advisor-ctx`。注意 Bun 的 `os.tmpdir()` 在 macOS 上指 `$TMPDIR`（`/var/folders/…/T/`），**不是 `/tmp`**——一开始我在 `/tmp` 找文件，误判成钩子没运行。

### 2.5 安装与配置

```bash
magpie plugin add /Users/zhangliang/workspace/demo/demo-claude-config/magpie-advisor/advisor-tool
```

**0.2.0 起只有一个插件。** 原来是 `advisor-tool` + `ctx.hooks.ts` 两个条目，合并的原因不只是少一条：**options 按插件条目保存**，分成两个条目时，你在设置页给工具设的模型和端点，钩子那条看不到。现在 `package.json` 里同时声明 `main`（工具）、`magpie.hooks`（请求钩子）和 `magpie.page`（设置页），三者共用一份 options。

**默认零配置就能用**：插件目录里没有 `advisor.json`，什么都不用填。端点取网关地址（`MAGPIE_ADDR` → `settings.json` 的 `port` → 3425），模型跟随 Claude Code 的 advisor 声明，声明不可用时退到会话自己的模型。

配置入口，优先级从高到低：

| 来源 | 怎么改 |
|---|---|
| magpie 插件选项 | Plugins 页的 **Options**、`magpie plugin options`，或插件自带的 **Advisor** 设置页 |
| `advisor.json`（可选，默认没有） | 想用文件配置时自己在同目录建一个 |
| 环境变量 | `ADVISOR_ENDPOINT` / `ADVISOR_MODEL` / `ADVISOR_KEY` |

```bash
magpie plugin options advisor-tool '{"model":"deepseek/deepseek-v4-pro"}'
magpie plugin options advisor-tool off     # 清掉
```

空值（`""`、`[]`、`{}`）视为「没设」，不会覆盖下一层——magpie 的选项编辑器会把 package.json 里的示例整个存进来，这一点必须容忍。

#### 设置页

侧边栏 → Plugins → **Advisor**。可以改端点（一行一个，可加备用端点）、勾选是否跟随 Claude Code 的 advisor 声明、选兜底模型，并查看最近一次调用的结果：端点、实际模型、声明模型、选择原因、耗时、上下文大小。

模型选择器是自绘的：可搜索，按 provider 分组（分组名和显示名取自 `/v1/models` 的 `magpie_label` / `display_name`），每条显示上下文窗口和是否推理模型，路由组单独一组。magpie 主窗口里的那个选择器是闭包组件，沙箱页面拿不到——CSP 禁 `connect`/`frame`，bridge 只开放 options 和 `PageReads` 里的两种读（`usage:summary`、`providers:list`），没有模型列表。所以这里用同一份 `/v1/models` 数据自己画，模型名不写死。

页面只通过 `_magpie/bridge.js` 读写**本插件自己的 options**，不碰 magpie 的其他设置；保存后 magpie 会重启插件宿主，下一次咨询生效。

页面跑在 magpie 的沙箱里，连不了网络，只能读插件目录下的静态文件：模型列表写在 `page/models.js`（网关钩子每个请求顺手刷新一次，60 秒缓存；存的是完整条目 `id`/`name`/`provider`/`providerName`/`context`/`reasoning`/`group`，不是纯 id 列表），调用结果写在 `page/state.js`，都由插件自己更新。

#### 端点：不写死，可配置多个

三种写法都认，按顺序试，去重：

```json
{ "endpoint": "http://127.0.0.1:3425" }
{ "endpoints": ["http://127.0.0.1:3425", "https://backup.example.com"] }
{ "endpoints": [{ "url": "https://backup.example.com", "key": "…" }] }
```

一个端点失败时换下一个。**只有「模型不被这个上游认识」才换模型；连不上、超时、5xx、429、鉴权失败都换端点**——这类错误换个模型名也救不回来。全部试完还不行，工具报错并列出每个端点失败的原因，不会静默返回空话。

#### 模型从哪来

插件代码不写死模型。`follow: true`（默认）时，候选链按顺序：

| 顺序 | 候选 | 什么时候用 |
|---|---|---|
| 1 | `models[声明]` | 你在选项里显式写了映射 |
| 2 | `/v1/models` 里的等价名 | 上游有归一化后同名的模型（`claude-sonnet-5-5` → `opendesign/claude-sonnet-5.5`） |
| 3 | 声明原文 | 拿不到 `/v1/models`，原样试一次 |
| 4 | `model` | 配置的兜底模型 |
| 5 | 会话自己的模型 | 最后一道保险：上游一定认它 |

前三个都来自 **Claude Code 请求里 advisor 工具声明的 `model`**——也就是 `/advisor`、`--advisor`、`advisorModel` 选的那个，和官方 advisor 同一来源。实测 CLI 会把模型名**原样**发过来，包括 magpie 的 id：

```
--advisor opendesign/claude-sonnet-5.5  → 声明里就是 opendesign/claude-sonnet-5.5
--advisor claude-opus-5-5               → 声明里就是 claude-opus-5-5
```

所以多数情况不需要映射表：你在 Claude Code 里选什么，就照什么去问。只有名字对不上时才需要 `models`：

```json
{ "follow": true, "models": { "opus": "opendesign/claude-sonnet-5.5" } }
```

等价匹配只认归一化后**完全相同**的名字，不做模糊猜测——`opus` 不会匹配到 `claude-sonnet-5.5`，否则你选的模型会被悄悄换掉。

第 4、5 个候选被启用时，结果末尾会注明：

```
[advisor model "opus" is not served here; answered with deepseek/deepseek-v4-pro (the configured fallback)]
```

避免 agent 以为问的是 opus。`follow: false` 时只用 `model`，失败就报错，不偷偷换。

`model` 留空时不设兜底，直接退到会话自己的模型——这就是「不填模型还是用主模型」。要指定就填本机一定能用的模型，列表可以 `curl -s http://127.0.0.1:3425/v1/models` 看。

#### 日志

排查信息写在 **`~/.config/magpie/advisor.log`**（`XDG_CONFIG_HOME` 生效），一行一个 JSON，超过 1MB 轮转 `.1`；同时写 stderr，magpie 会收进自己的日志。

```json
{"at":"2026-10-17T17:37:14.048Z","ok":true,"endpoint":"http://127.0.0.1:3425","model":"deepseek/deepseek-v4-pro","declared":"","why":"session","ms":1955,"seen":1,"captured":true,"chars":6185,"source":"defaults"}
```

`why` 说明命中了候选链哪一环（`mapped`/`matched`/`declared`/`fallback`/`session`），`source` 说明配置来自 `options`/`advisor.json`/`env`/`defaults`。**只记这些，不记对话内容，也不记 key。**

然后在项目里给 Claude Code 挂上 MCP：

```json
// magpie-advisor/.mcp.json
{
  "mcpServers": {
    "magpie-tools": { "type": "http", "url": "http://127.0.0.1:3425/mcp/magpie/tools" }
  }
}
```

### 2.6 实测结果

从 Claude Code 里跑完整链路（`claude -p "Read README.md lines 1-15, then call the advisor-tool_advisor tool once"`），用一个记录端点截下插件实际发出的请求，内容是这样：

```
Project and system instructions (excerpt):
  You are a Claude agent, built on Anthropic's Claude Agent SDK. …

Conversation so far:

User: Read README.md lines 1-15, then call the advisor-tool_advisor tool once. Then reply DONE.

Assistant: [calls Read] {"file_path":"…/magpie-advisor/README.md","limit":15}

User: [result of call_00_ET_IffIoKzVkLouj5K6FTUA2167] 1 # magpie 支持 Claude Code advisor：插件方案实测 + 上游补丁草案 …

The agent has asked you for guidance. What should it do?
```

即：**工具调用、工具结果、用户原话都在里面**，和官方 advisor 看到的一致。换成真实模型（`deepseek/deepseek-v4-pro`）后，它能准确复述这段对话里的具体操作，证明上下文确实到了。

注意：`-p` 会报 `[claude-code:unrecognized_model]`（因为 `deepseek/deepseek-v4-pro` 不是 Claude 模型），但请求照样走通，不影响工具调用。

**模型候选链与端点故障转移的实测**（`/tmp/advtest`，假的 OpenAI 兼容端点）：

| 场景 | 结果 |
|---|---|
| 第一个端点是死端口，第二个正常 | 直接走第二个，成功 |
| 声明 `claude-sonnet-5-5`，上游只有 `opendesign/claude-sonnet-5.5` | 等价匹配命中，问的是后者 |
| 声明 `opus`，上游没有等价模型 | 依次试 `opus` → 兜底模型，成功并附注说明 |
| 上游返回 500 | 不换模型（换名字救不回来），直接报端点失败 |
| 所有端点都不通 | 报错并列出每个端点的原因，约 5 秒返回 |

从真实 Claude Code 里再跑一次（`--model deepseek/deepseek-v4-pro`，**不**开 `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL`）：模型先 `Read` 了一个文件，再空参调用 `advisor-tool_advisor`，advisor 的回复准确引用了刚读到的内容——上下文确实到了。

零配置那条路径单独验过（删掉 `advisor.json`、清空插件选项后）：

```
{"at":"2026-10-17T17:58:50.819Z","ok":true,"endpoint":"http://127.0.0.1:3425",
 "model":"deepseek/deepseek-v4-pro","declared":"","why":"session","ms":4184,
 "seen":1,"captured":true,"chars":6209,"source":"defaults"}
```

`source: defaults`、`why: session`——没配模型，直接用了会话自己的模型；端点是从 magpie 发现的网关地址。

模型选择器也单独验过（2026-10-18，真实网关、37 个模型）：按 `magpie_label` 分成「路由组 / DeepSeek / Codex / Grok (SuperGrok) / WorkBuddy / WorkBuddy AI / Open Design」七组，显示名取 `display_name`，搜索 `deepseek` 命中 6 条，选中后保存写回的是 `deepseek/deepseek-v4-pro`；配置里存着但当前列表没有的模型会单独列在「当前列表里没有」，不会被悄悄清掉。网关钩子单独跑一次请求就能重新生成 `page/models.js`（不需要 advisor 被调用）。

开了实验开关反而会失败：magpie 删掉 `advisor_20260301` 后把提示词改写成 "The advisor tool is no longer available; disregard the earlier advisor instructions."，模型看到这句就拒绝调用同名 MCP 工具。两者不要同时开。

### 2.7 和内置 advisor 的差别

| | 内置 advisor | 插件 advisor |
|---|---|---|
| 工具类型 | Anthropic 服务端工具 `advisor_20260301` | 普通 MCP 工具 |
| 工具参数 | 无 | 无（对齐） |
| 选哪个模型 | `/advisor`、`--advisor`、`advisorModel` | 同一来源（`follow: true` 读请求里的工具声明，原样用；对不上才按 `models`/等价名/兜底模型回退） |
| 端点故障转移 | 不涉及 | `endpoints` 列表按顺序试，失败换下一个 |
| 谁执行 | 上游 API，在同一次推理里 | 插件宿主，第二次独立请求 |
| 上下文 | 完整对话，平台直接给 | 网关钩子落盘的请求体，按预算截断 |
| 对上游的要求 | 必须是原生 Anthropic Messages 且支持该工具 | 无，任何 OpenAI 兼容端点都行 |
| 上下文成本 | 不占工具位 | 占一个工具位（描述约 300 字） |
| 自动性 | Claude 按提示词自行决定何时咨询 | 同样靠提示词，可在 CLAUDE.md 里加一句「重大改动前先问 advisor」 |
| 显示 | 转录里 `Advising` / `Reviewed` | 普通工具调用行 |
| 可靠性 | 平台保证 | 依赖本地钩子；钩子没跑时明说「advisor could not read the conversation」 |

---

## 三、上游补丁草案（给维护者 / 自己 fork）

如果要在 magpie 里做原生支持，最小改动是**让非 Claude 上游也能「代理执行」advisor**：网关在直通路径上截获 advisor 工具，自己发一轮请求，把结果包成 `advisor_tool_result` 注入响应。

### 3.1 改动位置

| 文件 | 改什么 |
|---|---|
| `internal/gateway/advisor.go` | 新增「代理执行」分支：不删工具，改成记录 advisor 模型，供后续注入 |
| `internal/gateway/gateway.go` | `passthrough` 里，当 advisor 被标记为代理执行时，走新的 `advisorReply` 而不是直接转发 |
| `internal/gateway/ir.go` | `Request` 增加 `Advisor *AdvisorAsk`（模型名 + 问题），或复用现有字段 |

### 3.2 核心逻辑（伪代码，Go 风格对齐现有代码）

```go
// advisor.go

// advisorProxy is an advisor the upstream can't run itself: magpie asks it
// on the same account, and answers the client with the tool's result block.
type advisorProxy struct {
    Model string // the upstream's own name for it
}

// advisorTools returns the body with the advisor tool left in, and the
// advisor to proxy when the upstream can't run one itself: a Claude model
// of another provider's, or a non-Claude model (with advisorProxyAll set).
func advisorTools(body []byte, p provider.Provider, upstream string,
    wires map[string]string) (out []byte, proxy *advisorProxy) {
    // …现有解析…
    for _, t := range list {
        if !strings.HasPrefix(typ, "advisor_") { kept = append(kept, t); continue }
        name, ok := advisorModel(p, model, wires)
        if ok {
            kept = append(kept, t) // 上游自己能跑，原样保留
            continue
        }
        // 上游跑不了：不再删除，改成由 magpie 代理
        proxy = &advisorProxy{Model: model}
        kept = append(kept, t) // 工具留在请求里，模型才会去调
    }
    // …
}
```

```go
// gateway.go，passthrough 里

case provider.Anthropic:
    var proxy *advisorProxy
    body, proxy = advisorTools(body, p, upstream, wiresOf(r.Context()))
    if proxy != nil {
        return s.advisorReply(w, r, p, proto, model, body, proxy, u)
    }
```

```go
// advisor.go，代理执行：先让主模型跑，看到 advisor 调用就替它执行，再把结果拼回去

func (s *Server) advisorReply(w http.ResponseWriter, r *http.Request, p provider.Provider,
    proto provider.Protocol, model string, body []byte, adv *advisorProxy, u *Usage) (int, string) {
    req, err := parse(proto, body)
    if err != nil { return writeError(w, proto, 400, err.Error()), err.Error() }
    // 主模型这一轮：工具照发，它可能直接调 advisor，也可能直接答
    events, status, msg := s.ask(p, model)(r.Context(), req)
    if events == nil { return writeError(w, proto, status, msg), msg }
    // 转发事件，遇到 advisor 的 tool call 就吞掉，换成 server_tool_use +
    // advisor_tool_result 两个块，再把结果作为 tool_result 喂回主模型继续
    return relayAdvisor(w, r, proto, p, req, events, adv, u)
}
```

`relayAdvisor` 的职责，逐条：

1. 把主模型的普通事件原样转发。
2. 遇到 `name == "advisor"` 的 tool call：不转发给客户端，改发
   - `content_block_start`：`{"type":"server_tool_use","id":"srvtoolu_…","name":"advisor","input":{}}`
   - `content_block_delta`：`input_json_delta`，内容是 `{"question": …}`
   - `content_block_start`：`{"type":"advisor_tool_result","tool_use_id":"srvtoolu_…","content":{"type":"advisor_result","text":…}}`
3. 用 `adv.Model` 和问题内容发一次真实请求，拿回文本填进上一步。
4. 把这次 advisor 结果作为 `tool_result` 追加到 `req.Messages`，再问主模型一轮，继续转发直到结束。
5. 轮数上限沿用 `searchRounds` 的写法，防止死循环。

现有代码里 `searchReply` / `searchRounds`（`internal/gateway/search.go:905`）就是同一套模式，可以直接参照：它把模型发起的 `web_search` 调用吞掉、自己执行、再喂回去。advisor 的差别只是要输出两种 Anthropic 专有块，而不是 `web_search_tool_result`。

### 3.3 需要顺带处理的三件事

1. **错误块**：advisor 调用失败时，按官方格式返回 `advisor_tool_result_error`，而不是让整个请求失败。
2. **`advisor_redacted_result`**：Opus 5.5 的加密结果。代理方案里 magpie 自己解密不了，只能给 `advisor_result` 明文，或者按上游返回原样透传。
3. **非 Claude 主模型**：现在是「主模型不是 Claude 就全删 advisor」。代理方案下这个限制可以放开，因为执行者是 magpie 而不是上游——但要确认 Claude Code 在非 Claude 主模型下是否仍会按提示词去调 advisor（实测 CLI 会把工具塞进请求，所以至少请求层面没问题）。

### 3.4 风险

- **两段流式拼接**：主模型流到一半要停下来等 advisor，再继续。客户端看到的是同一个响应流，中间不能断，`relay` 的 keepalive 要覆盖这段等待。
- **token 计费**：advisor 那一轮是额外的请求，`Usage` 要累加，否则用量统计会少算。
- **缓存**：advisor 结果作为 `tool_result` 追加后，主模型的 prompt cache 前缀会变，需要确认不会每轮全量重算。
- **上游兼容**：只有 Anthropic Messages 直通路径能这么干。走 Chat / Responses 翻译的请求，客户端本来就不期待 `advisor_tool_result`，硬塞会被当成未知块——所以代理只对 `from == provider.Anthropic` 生效。

---

## 四、给上游的 issue 草稿

按 magpie 现有 issue 的格式（`### Describe the feature or problem you'd like to solve` / `### Proposed solution`），三条可以分开提：

### Issue 1：插件工具的 `ctx` 缺 `options`

> **Title**: `[bug] Plugin tool's ctx has no options, so a tool can't read the plugin's settings`
>
> **Describe the feature or problem you'd like to solve**
>
> A plugin tool's `execute(args, ctx)` gets `sessionID`, `messageID`, `callID`, `agent`, `directory`, `worktree`, `abort` and `metadata` (`internal/plugin/host.js:1509`), but not the plugin's `options`. `magpie plugin options <name> '{…}'` sets them and the Plugins page shows them, and gateway middleware reads them as `ctx.options` — a tool has no way to. A tool that needs an endpoint or a model therefore has to read a file beside itself or an environment variable.
>
> **Proposed solution**
>
> Add `options` to the tool `ctx`, the same object middleware gets (the plugin entry's `options` in `plugins.json`, `{}` when none). `runTool` already knows `spec`; the entry is in `plugins.json`. Reproduced on 0.1.1279: a tool reading `ctx.options.endpoint` gets `undefined`, while the same plugin's options are visible in `magpie plugin options <name>`.

### Issue 2：插件工具的 `ctx` 缺会话标识，多会话时读不到「自己那份」对话

> **Title**: `[bug] A plugin tool can't tell which conversation called it`
>
> **Describe the feature or problem you'd like to solve**
>
> A tool's `ctx` has `sessionID: ""` and the plugin tools MCP server forwards no session header (checked by pointing an MCP client at a header-logging server: only `User-Agent`, `Accept`, `Content-Type`, `mcp-protocol-version` arrive). A tool that wants the conversation it belongs to therefore has no way to identify it. A gateway hook can capture request bodies, but with several agents on one machine — the desktop app, `claude -p`, subagents — they all land in one place, and picking "the newest" hands a tool another conversation's transcript. Reproduced on 0.1.1279: an advisor tool read a different session's transcript and answered about the wrong project.
>
> **Proposed solution**
>
> Put the gateway session on the tool `ctx` (`sessionID`), the same id `GatewayContext.Session` already carries from `sessionOf(r.Header)`, and have `/mcp/magpie/tools` pass the caller's session (the MCP request itself may not carry it, but the agent's concurrent gateway requests do — a short-lived map keyed by agent + recent activity would do). Any stable per-conversation id would let a tool match its own capture instead of guessing.

### Issue 3：advisor 在非 Claude 上游能否代理执行

> **Title**: `[feat] Advisor tool: run it for an upstream that can't, instead of dropping it`
>
> **Describe the feature or problem you'd like to solve**
>
> Claude Code's advisor (`advisor_20260301`) is left out whenever the upstream isn't a Claude model of the same provider (`advisor.go`, `advisorTools`), and on a translation it is dropped with every other server tool. On a machine whose only Claude-capable upstreams are a subscription (kiro) or a relay (opendesign, cloudpp), the advisor can never run: the tool is stripped, the instructions are rewritten to "The advisor tool is no longer available", and the model answers as if it had consulted one.
>
> **Proposed solution**
>
> On the Anthropic passthrough path, when the advisor's model can't be run by the upstream, keep the tool in the request and run the advisor from magpie: when the model calls it, answer with `server_tool_use` + `advisor_tool_result` as Anthropic does, ask the advisor model on the same account, and feed the result back as a `tool_result` for another round. This is the shape `searchReply` / `searchRounds` already have for `web_search` (`search.go:905`), with two Anthropic-only blocks instead of `web_search_tool_result`. It would also let the advisor work when the request's own model isn't Claude's, since magpie, not the upstream, runs it.
>
> Open questions: `advisor_redacted_result` (Opus 5.5's sealed result) can't be produced for another upstream, so a proxy can only give `advisor_result` plaintext; and a non-Claude main model may need a check that Claude Code still calls the tool.
>
> **Verification note**: Claude Code itself doesn't check who runs the advisor — a stand-in endpoint answering with `server_tool_use` + `advisor_tool_result` is accepted and shown as a normal advisor result (tested with 2.1.302). So the client side of this is already proven.

### Issue 4：插件页面读不到模型列表

> **Title**: `[feat] Plugin pages: a read for the model list, so a page can offer magpie's own picker`
>
> **Describe the feature or problem you'd like to solve**
>
> A plugin page runs in a frame sandboxed to `allow-scripts` with `connect-src 'none'` and `frame-src 'none'` (`pluginpage.go` `pagePolicy`), so it can't fetch `/v1/models` itself, and it can't use the window's model picker either — that one is a closure inside `app.js` (`openAgentModels`), not exposed to frames. The bridge only answers `hello`, `theme`, `options.get`, `options.set` and `read`, and `PageReads` is `usage:summary` and `providers:list` (`plugin/page.go`), neither of which carries models. A plugin that wants a model field — the advisor plugin is one — has to have its gateway hook fetch `/v1/models`, write the result to a file in its own folder, and draw its own picker from that. It works, but the list is only as fresh as the last request through the gateway (60 s cache) and the page reimplements grouping, search and labels that the window already has.
>
> **Proposed solution**
>
> Add `models:list` to `PageReads`, returning the same objects the `/v1/models` handler builds (`id`, `display_name`, `magpie_label`, `context_window`, `reasoning`, routing groups included). A page could then render the list without the file round-trip. Stretch: expose a `models.pick` message that opens the window's own picker for a frame and answers with the chosen id, which would keep the two lists identical by construction.

---

## 五、当前状态与清理

| 项 | 状态 |
|---|---|
| `magpie-advisor/advisor-tool/` | 已安装到 magpie，`on`，一个条目里同时是工具（`advisor-tool_advisor`）、网关钩子和设置页；端点列表 + 模型候选链（`resolve.js`）+ 自绘模型选择器，已实测 |
| `magpie-advisor/_old/ctx.hooks.ts` | 0.1.0 的独立钩子插件，**已从 magpie 移除**；功能并入 `advisor-tool/hooks.js`。文件挪到 `_old/` 仅作对照，可以删 |
| `magpie-advisor/.mcp.json` | 已写，供项目内 Claude Code 挂载 |
| 探针 middleware / `probe.js` | 已删除 |
| 本地 echo 服务（:3998） | 已停 |
| 插件目录里的 `advisor.json` | **已删除**；配置全走插件选项，端点/模型零配置就有默认值 |
| `advisor.log` | `~/.config/magpie/advisor.log`，一行一个 JSON，1MB 轮转 |
| 捕获目录 `<tmpdir>/magpie-advisor-ctx` | 保留最近 8 份请求体，每份 0600；可随时整目录删除 |
| Plugins 页的版本号 / 说明 | **magpie 的限制**：路径插件 `Installed()` 返回空、说明只取市场 listing，所以这两项不显示；README 已能正常读取。详见 `advisor-tool/README.md` |

要卸载（现在只有一个插件）：

```bash
magpie plugin rm /Users/zhangliang/workspace/demo/demo-claude-config/magpie-advisor/advisor-tool
rm -rf "$(getconf DARWIN_USER_TEMP_DIR)magpie-advisor-ctx"
rm -f ~/.config/magpie/advisor.log
```

---

## 六、参考

- magpie 仓库：<https://github.com/yetone/magpie>
- advisor 实现：`internal/gateway/advisor.go`，路由说明：`docs/subsystems/gateway-routing.md:170`
- middleware 限制：`docs/subsystems/gateway-middleware.md`，无网络测试：`internal/middleware/points_test.go:271`
- 插件工具：`docs/subsystems/plugin-tools.md`，`internal/plugin/host.js:1509`
- search 的多轮模式：`internal/gateway/search.go:905`（`searchReply`）、`:925`（`searchRounds`）
- Claude Code advisor 文档：<https://code.claude.com/docs/en/advisor>
