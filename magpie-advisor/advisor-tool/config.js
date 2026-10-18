// 配置从哪来：magpie 的插件选项 > 同目录 advisor.json > 环境变量 > 内置默认。
//
// 端点默认就是**网关地址**，不写死：先看 MAGPIE_ADDR，再看 magpie 的
// settings.json 里的 port，最后才退回 3425。
//
// 插件选项由 magpie 保存（Plugins 页的 Options、`magpie plugin options`，
// 或插件自己的页面）。插件工具的 ctx 里没有 options，所以由同一个插件的
// 网关钩子把 options 落到 OPTIONS_FILE，工具再读回来。

import { readFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const HERE = dirname(fileURLToPath(import.meta.url));
export const CAPTURE_DIR = join(tmpdir(), "magpie-advisor-ctx");
export const OPTIONS_FILE = join(CAPTURE_DIR, "options.json");
// 页面文件由 magpie 按插件目录静态提供；这两个文件由插件自己生成，
// 页面就能显示「网关实际地址、可选模型、最近一次调用结果」。
export const PAGE_DIR = join(HERE, "page");
export const MODELS_FILE = join(PAGE_DIR, "models.js");
export const STATE_FILE = join(PAGE_DIR, "state.js");

const DEFAULTS = {
  endpoints: [],      // 空 = 自动用网关地址
  follow: true,       // 跟随 Claude Code 请求里 advisor 工具声明的模型
  models: {},         // 可选的显式映射
  model: "",          // 兜底模型；空 = 不设，最后用会话自己的模型
  key: "",
  context: true,
  budget: 16000,
  timeout: 40000,
};

function readJSON(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (e) {
    return null;
  }
}

// normalizeAddr 把 MAGPIE_ADDR 的几种写法都变成 http://host:port。
// 纯数字当作端口；0.0.0.0 / :: 换成本机回环。
export function normalizeAddr(raw) {
  let s = String(raw || "").trim();
  if (!s) return "";
  if (/^\d+$/.test(s)) return "http://127.0.0.1:" + s;
  if (!s.includes("://")) s = "http://" + s;
  try {
    const u = new URL(s);
    if (u.hostname === "0.0.0.0" || u.hostname === "::") u.hostname = "127.0.0.1";
    return (u.origin + u.pathname).replace(/\/+$/, "");
  } catch (e) {
    return "";
  }
}

// configDir 是 magpie 的配置目录。插件的 ctx.directory 就是它
// （magpie 用 settings.Dir() 初始化插件宿主），所以便携版、XDG 都能对上；
// 拿不到时才按惯例推。
export function configDir(fromCtx) {
  if (fromCtx) return fromCtx;
  const base = process.env.XDG_CONFIG_HOME || join(homedir(), ".config");
  return join(base, "magpie");
}

// gatewayUrl 是 magpie 网关的地址，优先 MAGPIE_ADDR，其次 settings.json 的 port。
export function gatewayUrl(fromCtx) {
  const fromEnv = normalizeAddr(process.env.MAGPIE_ADDR);
  if (fromEnv) return fromEnv;
  const s = readJSON(join(configDir(fromCtx), "settings.json"));
  const p = Number(s?.port);
  if (Number.isInteger(p) && p >= 1024 && p <= 65535) return "http://127.0.0.1:" + p;
  return "http://127.0.0.1:3425";
}

// settings 把四层配置合成一份。后面的覆盖前面的。
// isBlank 判断一个配置值是不是「没设」：magpie 的选项编辑器会把
// package.json 里的示例整个存进来（endpoints: []、model: ""），
// 这些空值不能把 advisor.json 或环境变量里的值盖掉。
function isBlank(v) {
  if (v === undefined || v === null) return true;
  if (typeof v === "string") return v.trim() === "";
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") return Object.keys(v).length === 0;
  return false;
}

// overlay 只让**设了值**的层生效。
function overlay(base, layer) {
  const out = { ...base };
  for (const [k, v] of Object.entries(layer || {})) if (!isBlank(v)) out[k] = v;
  return out;
}

// settings 把四层配置合成一份。后面的覆盖前面的。
// fromCtx 是插件钩子的 ctx.directory（magpie 的配置目录），可选。
export function settings(fromCtx) {
  const file = readJSON(join(HERE, "advisor.json")) || {};
  const fromEnv = {};
  if (process.env.ADVISOR_ENDPOINT) fromEnv.endpoint = process.env.ADVISOR_ENDPOINT;
  if (process.env.ADVISOR_MODEL) fromEnv.model = process.env.ADVISOR_MODEL;
  if (process.env.ADVISOR_KEY) fromEnv.key = process.env.ADVISOR_KEY;
  const saved = readJSON(OPTIONS_FILE) || {};
  const opt = saved.options || {};
  // 钩子拿得到 magpie 的配置目录，工具拿不到：它把目录随 options 一起落下。
  if (!fromCtx && saved.dir) fromCtx = saved.dir;
  let o = overlay(DEFAULTS, file);
  o = overlay(o, fromEnv);
  o = overlay(o, opt);
  // follow 的默认是 true，只有显式 false 才关
  const follow = o.follow === undefined ? true : o.follow !== false;
  const num = (v, d) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : d);
  return {
    endpoints: Array.isArray(o.endpoints) ? o.endpoints : [],
    endpoint: String(o.endpoint || ""),
    gateway: gatewayUrl(fromCtx),
    follow,
    models: o.models && typeof o.models === "object" ? o.models : {},
    model: String(o.model || ""),
    key: String(o.key || ""),
    context: o.context !== false,
    budget: num(o.budget, DEFAULTS.budget),
    timeout: num(o.timeout, DEFAULTS.timeout),
    source: !isBlank(opt.endpoints) || !isBlank(opt.endpoint) || !isBlank(opt.model)
      ? "options"
      : !isBlank(file.endpoints) || !isBlank(file.endpoint) || !isBlank(file.model)
        ? "advisor.json"
        : !isBlank(fromEnv.model) || !isBlank(fromEnv.endpoint)
          ? "env"
          : "defaults",
  };
}
