// advisor 工具（magpie 插件工具 / MCP）。
// 语义对齐 Claude Code 内置 advisor：工具本身不带参数，模型直接调用；
// advisor 拿到的是到目前为止的完整对话（含每次工具调用和结果）。
//
// 配置：magpie 插件选项 > advisor.json > 环境变量 > 默认（见 config.js）。
// 端点默认取网关地址；模型默认跟随 Claude Code 的 advisor 声明。

import { readFileSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { transcript } from "./context.js";
import { settings, CAPTURE_DIR } from "./config.js";
import { endpoints, modelChain, servedEntries } from "./resolve.js";
import { log } from "./log.js";
import { writePageModels, writePageState } from "./pagedata.js";

const SYSTEM = [
  "You are an advisor. Another agent is working on a task and has asked for your guidance.",
  "You see the conversation so far, including its tool calls and their results.",
  "Reply with concrete guidance the agent can act on: what it may have missed,",
  "the approach you would take, what to check first, and whether it should proceed.",
  "Be brief and specific. Do not restate the conversation. Do not write the final answer for the user.",
  "If there is nothing useful to add, say so plainly.",
].join(" ");

// 网关钩子落下的请求体里，最后一条 assistant 消息可能就是这次 advisor 调用
// 本身（模型已经发出 tool_use）。工具名随客户端挂载的 MCP 名而变
// （mcp__magpie-tools__advisor-tool_advisor、advisor-tool_advisor…），按子串认。
const SELF_TOOL = "advisor";

// 插件工具的硬超时是 55s（magpie internal/plugin/tools.go），
// 多端点依次重试时留 5s 余量，免得被宿主杀掉、连错误都来不及回。
const DEADLINE_MS = 50_000;

// declaredAdvisor 是请求里 advisor 工具声明的模型名（Claude Code 的叫法）。
function declaredAdvisor(body) {
  for (const t of body?.tools ?? []) {
    if (t && typeof t.type === "string" && t.type.startsWith("advisor_") && typeof t.model === "string") {
      return t.model.trim();
    }
  }
  return "";
}

// PENDING 是网关钩子写下的「这次回复里调用了 advisor」标记，里面带着
// 对应的那次请求体。插件工具的 ctx 里没有会话标识（sessionID 是空的），
// 所以不能靠「取最近一份捕获」——同一台机器上并发跑着几个会话时那样会
// 读到别人的对话（实测发生过）。
const PENDING = join(CAPTURE_DIR, "pending-advisor.json");

// pendingCapture 读这个标记，读完就删（一次一用）。
//
// 只认本次调用开始之后写入的标记：上一次 advisor 调用留下的标记还在
// 文件里，若不看时间就会把上一轮的对话当成这一轮的（实测发生过）。
// 钩子的 onResponse 是 fire-and-forget，可能比工具调用晚几百毫秒，
// 所以短暂等待新标记出现。
async function pendingCapture(startedAt, waitMs = 5000) {
  const deadline = startedAt + waitMs;
  for (;;) {
    try {
      const p = JSON.parse(readFileSync(PENDING, "utf8"));
      if (p && p.body && Number(p.at || 0) >= startedAt - 1500) {
        try { unlinkSync(PENDING); } catch (e) { /* 已被别处取走 */ }
        return p;
      }
    } catch (e) {
      // 还没有标记，或标记刚被取走
    }
    if (Date.now() >= deadline) return null;
    await new Promise((r) => setTimeout(r, 100));
  }
}

// prompt 把转录拼成一次请求。问题由模型隐含在对话里，不需要单独传。
function prompt(capture, budget) {
  const lines = [];
  if (capture?.body) {
    const t = transcript(capture.body, budget, SELF_TOOL);
    if (t.system) lines.push("Project and system instructions (excerpt):\n" + t.system);
    if (t.messages.length) {
      lines.push(
        "Conversation so far" + (t.dropped ? ` (${t.dropped} earlier messages omitted)` : "") + ":"
      );
      for (const m of t.messages) lines.push(`${m.role === "user" ? "User" : "Assistant"}: ${m.content}`);
    }
    lines.push("The agent has asked you for guidance. What should it do?");
    return { text: lines.join("\n\n"), seen: t.messages.length };
  }
  lines.push("The conversation itself could not be read. The agent asked for guidance, but no transcript is available.");
  return { text: lines.join("\n\n"), seen: 0 };
}

async function ask(ep, model, text, timeout) {
  const headers = { "content-type": "application/json" };
  if (ep.key) headers.authorization = "Bearer " + ep.key;
  const res = await fetch(ep.url + "/v1/chat/completions", {
    method: "POST",
    headers,
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: text },
      ],
    }),
    signal: AbortSignal.timeout(timeout),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    const err = new Error("advisor answered " + res.status + ": " + body.slice(0, 300));
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  const said =
    data && data.choices && data.choices[0] && data.choices[0].message
      ? data.choices[0].message.content
      : "";
  if (typeof said !== "string" || !said.trim()) throw new Error("advisor answered with nothing");
  return said.trim();
}

// modelMiss 判断这次失败是不是「这个上游不认识这个模型」。
// 是的话换候选模型；不是的话（连不上、5xx、429、鉴权）换端点。
function modelMiss(e) {
  if (e?.status === 404) return true;
  return e?.status === 400 && /model|not found|unknown/i.test(String(e.message || ""));
}

// 声明被换掉时要让 agent 知道：它以为问的是 opus，实际答的是别的模型。
const WHY_LABEL = {
  fallback: "the configured fallback",
  session: "this session's own model",
};

async function consult() {
  const o = settings();
  const startedAt = Date.now();
  const deadline = startedAt + DEADLINE_MS;
  // 端点：显式配置优先，否则用网关地址。不写死端口。
  const eps = endpoints({ ...o, endpoint: o.endpoint || o.gateway });
  if (!eps.length) throw new Error("advisor has no endpoint: set endpoints in its options, or run magpie's gateway");
  if (!o.model && !o.follow) throw new Error("advisor is not configured: set a model, or follow: true");

  // 只认钩子标记的那份。不退回「最近一份」：并发会话时会读错人的对话，
  // 宁可明说没有上下文，也不能给 advisor 一段张冠李戴的转录。
  const capture = o.context ? await pendingCapture(startedAt) : null;
  const built = prompt(capture, o.budget);
  const declared = declaredAdvisor(capture?.body);
  // 会话自己正在用的模型：上游一定认它，作为最后一个候选。
  const sessionModel = String(capture?.body?.model || "");

  const tried = [];
  for (const ep of eps) {
    if (Date.now() >= deadline) break;
    // /v1/models 用来把 claude-sonnet-5-5 认成 opendesign/claude-sonnet-5.5，
    // 拿不到就跳过等价匹配，直接按原样试。
    const served = await servedEntries(ep.url, ep.key);
    writePageModels(o.gateway, served);
    for (const cand of modelChain(o, declared, sessionModel, served.map((x) => x.id))) {
      const left = deadline - Date.now();
      if (left <= 0) break;
      const t0 = Date.now();
      try {
        const text = await ask(ep, cand.model, built.text, Math.min(o.timeout, left));
        const note =
          declared && WHY_LABEL[cand.why]
            ? `\n\n[advisor model "${declared}" is not served here; answered with ${cand.model} (${WHY_LABEL[cand.why]})]`
            : "";
        const state = {
          ok: true, endpoint: ep.url, model: cand.model, declared, why: cand.why,
          ms: Date.now() - t0, seen: built.seen, captured: Boolean(capture),
          chars: built.text.length, source: o.source,
        };
        log(state);
        writePageState(state);
        return {
          text: text + note,
          captured: Boolean(capture),
          seen: built.seen,
          model: cand.model,
          endpoint: ep.url,
        };
      } catch (e) {
        if (modelMiss(e)) {
          tried.push(`${ep.url} ${cand.model}: ${e.status}`);
          continue;
        }
        // 端点级失败（连不上、超时、5xx、429、鉴权）：换下一个端点。
        tried.push(`${ep.url}: ${e.message}`);
        break;
      }
    }
  }
  const err = "advisor could not reach a working endpoint/model: " + tried.join("; ");
  log({ ok: false, error: err, ms: Date.now() - startedAt, source: o.source });
  writePageState({ ok: false, error: err, ms: Date.now() - startedAt, source: o.source });
  throw new Error(err);
}

export const AdvisorTool = async () => ({
  tool: {
    advisor: {
      description:
        "Consult a stronger model for a second opinion at a decision point: before committing to an approach, " +
        "when an error keeps recurring, or before declaring a task done. It sees the whole conversation so far, " +
        "including tool calls and their results, so you don't need to restate anything. Returns its guidance.",
      args: {},
      async execute() {
        const out = await consult();
        // 正常情况只回 advisor 的原文，和内置 advisor 一样。
        // 拿不到转录时明说，避免让模型误以为 advisor 看过全部上下文。
        if (!out.captured) {
          return out.text + "\n\n[advisor could not read the conversation; it answered without it]";
        }
        return out.text;
      },
    },
  },
});
