// 把每次 agent 请求的完整对话落到本地，供 advisor 工具读取。
//
// magpie 的异步网关钩子（Bun）在路由前拿到客户端原始请求体（onRequest），
// 回复写完后拿到完整回复（onResponse）。两处配合解决「哪份请求属于哪个会话」：
// 回复里出现 advisor 工具调用时，把它对应的那次请求标成「待咨询」，
// advisor 工具执行时只认这个标记，不会读到别的会话。
//
// 落盘位置：<tmpdir>/magpie-advisor-ctx（macOS 上是 $TMPDIR，不是 /tmp）。
import {
  mkdirSync, writeFileSync, readdirSync, statSync, unlinkSync, chmodSync, readFileSync,
} from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

export const CAPTURE_DIR = join(tmpdir(), "magpie-advisor-ctx");
const PENDING = join(CAPTURE_DIR, "pending-advisor.json");
// 一次请求体可达 1MB，留太多会白占磁盘；advisor 只用最近这一轮。
const MAX_FILES = 8;
// 待咨询标记不做 TTL：工具侧只认「本次调用开始之后写入」的标记，读完即删，
// 上一轮残留的标记不会被误用。

try {
  mkdirSync(CAPTURE_DIR, { recursive: true, mode: 0o700 });
} catch (e) {
  console.error("[advisor-ctx] cannot create " + CAPTURE_DIR + ": " + e);
}

function writeJSON(file, value) {
  writeFileSync(file, JSON.stringify(value), { mode: 0o600 });
  try { chmodSync(file, 0o600); } catch {}
}

function prune() {
  const files = readdirSync(CAPTURE_DIR)
    .filter((f) => f.endsWith(".json") && f !== "pending-advisor.json")
    .map((f) => ({ f, t: statSync(join(CAPTURE_DIR, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  for (const old of files.slice(MAX_FILES)) {
    try { unlinkSync(join(CAPTURE_DIR, old.f)); } catch {}
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

export async function onRequest(body, ctx) {
  try {
    mkdirSync(CAPTURE_DIR, { recursive: true, mode: 0o700 });
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
      try { body = JSON.parse(readFileSync(file, "utf8")); } catch {}
    }
    // 没有这次请求的记录时，退回到按会话找最近一份。
    if (!body && session) {
      const cands = readdirSync(CAPTURE_DIR)
        .filter((f) => f.endsWith(".json") && f.includes(session))
        .map((f) => ({ f, t: statSync(join(CAPTURE_DIR, f)).mtimeMs }))
        .sort((a, b) => b.t - a.t);
      if (cands.length) {
        try { body = JSON.parse(readFileSync(join(CAPTURE_DIR, cands[0].f), "utf8")); } catch {}
      }
    }
    if (!body || !body.body) return;
    // 只存请求体本身：advisor 工具要的是 body.messages，不是捕获记录的包装。
    writeJSON(PENDING, { at: Date.now(), session, body: body.body });
  } catch (e) {
    console.error("[advisor-ctx] onResponse: " + e);
  }
}
