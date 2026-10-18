// 插件页面的数据文件。
//
// 页面跑在 magpie 的沙箱里（CSP 是 sandbox allow-scripts、connect-src 'none'），
// 连不了网络，只能读插件目录下的静态文件。所以「可选模型」和「最近一次调用」
// 由插件自己写成两个 JS 文件，页面用 <script> 加载。
//
// 写失败不影响咨询本身：页面数据只是辅助。

import { writeFileSync, mkdirSync, chmodSync } from "node:fs";
import { PAGE_DIR, MODELS_FILE, STATE_FILE } from "./config.js";

function put(file, name, payload) {
  try {
    mkdirSync(PAGE_DIR, { recursive: true });
    writeFileSync(file, "window." + name + " = " + JSON.stringify(payload) + ";\n");
    try { chmodSync(file, 0o644); } catch (e) { /* 权限继承自目录即可 */ }
  } catch (e) {
    // 页面数据写不进去时，页面只是少一块信息
  }
}

// writePageModels 写网关地址和它当前提供的模型。
// 存的是 /v1/models 的完整条目（id、显示名、provider、上下文窗口、
// 是否推理模型），页面才能像 magpie 自己的选择器那样分组、显示名字。
// 旧版本只存 id 字符串，这里兼容一下。
export function writePageModels(gateway, models) {
  if (!Array.isArray(models) || !models.length) return;
  const entries = models
    .map((m) => (typeof m === "string" ? { id: m } : m))
    .filter((m) => m && m.id);
  if (!entries.length) return;
  put(MODELS_FILE, "MAGPIE_ADVISOR_MODELS", {
    at: new Date().toISOString(),
    gateway: gateway || "",
    models: entries,
  });
}

// writePageState 写最近一次咨询的结果（成功或失败）。
export function writePageState(state) {
  if (!state) return;
  put(STATE_FILE, "MAGPIE_ADVISOR_STATE", { at: new Date().toISOString(), ...state });
}
