# Advisor（magpie 插件）

给 Claude Code 一个 advisor 工具：模型在关键节点调用它，它拿到**到目前为止的完整对话**（含每次工具调用和结果），去问另一个模型要建议。上游不必是 Anthropic——任何 OpenAI 兼容端点都行。

版本 **0.2.0**。一个插件条目包含三部分：

| 部分 | 文件 | 作用 |
|---|---|---|
| 工具 | `index.js` | 以 `advisor-tool_advisor` 出现在 magpie 的 MCP 服务器上，所有 agent 都能调用 |
| 请求钩子 | `hooks.js` | 把每次请求的完整对话和本插件的 options 落到本地，供工具读取 |
| 设置页 | `page/` | magpie 侧边栏 Plugins 分组里的 **Advisor** 页：选模型、改端点、看最近一次调用 |

数据文件由 `pagedata.js` 写：`page/models.js`（网关地址 + `/v1/models` 的模型列表）和 `page/state.js`（最近一次调用结果）。

> 0.1.0 是两个插件（`advisor-tool` + `ctx.hooks.ts`）。合并不只是为了少一条：**options 是按插件条目保存的**，分成两个条目时，你在设置页给工具设的模型和端点，钩子那条看不到。现在两者共用一份 options。

## 安装

```bash
magpie plugin add /Users/zhangliang/workspace/demo/demo-claude-config/magpie-advisor/advisor-tool
```

装好后 `magpie plugin` 应显示：

```
<路径>  on
  async gateway hook  onRequest
  tools  advisor-tool_advisor
  page  Advisor (reads nothing)
```

然后在项目里挂上 magpie 的 MCP 服务器（`.mcp.json`）：

```json
{
  "mcpServers": {
    "magpie-tools": { "type": "http", "url": "http://127.0.0.1:3425/mcp/magpie/tools" }
  }
}
```

## 配置

**什么都不用填就能用。** 端点默认取网关地址（`MAGPIE_ADDR` → magpie 的 `settings.json` 里的 `port` → 3425），模型默认跟随 Claude Code 的 advisor 声明。

要改，三个入口，优先级从高到低：

1. **插件选项**——Plugins 页的 Options、`magpie plugin options`，或插件自带的 **Advisor** 设置页
2. **`advisor.json`**（可选，默认没有这个文件；想用文件配置时自己建）
3. **环境变量** `ADVISOR_ENDPOINT` / `ADVISOR_MODEL` / `ADVISOR_KEY`

```bash
magpie plugin options advisor-tool '{"model":"deepseek/deepseek-v4-pro"}'
magpie plugin options advisor-tool off     # 清掉
```

空值（`""`、`[]`、`{}`）视为「没设」，不会覆盖下一层的值——magpie 的选项编辑器会把 package.json 里的示例整个存进来，这一点必须容忍。

### 设置页

侧边栏 → Plugins → **Advisor**。可以：

- 改端点（一行一个，可加备用端点）；
- 勾选是否跟随 Claude Code 的 advisor 声明；
- 选兜底模型：可搜索的选择器，按 provider 分组（分组名和显示名取自 `/v1/models` 的 `magpie_label` / `display_name`），每条显示上下文窗口和是否推理模型，路由组单独一组；列表来自网关的 `/v1/models`，每个经过网关的请求都会顺手刷新一次（60 秒缓存），所以刚装好还没咨询过也有得选；
- 看最近一次调用的结果：端点、实际模型、声明模型、选择原因、耗时、上下文大小。

页面跑在 magpie 的沙箱里，连不了网络，只能读插件目录下的静态文件：模型列表写在 `page/models.js`，调用结果写在 `page/state.js`，都由插件自己更新。`models.js` 存的是完整条目（`id`、`name`、`provider`、`providerName`、`context`、`reasoning`、`group`），不是纯 id 列表。

> magpie 主窗口里那个模型选择器是闭包组件，沙箱页面拿不到（CSP 禁 `connect`/`frame`，bridge 只开放 options 和 `PageReads` 里的两种读）。所以这里自绘了一个，用的是同一份 `/v1/models` 数据，模型名不写死。

### 端点

三种写法都认，按顺序试，去重：

```json
{ "endpoint": "http://127.0.0.1:3425" }
{ "endpoints": ["http://127.0.0.1:3425", "https://backup.example.com"] }
{ "endpoints": [{ "url": "https://backup.example.com", "key": "…" }] }
```

**只有「模型不被这个上游认识」才换模型；连不上、超时、5xx、429、鉴权失败都换端点**——这类错误换个模型名也救不回来。全部试完还不行，工具报错并列出每个端点失败的原因。

### 模型

`follow: true`（默认）时的候选链：

| 顺序 | 候选 | 什么时候用 |
|---|---|---|
| 1 | `models[声明]` | 你在选项里显式写了映射 |
| 2 | `/v1/models` 里的等价名 | 归一化后同名（`claude-sonnet-5-5` → `opendesign/claude-sonnet-5.5`） |
| 3 | 声明原文 | 拿不到 `/v1/models`，原样试一次 |
| 4 | `model` | 配置的兜底模型 |
| 5 | 会话自己的模型 | 最后一道保险：上游一定认它 |

前三个都来自 Claude Code 请求里 advisor 工具声明的 `model`——也就是 `/advisor`、`--advisor`、`advisorModel` 选的那个，和官方 advisor 同一来源。CLI 会把模型名**原样**发过来，包括 magpie 的 id，所以多数情况不需要映射表。

第 4、5 个候选被启用时，结果末尾会注明换了模型，避免 agent 以为问的是原来那个。`follow: false` 时只用 `model`，失败就报错，不偷偷换。

## 排查

日志在 **`~/.config/magpie/advisor.log`**（`XDG_CONFIG_HOME` 生效），一行一个 JSON，超过 1MB 轮转一份 `.1`。同时也会写到 stderr，magpie 收进自己的日志。

```bash
tail -n 5 ~/.config/magpie/advisor.log
```

```json
{"at":"2026-10-17T17:22:15.579Z","ok":true,"endpoint":"http://127.0.0.1:3425","model":"deepseek/deepseek-v4-pro","declared":"","why":"session","ms":4235,"seen":1,"captured":true,"chars":6205,"source":"defaults"}
```

| 字段 | 含义 |
|---|---|
| `ok` | 这次咨询是否成功 |
| `endpoint` | 实际用的端点 |
| `model` / `declared` | 实际问的模型 / Claude Code 声明的模型 |
| `why` | 命中了候选链的哪一环：`mapped`、`matched`、`declared`、`fallback`、`session` |
| `ms` | 上游耗时 |
| `seen` / `chars` | 送进 advisor 的对话条数 / 字符数 |
| `captured` | 有没有读到对话（false 时工具会明说） |
| `source` | 配置来自 `options` / `advisor.json` / `env` / `defaults` |
| `error` | 失败原因，含每个端点各自的错误 |

**只记这些，不记对话内容，也不记 key。**

## 为什么列表里没有版本号和说明

`package.json` 里写了 `version` 和 `description`，但 magpie 的 Plugins 页对**从文件夹安装**的插件不显示这两项，这是 magpie 的实现决定的，不是插件漏写：

- 版本：`plugin.Installed(spec)`（`internal/plugin/market.go:665`）对路径插件直接返回 `""`，所以行上不会出现 `v0.2.0`。
- 说明：行和详情面板的摘要只取自 magpie 市场（npm）的 listing；本地文件夹没有 listing，`description` 字段不会被读。
- 详情面板里原本「无法读取该文件夹的 README」的问题已经解决——这个目录有 `README.md`，`folderReadme()` 会读它。

想要版本号显示出来，可以改用 git 仓库方式安装（`magpie plugin add github:owner/repo`），这时 `Installed()` 会读安装后 `package.json` 的 `version`；说明仍然只对市场里列出的插件生效。

## 已知限制

- **不要同时开 `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1`。** magpie 会删掉服务端的 `advisor_20260301`，并把提示词改写成 "The advisor tool is no longer available; disregard the earlier advisor instructions."，模型看到这句就拒绝调用同名的 MCP 工具（实测）。
- 插件工具的 `ctx` 里没有 `sessionID` 也没有 `options`（见 magpie issue 草案），所以：会话归属靠钩子写的「待咨询」标记（一次一用），options 靠钩子落盘转发。
- 上下文按字符预算截断（默认 16000），最近的对话优先；工具调用截 600 字、结果截 1500 字。

## 卸载

```bash
magpie plugin rm /Users/zhangliang/workspace/demo/demo-claude-config/magpie-advisor/advisor-tool
rm -rf "$(getconf DARWIN_USER_TEMP_DIR)magpie-advisor-ctx"
rm -f ~/.config/magpie/advisor.log
```
