// 把网关钩子落下的请求体还原成 advisor 该看到的对话。
// 官方 advisor 拿到的是完整对话，包括每一次工具调用和结果；这里尽量对齐：
// 按字符预算从最近往前取，工具调用和结果截断，单条消息也有上限，
// 避免一条巨大的工具输出把整段对话挤掉。

const TOOL_USE_CAP = 600;
const TOOL_RESULT_CAP = 1500;
const SYSTEM_CAP = 6000;

// textOf 把一条消息的内容块转成文本。图片和文档只留标记：
// 它们占空间大，且 advisor 看的是文字判断。
const SYSTEM_REMINDER = /<system-reminder>([\s\S]*?)<\/system-reminder>/g;

// splitReminders 把用户消息里注入的 <system-reminder> 摘出来。
// 客户端把项目规则、目录变更、后台任务通知都塞在这种块里，它们是模型看到的
// 上下文，但不是用户说的话；混进对话会占满预算、把真正的对话挤掉。
export function splitReminders(text) {
  const reminders = [];
  const rest = String(text ?? "").replace(SYSTEM_REMINDER, (_, inner) => {
    const t = inner.trim();
    if (t) reminders.push(t);
    return "";
  });
  return { text: rest.replace(/\n{3,}/g, "\n\n").trim(), reminders };
}

function textOf(content, caps) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const out = [];
  for (const c of content) {
    if (!c || typeof c !== "object") continue;
    switch (c.type) {
      case "text":
        if (c.text) out.push(String(c.text));
        break;
      case "thinking":
      case "redacted_thinking":
        break; // 思考不转发
      case "image":
        out.push("[image]");
        break;
      case "document":
        out.push("[document]");
        break;
      case "tool_use":
        out.push(`[calls ${c.name}] ${oneLine(JSON.stringify(c.input ?? {}), caps.toolUse)}`);
        break;
      case "tool_result":
        out.push(`[result of ${c.tool_use_id ?? "tool"}] ${oneLine(textOf(c.content, caps), caps.toolResult)}`);
        break;
      default:
        break;
    }
  }
  return out.filter(Boolean).join("\n");
}

function oneLine(s, cap) {
  const t = String(s ?? "").replace(/\s+/g, " ").trim();
  return t.length > cap ? t.slice(0, cap) + "…" : t;
}

function systemText(system) {
  if (typeof system === "string") return system;
  if (!Array.isArray(system)) return "";
  return system
    .filter((b) => b && b.type === "text" && b.text)
    .map((b) => b.text)
    .join("\n\n");
}

// headTail 保留开头和结尾，中间省略：系统提示的约束常在最前和最后。
function headTail(s, cap) {
  if (s.length <= cap) return s;
  const head = Math.floor(cap * 0.6);
  const tail = cap - head;
  return s.slice(0, head) + "\n…\n" + s.slice(s.length - tail);
}

// turnTail 保留一条消息的末尾 cap 个字符：最近的结论通常在后面。
function turnTail(s, cap) {
  return s.length > cap ? "…" + s.slice(s.length - cap) : s;
}

// transcript 把一次请求体压成 {system, messages}，总字符数不超过 budget。
// 越新的消息越优先保留。skipCall 给了工具名时，末尾那条只含该工具调用的
// assistant 消息会被去掉：那是 agent 正在问 advisor 的这一次调用。
export function transcript(body, budget = 16000, skipCall = "") {
  const caps = { toolUse: TOOL_USE_CAP, toolResult: TOOL_RESULT_CAP };
  const turns = [];
  // 有的客户端把环境说明放在 messages 里 role: "system" 的消息中，而不是
  // 顶层的 system 字段；这些也是模型看到的上下文，归到系统提示里。
  const extraSystem = [];
  for (const m of body?.messages ?? []) {
    if (!m || typeof m !== "object") continue;
    if (m.role === "system") {
      const text = textOf(m.content, caps).trim();
      if (text) extraSystem.push(text);
      continue;
    }
    if (m.role !== "user" && m.role !== "assistant") continue;
    let text = textOf(m.content, caps).trim();
    if (m.role === "user") {
      const split = splitReminders(text);
      text = split.text;
      extraSystem.push(...split.reminders);
    }
    if (!text) continue;
    const last = turns[turns.length - 1];
    if (last && last.role === m.role) last.content += "\n\n" + text;
    else turns.push({ role: m.role, content: text });
  }

  if (skipCall) {
    const last = turns[turns.length - 1];
    if (last && last.role === "assistant") {
      const kept = last.content
        .split("\n")
        .filter((l) => !(l.startsWith("[calls ") && l.toLowerCase().includes(skipCall)));
      if (kept.join("").trim()) last.content = kept.join("\n");
      else turns.pop();
    }
  }

  // 单条消息不超过预算的三分之一，否则一条长输出会吃掉整段对话。
  const turnCap = Math.max(1000, Math.floor(budget / 3));
  for (const t of turns) t.content = turnTail(t.content, turnCap);

  const sys = [systemText(body?.system).trim(), ...extraSystem].filter(Boolean).join("\n\n");
  let left = Math.max(0, budget);
  const sysExcerpt = sys ? headTail(sys, Math.min(SYSTEM_CAP, Math.floor(left * 0.4))) : "";
  left -= sysExcerpt.length;

  const kept = [];
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    if (t.content.length > left) {
      if (kept.length === 0) kept.unshift({ role: t.role, content: turnTail(t.content, left) });
      break;
    }
    kept.unshift(t);
    left -= t.content.length;
  }
  return { system: sysExcerpt, messages: kept, dropped: turns.length - kept.length };
}
