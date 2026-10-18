// 网关钩子（magpie 的异步请求钩子，Bun 运行），和 advisor 工具在同一个插件里。
//
// 两件事：
//   1. 把每次 agent 请求的完整对话落到本地，供 advisor 工具读取；
//   2. 把用户在 magpie 里设的插件 options 落到本地，供 advisor 工具读取
//      （插件工具的 ctx 里没有 options，只有网关钩子拿得到）。
//
// 合在一个插件里的原因：options 是**按插件条目**保存的。分成两个插件时，
// 你在 Plugins 页给「advisor」设的模型和端点，钩子那个条目看不到。
//
// 落盘位置：<tmpdir>/magpie-advisor-ctx（macOS 上是 $TMPDIR，不是 /tmp）。
import {
  mkdirSync, writeFileSync, readdirSync, statSync, unlinkSync, chmodSync, readFileSync,
} from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { settings } from "./config.js";
import { endpoints, servedEntries } from "./resolve.js";
import { writePageModels } from "./pagedata.js";

const CAPTURE_DIR = join(tmpdir(), "magpie-advisor-ctx");
const PENDING = join(CAPTURE_DIR, "pending-advisor.json");
const OPTIONS = join(CAPTURE_DIR, "options.json");
// 一次请求体可达 1MB，留太多会白占磁盘；advisor 只用最近这一轮。
const MAX_FILES = 8;

function writeJSON(file, value) {
  writeFileSync(file, JSON.stringify(value), { mode: 0o600 });
  try { chmodSync(file, 0o600); } catch (e) { /* 文件系统不支持时忽略 */ }
}

function prune() {
  const files = readdirSync(CAPTURE_DIR)
    .filter((f) => f.endsWith(".json") && f !== "pending-advisor.json" && f !== "options.json")
    .map((f) => ({ f, t: statSync(join(CAPTURE_DIR, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  for (const old of files.slice(MAX_FILES)) {
    try { unlinkSync(join(CAPTURE_DIR, old.f)); } catch (e) { /* 已被别处删掉 */ }
  }
}

// advisorCalled 判断一次回复里有没有 advisor 工具调用。工具名随客户端
// 挂载的 MCP 名而变（mcp__magpie-tools__advisor-tool_advisor、
// advisor-tool_advisor…），按子串认，排除 probe 之类同名插件。
function advisorCalled(reply) {
  const blocks = reply && Array.isArray(reply.content) ? reply.content : [];
  return blocks.some((b) => {
    if (!b || b.type !== "tool_use" || typeof b.name !== "string") return false;
    const n = b.name.toLowerCase();
    return n.includes("advisor") && !n.includes("probe");
  });
}

// optionsOf 是这个插件在 magpie 里的 options。钩子的 ctx 里带着它
// （host.js 的 `options: structuredClone(h.options)`），每次请求都可能变。
function optionsOf(ctx) {
  const o = ctx && typeof ctx.options === "object" && ctx.options ? ctx.options : {};
  return o;
}

// refreshPageModels 让设置页在还没咨询过时也有模型可选。
// 工具只在被调用时写 models.js，用户刚装好插件打开设置页时是空的。
// 钩子在每个请求上跑，这里顺手取一次 /v1/models（有 60s 缓存），
// 失败了也不影响请求。
let refreshing = false;
async function refreshPageModels() {
  if (refreshing) return;
  refreshing = true;
  try {
    const o = settings();
    const eps = endpoints({ ...o, endpoint: o.endpoint || o.gateway });
    if (!eps.length) return;
    const served = await servedEntries(eps[0].url, eps[0].key);
    writePageModels(o.gateway, served);
  } catch (e) {
    // 页面数据只是辅助
  } finally {
    refreshing = false;
  }
}

export async function onRequest(body, ctx) {
  try {
    mkdirSync(CAPTURE_DIR, { recursive: true, mode: 0o700 });
    // options 先落盘：工具可能马上就被调用，晚一步就读到旧的。
    // dir 是 magpie 的配置目录（ctx.directory），工具拿它定位 settings.json
    // 和 advisor.log，便携版/XDG 也能对上。
    const options = optionsOf(ctx);
    if (Object.keys(options).length || ctx?.directory) {
      writeJSON(OPTIONS, { at: Date.now(), options, dir: ctx?.directory || "" });
    }
    const at = Date.now();
    const session = ctx?.session ?? "";
    const file = join(CAPTURE_DIR, `${at}-${session || "nosession"}.json`);
    writeJSON(file, {
      at,
      session,
      agent: ctx?.agent ?? "",
      cwd: ctx?.cwd ?? "",
      protocol: ctx?.protocol ?? "",
      model: ctx?.model ?? "",
      body,
    });
    // 同一次钩子链的 onResponse 要能找到这次请求，用 ctx.state 串起来。
    if (ctx && ctx.state && typeof ctx.state === "object") ctx.state.advisorFile = file;
    prune();
    refreshPageModels();
  } catch (e) {
    // 落盘失败不能让请求失败：钩子 fail-open
    console.error("[advisor-ctx] onRequest: " + e);
  }
  return undefined;
}

export async function onResponse(reply, ctx) {
  try {
    if (!advisorCalled(reply)) return;
    const session = ctx?.session ?? "";
    let body = null;
    const file = ctx?.state?.advisorFile;
    if (file) {
      try { body = JSON.parse(readFileSync(file, "utf8")); } catch (e) { /* 已被清理 */ }
    }
    // 没有这次请求的记录时，退回到按会话找最近一份。
    if (!body && session) {
      const cands = readdirSync(CAPTURE_DIR)
        .filter((f) => f.endsWith(".json") && f !== "options.json" && f.includes(session))
        .map((f) => ({ f, t: statSync(join(CAPTURE_DIR, f)).mtimeMs }))
        .sort((a, b) => b.t - a.t);
      if (cands.length) {
        try { body = JSON.parse(readFileSync(join(CAPTURE_DIR, cands[0].f), "utf8")); } catch (e) { /* 已被清理 */ }
      }
    }
    if (!body || !body.body) return;
    // 只存请求体本身：advisor 工具要的是 body.messages，不是捕获记录的包装。
    writeJSON(PENDING, { at: Date.now(), session, body: body.body });
  } catch (e) {
    console.error("[advisor-ctx] onResponse: " + e);
  }
}
