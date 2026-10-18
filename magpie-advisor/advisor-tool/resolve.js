// 决定这次 advisor 问哪个端点、哪个模型。
//
// 两件事都不写死：
//   端点：endpoints 按顺序试，连不上 / 5xx / 429 换下一个；
//   模型：候选链从 Claude Code 声明的 advisor 模型出发，一路退到配置的
//        兜底模型和会话自己的模型；上游不认识某个名字时换下一个候选。
//
// 候选模型名尽量直接用 Claude Code 给的：CLI 会把 advisor 声明的 model
// 原样发过来（包括 opendesign/claude-sonnet-5.5 这种上游 id）。只有当
// 名字和端点提供的模型对不上时，才用 /v1/models 做一次等价匹配——
// claude-sonnet-5-5 与 opendesign/claude-sonnet-5.5 归一化后相同。

const MODELS_TTL = 60_000;
const MODELS_TIMEOUT = 3000;

// servedCache 缓存每个端点的 /v1/models，避免每次咨询都多打一次请求。
const servedCache = new Map();

// endpoints 把配置归一成 [{url, key}]，按顺序去重。
// 支持三种写法：
//   "endpoint": "http://…"
//   "endpoints": ["http://…", "https://…"]
//   "endpoints": [{"url": "…", "key": "…"}]
export function endpoints(o) {
  const raw = Array.isArray(o.endpoints) && o.endpoints.length ? o.endpoints : [o.endpoint];
  const out = [];
  for (const e of raw) {
    const isObj = e && typeof e === "object";
    const url = String((isObj ? e.url : e) || "").trim().replace(/\/+$/, "");
    if (!url) continue;
    if (out.some((x) => x.url === url)) continue;
    const key = isObj && e.key ? String(e.key) : String(o.key || "");
    out.push({ url, key });
  }
  return out;
}

// norm 把模型名压成可比较的形式：去掉 provider/ 前缀，只留字母数字。
// claude-sonnet-5-5、opendesign/claude-sonnet-5.5、Claude Sonnet 5.5
// 都会压成 claudesonnet55。
function norm(s) {
  return String(s || "").toLowerCase().replace(/^[^/]+\//, "").replace(/[^a-z0-9]/g, "");
}

// bestMatch 在端点提供的模型里找和 name 等价的那个。
// 只认归一化后完全相同的，不做模糊猜测：opus 不会匹配到 claude-sonnet-5.5。
export function bestMatch(name, served) {
  const raw = String(name || "").trim();
  if (!raw || !Array.isArray(served) || !served.length) return "";
  if (served.includes(raw)) return raw;
  const n = norm(raw);
  if (!n) return "";
  for (const id of served) if (norm(id) === n) return id;
  return "";
}

// servedEntries 读端点的 /v1/models，返回完整的模型条目。
//
// 只取页面和候选链都用得上的字段：id、显示名、provider、上下文窗口、
// 是否推理模型。都是上游给的，不写死任何模型名。
//
// 拿不到就返回空数组（跳过等价匹配），不让一次探测失败挡住 advisor。
export async function servedEntries(base, key) {
  const hit = servedCache.get(base);
  if (hit && Date.now() - hit.at < MODELS_TTL) return hit.entries;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), MODELS_TIMEOUT);
  try {
    const headers = {};
    if (key) headers.authorization = "Bearer " + key;
    const res = await fetch(base + "/v1/models", { headers, signal: ctrl.signal });
    if (!res.ok) return hit ? hit.entries : [];
    const data = await res.json();
    const entries = (Array.isArray(data?.data) ? data.data : [])
      .filter((m) => m && typeof m.id === "string" && m.id)
      .map((m) => {
        // magpie_label 是「显示名 · provider 名」，分组用它给出的 provider 名，
        // 和 magpie 自己的选择器一致；没有就退回 owned_by。
        const label = String(m.magpie_label || "");
        const cut = label.lastIndexOf(" · ");
        return {
          id: m.id,
          name: String(m.display_name || (cut > 0 ? label.slice(0, cut) : label) || m.id),
          provider: String(m.owned_by || ""),
          providerName: cut > 0 ? label.slice(cut + 3) : String(m.owned_by || ""),
          context: Number(m.context_window || m.context_length || m.max_input_tokens || 0) || 0,
          reasoning: Boolean(m.reasoning),
          // 路由组是 magpie 自己合成的 id（group/…），单独一组
          group: m.id.startsWith("group/"),
        };
      });
    if (entries.length) servedCache.set(base, { at: Date.now(), entries });
    return entries;
  } catch (e) {
    return hit ? hit.entries : [];
  } finally {
    clearTimeout(timer);
  }
}

// servedModels 是候选链要的模型 id 列表。
export async function servedModels(base, key) {
  const entries = await servedEntries(base, key);
  return entries.map((e) => e.id);
}

// modelChain 给出按优先级排好的模型候选。
// follow 关掉时只有配置的 model：用户要的是固定模型，失败就明说，不偷偷换。
export function modelChain(o, declared, sessionModel, served) {
  const out = [];
  const push = (m, why) => {
    const s = String(m || "").trim();
    if (!s || out.some((x) => x.model === s)) return;
    out.push({ model: s, why });
  };

  if (!o.follow) {
    push(o.model, "configured");
    return out;
  }

  if (declared) {
    // 1. 用户显式配置的映射最优先。
    if (o.models[declared]) push(o.models[declared], "mapped");
    // 2. 端点上有等价名字时用端点的写法，省一次 404。
    const matched = bestMatch(declared, served);
    if (matched) push(matched, "matched");
    // 3. 没有 /v1/models 时原样试一次。
    else push(declared, "declared");
  }
  // 4. 配置的兜底模型。
  push(o.model, "fallback");
  // 5. 会话自己正在用的模型：它一定被这个上游接受，最后再退到它。
  push(sessionModel, "session");
  return out;
}
